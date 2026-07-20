"""「キーボードショートカット設定」ボタンのテスト。

キー割り当ての変更は INI の直接編集で行うため、ファイルへたどり着けることが
機能の本体になる。開いた先が空だったり存在しなかったりしないことを見る。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from annotate_tool import settings as settings_module
from annotate_tool.coco_data import ImageEntry
from annotate_tool.widgets import main_window


class StubDataset:
    images = [ImageEntry(1, "a.png", 10, 10)]

    def annotations_for(self, image_id: int) -> list:
        return []

    def category_name(self, category_id: int) -> str:
        return "x"

    def image_path(self, image: ImageEntry) -> str:
        return "missing.png"

    def save(self) -> None:
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def opened(monkeypatch, tmp_path, app):
    """設定ファイルを tmp へ向け、フォルダを開く代わりに記録する。"""
    ini = tmp_path / "cfg" / "annotate-tool.ini"  # まだ存在しないフォルダ
    monkeypatch.setattr(
        settings_module, "load", lambda: QSettings(str(ini), QSettings.IniFormat)
    )
    urls: list[str] = []

    class FakeDesktopServices:
        @staticmethod
        def openUrl(url):
            urls.append(url.toLocalFile())
            return True

    monkeypatch.setattr(main_window, "QDesktopServices", FakeDesktopServices)
    return urls


def find_button(window) -> QPushButton:
    return next(
        b
        for b in window.findChildren(QPushButton)
        if "ショートカット" in b.text()
    )


def test_button_opens_the_folder_holding_the_ini(opened, tmp_path):
    w = main_window.ViewerWindow(StubDataset())
    try:
        find_button(w).click()
    finally:
        w.close()

    assert len(opened) == 1
    folder = tmp_path / "cfg"
    assert opened[0].rstrip("/\\") == str(folder).replace("\\", "/").rstrip("/")
    assert folder.is_dir(), "存在しないフォルダを開こうとしていない"


def test_ini_is_written_before_opening(opened, tmp_path):
    """開いた先が空に見えないこと。

    QSettings は書き込みを遅延させるため、sync せずに開くと
    「フォルダは出たが設定ファイルが無い」状態になりうる。
    """
    w = main_window.ViewerWindow(StubDataset())
    try:
        find_button(w).click()
    finally:
        w.close()

    ini = tmp_path / "cfg" / "annotate-tool.ini"
    assert ini.exists()
    assert "[shortcuts]" in ini.read_text(encoding="utf-8"), "編集対象が書かれている"
