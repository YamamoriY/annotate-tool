"""ショートカットの有効/無効が状態に追従するかのテスト。

ここだけは QApplication を立ててウィンドウを実際に組み立てる。判定を
`_enabled` の1箇所へ集約した以上、その1箇所が状態を正しく読めているかは
押さえておく必要があるため(ここが壊れると、キーが黙って効かなくなる)。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from annotate_tool import shortcuts, style
from annotate_tool.coco_data import Annotation, ImageEntry
from annotate_tool.widgets.control_group import ControlGroup
from annotate_tool.widgets.main_window import ViewerWindow


class StubDataset:
    """ViewerWindow が dataset に求めるものだけを持つスタブ。"""

    def __init__(self, image_path: str = "missing.png"):
        self._image_path = image_path
        self.images = [ImageEntry(1, "a.png", 10, 10), ImageEntry(2, "b.png", 10, 10)]
        self.anns = {
            1: [
                Annotation(
                    id=i,
                    image_id=1,
                    category_id=1,
                    segmentation=[[0, 0, 5, 0, 5, 5, 0, 5]],
                )
                for i in (10, 11)
            ]
        }

    def annotations_for(self, image_id: int) -> list[Annotation]:
        return self.anns.get(image_id, [])

    def category_name(self, category_id: int) -> str:
        return "x"

    def image_path(self, image: ImageEntry) -> str:
        return self._image_path

    def save(self) -> None:
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def image_file(tmp_path_factory, app):
    """実在する画像。読めないと _load_image が途中で抜け、情報表示が空のままになる。"""
    path = tmp_path_factory.mktemp("images") / "a.png"
    QImage(10, 10, QImage.Format_RGB32).save(str(path))
    return str(path)


@pytest.fixture
def window(app, image_file):
    w = ViewerWindow(StubDataset(image_file))
    # ボタンの表示状態を見るため実際に表示する。伏せたままだと isVisible() が
    # 常に False を返し、「出ていないこと」の確認が素通りしてしまう。
    w.show()
    yield w
    w.close()


def enabled(window, shortcut) -> bool:
    return window._actions[shortcut.id].isEnabled()


def test_nothing_selected(window):
    assert enabled(window, shortcuts.ADD)
    assert not enabled(window, shortcuts.EDIT)
    assert not enabled(window, shortcuts.DELETE)


def test_single_selection_allows_edit_and_delete(window):
    window.state.select(0)
    assert enabled(window, shortcuts.EDIT)
    assert enabled(window, shortcuts.DELETE)
    assert not enabled(window, shortcuts.ADD)  # 選択中は追加を出さない
    assert window.action_bar._edit_btn.isVisible()  # ボタンも出る


def test_multi_selection_blocks_edit(window):
    """複数選択では塗り直す対象が決まらない。キーもボタンも揃って無効。"""
    window.state.set_selection([0, 1])
    assert not enabled(window, shortcuts.EDIT)
    assert not window.action_bar._edit_btn.isVisible()
    assert enabled(window, shortcuts.DELETE)


def test_add_mode_blocks_image_navigation(window):
    """塗っている最中に画像が変わると、塗りかけが黙って失われるため止める。"""
    window.state.enter_add_mode()
    assert not enabled(window, shortcuts.PREV)
    assert not enabled(window, shortcuts.NEXT)


def test_navigation_returns_after_leaving_add_mode(window):
    window.state.enter_add_mode()
    window.state.cancel_add_mode()
    assert enabled(window, shortcuts.PREV)
    assert enabled(window, shortcuts.NEXT)


def test_escape_is_always_available(window):
    assert enabled(window, shortcuts.ESCAPE)
    window.state.enter_add_mode()
    assert enabled(window, shortcuts.ESCAPE)


def test_confirm_needs_something_to_confirm(window):
    """確定するものが無いうちは確定できないこと。

    「確定」ボタンが出る条件と揃えてある。何も塗っていない状態で A を押しても
    黙ってモードを抜けたりしない(抜けたいときは Esc)。
    """
    window.state.enter_add_mode()
    assert not enabled(window, shortcuts.CONFIRM)

    window.view._add_path_point(QPoint(1, 1))
    assert enabled(window, shortcuts.CONFIRM)  # 頂点を打てば確定できる

    window.view.cancel_path()
    assert not enabled(window, shortcuts.CONFIRM)
    assert window.state.add_mode, "確定できないだけで、モードは維持される"


def test_tool_shortcuts_only_work_in_add_mode(window):
    """1/2/3 はツールパネルが出ている追加モード中だけ。"""
    for shortcut, _tool in ViewerWindow._TOOL_SHORTCUTS:
        assert not enabled(window, shortcut)
    window.state.enter_add_mode()
    for shortcut, _tool in ViewerWindow._TOOL_SHORTCUTS:
        assert enabled(window, shortcut)


def test_tool_shortcut_updates_panel_and_view(window):
    """ToolPanel.set_tool はシグナルを出さないので、ビューへは別途伝える必要がある。

    片方だけ更新すると、パネルの表示と実際の描画がずれる。
    """
    window.state.enter_add_mode()
    for shortcut, tool in ViewerWindow._TOOL_SHORTCUTS:
        window._select_tool(tool)
        assert window.tool_panel.tool() is tool, shortcut.id
        assert window.view._tool is tool, shortcut.id


def test_entry_tool_is_carried_over(window):
    """モードを抜けて入り直すと、前回使ったツールがそのまま戻る。

    以前は消しゴムだけブラシへ戻していた(空のマスクを消しても何も起きないため)
    が、修正モードでは最初から塗られているので消しゴムで入りたい場面がある。
    """
    for _shortcut, tool in ViewerWindow._TOOL_SHORTCUTS:
        window.state.enter_add_mode()
        window._select_tool(tool)
        window.state.cancel_add_mode()

        window.state.enter_add_mode()
        assert window.tool_panel.tool() is tool
        assert window.view._tool is tool
        window.state.cancel_add_mode()


def test_info_label_sits_in_the_image_group(window):
    """現在の画像の情報はステータスバーではなく、右パネル最上段の「画像」の中。"""
    group = window.side_panel.widget().layout().itemAt(0).widget()
    assert isinstance(group, ControlGroup)
    assert group.findChild(QLabel).text() == "画像", "最上段は「画像」グループ"
    assert window._info_label.parent() is group
    assert window._info_label not in window.statusBar().findChildren(QLabel)


def test_image_group_holds_the_navigation_buttons(window):
    """画像送りも同じグループに入る(見る対象と移動手段をまとめる)。"""
    group = window.side_panel.widget().layout().itemAt(0).widget()
    labels = [b.text() for b in group.findChildren(QPushButton)]
    assert len(labels) == 2 and any("前" in t for t in labels)


def test_info_label_style(window):
    assert window._info_label.styleSheet() == style.INFO_LABEL_QSS
    assert window._info_label.wordWrap(), "パネル幅では収まらないため折り返す"


def test_info_label_splits_file_and_contents(window):
    """1行目にどの画像か(ファイル名は太字)、2行目にその中身。"""
    text = window._info_label.text()
    assert "<b>a.png</b> [1/2]" in text
    assert "インスタンス数: 2" in text
    assert text.index("a.png") < text.index("インスタンス数")


def test_info_label_follows_the_current_image(window):
    window.state.next_image()
    assert "<b>b.png</b> [2/2]" in window._info_label.text()


def test_info_label_escapes_the_file_name(app, image_file):
    """ファイル名は任意の文字列。素で流すと HTML として解釈されてしまう。"""
    dataset = StubDataset(image_file)
    dataset.images = [ImageEntry(1, "a<b>&.png", 10, 10)]
    w = ViewerWindow(dataset)
    try:
        assert "a&lt;b&gt;&amp;.png" in w._info_label.text()
    finally:
        w.close()


def test_tool_button_labels_fit(window):
    """ラベルにキー表記が付くため、固定幅に収まるか確かめる。

    溢れても Qt は省略記号へ潰すだけで、エラーにはならない。
    """
    for button in window.tool_panel._buttons.values():
        assert button.sizeHint().width() <= style.TOOL_BUTTON_WIDTH, button.text()


def test_undo_point_follows_the_drawn_path(window):
    """頂点の増減はマウス操作で起きるので、pathChanged 経由で追従する。"""
    window.state.enter_add_mode()
    assert not enabled(window, shortcuts.UNDO_POINT)  # まだ打っていない

    window.view._add_path_point(QPoint(1, 1))
    assert enabled(window, shortcuts.UNDO_POINT)

    window.view.undo_path_point()
    assert not enabled(window, shortcuts.UNDO_POINT)  # 打つ前へ戻った
