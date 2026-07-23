"""右クリックで反対のツール(ブラシ⇔消しゴム)を使う設定のテスト。

本題はマウスボタンの振り分けなので、内部メソッドではなく実物の QMouseEvent を
ハンドラへ渡して確かめる(組み立て方は test_touchpad と同じ)。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from annotate_tool import settings as settings_module
from annotate_tool.tools import Tool
from annotate_tool.widgets.image_view import ImageView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = ImageView()
    v.resize(120, 120)
    pm = QPixmap(40, 40)
    pm.fill()
    v.set_image(pm)
    v.set_add_mode(True)
    yield v
    v.set_add_mode(False)
    v.deleteLater()


def mouse(kind, pos, button, buttons):
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button, buttons, Qt.NoModifier)


def drag(view: ImageView, button: Qt.MouseButton, pos=QPoint(60, 60)) -> None:
    """press → release の一筆(動かさない点打ち)。"""
    view.mousePressEvent(mouse(QEvent.MouseButtonPress, pos, button, button))
    view.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, pos, button, Qt.NoButton))


def mask_any(view: ImageView) -> bool:
    return bool(view._mask_alpha().any())


# --- 既定(設定 OFF)---------------------------------------------------------
def test_right_click_does_nothing_by_default(view):
    drag(view, Qt.RightButton)
    assert not mask_any(view), "設定 OFF の右クリックでは塗らない"
    assert not view._painting


# --- ブラシ選択中の右クリック = 消しゴム --------------------------------------
def test_right_drag_erases_while_brush_selected(view):
    view.set_right_click_swap(Tool.BRUSH, True)
    drag(view, Qt.LeftButton)
    assert mask_any(view), "前提: 左の一筆で塗れている"

    cleared = []
    view.paintCleared.connect(lambda: cleared.append(True))
    drag(view, Qt.RightButton)
    assert not mask_any(view), "同じ場所への右の一筆で消える(半径も同じ 12px)"
    assert cleared, "消し切ったら paintCleared が出る(確定を引っ込める)"
    assert view._tool is Tool.BRUSH, "一筆が終われば選択中のツールはブラシのまま"


def test_right_stroke_does_not_emit_paint_started(view):
    view.set_right_click_swap(Tool.BRUSH, True)
    started = []
    view.paintStarted.connect(lambda: started.append(True))
    drag(view, Qt.RightButton)  # 空マスクへの消しゴム
    assert not started, "消しゴムだけ動かしても「確定」は出さない"


# --- 消しゴム選択中の右クリック = ブラシ --------------------------------------
def test_right_drag_paints_while_eraser_selected(view):
    view.set_tool(Tool.ERASER)
    view.set_right_click_swap(Tool.ERASER, True)
    started = []
    view.paintStarted.connect(lambda: started.append(True))

    drag(view, Qt.RightButton)
    assert mask_any(view), "右の一筆はブラシとして塗る"
    assert started, "ブラシとして塗ったら「確定」を出す"
    assert view._tool is Tool.ERASER, "選択中のツールは消しゴムのまま"

    drag(view, Qt.LeftButton)
    assert not mask_any(view), "左は選択中の消しゴムのまま"


# --- 一筆の最中の別ボタン -----------------------------------------------------
def test_other_button_is_ignored_mid_stroke(view):
    view.set_right_click_swap(Tool.BRUSH, True)
    pos = QPoint(60, 60)
    view.mousePressEvent(
        mouse(QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton)
    )
    view.mousePressEvent(
        mouse(
            QEvent.MouseButtonPress, pos, Qt.RightButton,
            Qt.LeftButton | Qt.RightButton,
        )
    )
    assert view._active_tool is Tool.BRUSH, "塗っている最中の右押下では入れ替えない"
    # 先に始めたボタンを離すまで一筆は続く
    view.mouseReleaseEvent(
        mouse(QEvent.MouseButtonRelease, pos, Qt.RightButton, Qt.LeftButton)
    )
    assert view._painting, "後から押したボタンの release では一筆を終えない"
    view.mouseReleaseEvent(
        mouse(QEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.NoButton)
    )
    assert not view._painting
    assert mask_any(view), "左の一筆は普通に塗れている"


# --- ポリゴンツールは対象外 ---------------------------------------------------
def test_polygon_tool_ignores_right_click(view):
    view.set_right_click_swap(Tool.BRUSH, True)
    view.set_tool(Tool.POLYGON)
    drag(view, Qt.RightButton)
    assert not mask_any(view)
    assert not view._painting


# --- 設定の永続化 ------------------------------------------------------------
def test_swap_settings_default_to_off(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    assert settings_module.brush_right_click_eraser(s) is False
    assert settings_module.eraser_right_click_brush(s) is False


def test_swap_settings_roundtrip(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    settings_module.set_brush_right_click_eraser(s, True)
    settings_module.set_eraser_right_click_brush(s, True)
    assert settings_module.brush_right_click_eraser(s) is True
    assert settings_module.eraser_right_click_brush(s) is True
