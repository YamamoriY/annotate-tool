"""タッチパッドモードとパン操作のテスト。

ホイールの解釈(ズーム / パン)はビューの transform とスクロールバーの変化で
確かめる。イベントは実物の QWheelEvent / QMouseEvent を組み立てて直接
ハンドラへ渡す(表示は不要)。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication

from annotate_tool import settings as settings_module
from annotate_tool.widgets.image_view import ImageView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = ImageView()
    v.resize(120, 120)
    v.set_image(QPixmap(400, 400))
    yield v
    v.deleteLater()


def send_wheel(view, angle_y=120, pixel=QPoint(), modifiers=Qt.NoModifier):
    event = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        pixel,
        QPoint(0, angle_y),
        Qt.NoButton,
        modifiers,
        Qt.ScrollUpdate,
        False,
    )
    view.wheelEvent(event)


def mouse(kind, pos, button, buttons):
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button, buttons, Qt.NoModifier)


def zoom_in_for_scroll_room(view):
    """スクロールバーに可動域ができるまでズームインする(パンのテスト用)。"""
    view._zoom_by(8.0)
    assert view.horizontalScrollBar().maximum() > 0, "パンの余地がある前提"


# --- ホイールの解釈 ---------------------------------------------------------
def test_wheel_zooms_by_default(view):
    before = view.transform().m11()
    send_wheel(view, angle_y=120)
    assert view.transform().m11() == pytest.approx(before * 1.25)


def test_touchpad_mode_wheel_pans_instead_of_zooming(view):
    view.set_touchpad_mode(True)
    zoom_in_for_scroll_room(view)
    vbar = view.verticalScrollBar()
    scale_before, scroll_before = view.transform().m11(), vbar.value()
    send_wheel(view, angle_y=-120, pixel=QPoint(0, -30))
    assert view.transform().m11() == scale_before, "ズームしない"
    assert vbar.value() == scroll_before + 30, "pixelDelta ぶんスクロールする"


def test_touchpad_mode_falls_back_to_angle_delta(view):
    """pixelDelta の取れないデバイスでは角度から換算する(1 ノッチ = 60px)。"""
    view.set_touchpad_mode(True)
    zoom_in_for_scroll_room(view)
    vbar = view.verticalScrollBar()
    before = vbar.value()
    send_wheel(view, angle_y=-120)
    assert vbar.value() == before + 60


def test_ctrl_wheel_zooms_even_in_touchpad_mode(view):
    """Windows のタッチパッドはピンチを Ctrl+ホイールとして届ける。"""
    view.set_touchpad_mode(True)
    before = view.transform().m11()
    send_wheel(view, angle_y=120, modifiers=Qt.ControlModifier)
    assert view.transform().m11() == pytest.approx(before * 1.25)


# --- Space+左ドラッグのパン --------------------------------------------------
def test_space_left_drag_pans(view):
    zoom_in_for_scroll_room(view)
    hbar = view.horizontalScrollBar()
    hbar.setValue(hbar.maximum() // 2)  # 端では片方向へ動けないため中央から
    before = hbar.value()

    view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
    view.mousePressEvent(
        mouse(QEvent.MouseButtonPress, QPoint(50, 50), Qt.LeftButton, Qt.LeftButton)
    )
    view.mouseMoveEvent(
        mouse(QEvent.MouseMove, QPoint(30, 50), Qt.NoButton, Qt.LeftButton)
    )
    assert hbar.value() == before + 20, "左へ 20px 動かすと右へ 20px スクロール"

    view.mouseReleaseEvent(
        mouse(QEvent.MouseButtonRelease, QPoint(30, 50), Qt.LeftButton, Qt.NoButton)
    )
    view.keyReleaseEvent(QKeyEvent(QEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier))
    assert not view._panning


def test_left_drag_without_space_does_not_pan(view):
    zoom_in_for_scroll_room(view)
    hbar = view.horizontalScrollBar()
    hbar.setValue(hbar.maximum() // 2)
    before = hbar.value()

    view.mousePressEvent(
        mouse(QEvent.MouseButtonPress, QPoint(50, 50), Qt.LeftButton, Qt.LeftButton)
    )
    view.mouseMoveEvent(
        mouse(QEvent.MouseMove, QPoint(30, 50), Qt.NoButton, Qt.LeftButton)
    )
    view.mouseReleaseEvent(
        mouse(QEvent.MouseButtonRelease, QPoint(30, 50), Qt.LeftButton, Qt.NoButton)
    )
    assert hbar.value() == before, "通常の左ドラッグは矩形選択のままパンしない"


# --- 設定の永続化 ------------------------------------------------------------
def test_touchpad_mode_defaults_to_off(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    assert settings_module.touchpad_mode(s) is False


def test_touchpad_mode_roundtrip(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    settings_module.set_touchpad_mode(s, True)
    assert settings_module.touchpad_mode(s) is True
