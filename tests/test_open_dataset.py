"""「COCO JSON を開く」まわりのテスト。

起動時の既定パス(data/instances.json)を廃したので、代わりに
「引数 > 前回開いたファイル > 何も開かない」が守られていることを押さえる。
ここが崩れると、起動しても何も出ない/前回の続きから始められない。
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from annotate_tool import app as app_module
from annotate_tool import settings as settings_module
from annotate_tool.coco_data import CocoDataset
from annotate_tool.widgets import main_window


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_dataset(dir_path, file_name: str = "a.png"):
    """画像1枚・アノテーション1件の最小 COCO を作り、JSON のパスを返す。"""
    dir_path.mkdir(parents=True, exist_ok=True)
    QImage(10, 10, QImage.Format_RGB32).save(str(dir_path / file_name))
    path = dir_path / "instances.json"
    path.write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": file_name, "width": 10, "height": 10}],
                "categories": [{"id": 1, "name": "log"}],
                "annotations": [
                    {
                        "id": 1,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [[0, 0, 5, 0, 5, 5]],
                        "area": 12.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def ini(monkeypatch, tmp_path):
    """設定ファイルを tmp へ向ける(利用者の実 INI を汚さない)。"""
    path = tmp_path / "cfg" / "annotate-tool.ini"
    monkeypatch.setattr(
        settings_module, "load", lambda: QSettings(str(path), QSettings.IniFormat)
    )
    return path


# --- 空のデータセット --------------------------------------------------------
def test_empty_dataset_has_nothing_and_saves_nowhere(tmp_path):
    ds = CocoDataset()
    assert ds.json_path is None
    assert ds.images == [] and ds.annotations == []
    ds.save()  # 書き出す先が無いので何もしない(例外も出さない)


def test_window_starts_without_a_dataset(app, ini):
    w = main_window.ViewerWindow()
    try:
        assert w._path_label.text() == "未選択"
        # 塗る先の画像が無いので「追加」は出さない
        assert not w._actions["add"].isEnabled()
    finally:
        w.close()


# --- 開く --------------------------------------------------------------------
def test_open_dataset_swaps_the_view_and_remembers_the_path(app, ini, tmp_path):
    path = make_dataset(tmp_path)
    w = main_window.ViewerWindow()
    try:
        assert w.open_dataset(path)
        assert w.state.dataset.json_path == path
        assert str(path) in w._path_label.text()
        assert "a.png" in w._info_label.text()
        assert w._actions["add"].isEnabled()
        # 次の起動で開き直せるよう、切り替えた時点で書き出す
        settings_module.flush(w.settings)
        assert settings_module.last_json(settings_module.load()) == str(path)
    finally:
        w.close()


def test_open_dataset_keeps_the_current_one_on_failure(app, ini, tmp_path):
    path = make_dataset(tmp_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")

    w = main_window.ViewerWindow()
    try:
        w.open_dataset(path)
        assert not w.open_dataset(broken), "壊れたファイルは開けない"
        assert w.state.dataset.json_path == path, "開けなければ今の内容を保つ"
        assert not w.open_dataset(tmp_path / "nope.json"), "存在しないファイル"
        assert w.state.dataset.json_path == path
    finally:
        w.close()


def test_open_dataset_resets_selection_and_index(app, ini, tmp_path):
    first = make_dataset(tmp_path / "one", "a.png")
    second = make_dataset(tmp_path / "two", "b.png")

    w = main_window.ViewerWindow()
    try:
        w.open_dataset(first)
        w.state.select(0)
        assert w.state.selected_indices == (0,)
        w.open_dataset(second)
        assert w.state.selected_indices == (), "別データの選択を持ち越さない"
        assert w.state.image_index == 0
        assert "b.png" in w._info_label.text()
    finally:
        w.close()


# --- 起動時に開くファイルの決定 ------------------------------------------------
def test_startup_path_prefers_the_argument(ini, tmp_path):
    settings_module.set_last_json(settings_module.load(), str(tmp_path / "old.json"))
    given = tmp_path / "given.json"
    assert app_module.startup_path(given) == given


def test_startup_path_falls_back_to_the_last_opened(ini, tmp_path):
    path = make_dataset(tmp_path)
    s = settings_module.load()
    settings_module.set_last_json(s, str(path))
    settings_module.flush(s)
    assert app_module.startup_path(None) == path


def test_startup_path_ignores_a_vanished_file(ini, tmp_path):
    s = settings_module.load()
    settings_module.set_last_json(s, str(tmp_path / "gone.json"))
    settings_module.flush(s)
    # 前回のファイルが消えていても起動は止めない(何も開かずに立ち上げる)
    assert app_module.startup_path(None) is None


def test_startup_path_without_any_history(ini):
    assert app_module.startup_path(None) is None
