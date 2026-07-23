"""筆・消しゴムの太さの永続化テスト。

設定ファイル(INI)への読み書きと、読んだ値がツールパネル / ビューの初期値に
なることを確かめる。表示は不要なので、ウィジェットは組み立てるだけ。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from annotate_tool import settings as settings_module
from annotate_tool import style
from annotate_tool.tools import Tool
from annotate_tool.widgets.image_view import ImageView
from annotate_tool.widgets.main_window import ViewerWindow
from annotate_tool.widgets.tool_panel import ToolPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ini(tmp_path):
    return QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)


# --- 設定ファイル -----------------------------------------------------------
def test_defaults_when_unset(ini):
    radii = settings_module.tool_radii(ini)
    assert radii[Tool.BRUSH] == style.BRUSH_RADIUS
    assert radii[Tool.ERASER] == style.ERASER_RADIUS


def test_roundtrip(ini):
    settings_module.set_tool_radius(ini, Tool.BRUSH, 30.0)
    settings_module.set_tool_radius(ini, Tool.ERASER, 8.0)
    ini.sync()

    reopened = QSettings(ini.fileName(), QSettings.IniFormat)
    radii = settings_module.tool_radii(reopened)
    assert radii[Tool.BRUSH] == 30.0
    assert radii[Tool.ERASER] == 8.0


def test_out_of_range_is_clamped(ini):
    settings_module.set_tool_radius(ini, Tool.BRUSH, style.BRUSH_RADIUS_MAX + 100)
    settings_module.set_tool_radius(ini, Tool.ERASER, 0.0)
    radii = settings_module.tool_radii(ini)
    assert radii[Tool.BRUSH] == style.BRUSH_RADIUS_MAX
    assert radii[Tool.ERASER] == style.BRUSH_RADIUS_MIN


def test_broken_value_falls_back_to_default(ini):
    """手で書き換えられるファイルなので、数値でない行でも起動を止めない。"""
    ini.setValue(settings_module.KEY_TOOL_RADIUS[Tool.BRUSH], "ふとめ")
    assert settings_module.tool_radii(ini)[Tool.BRUSH] == style.BRUSH_RADIUS


def test_polygon_has_no_radius_key(ini):
    settings_module.set_tool_radius(ini, Tool.POLYGON, 20.0)
    assert ini.allKeys() == [], "太さを持たないツールは書かない"


# --- 読んだ値が初期値になるか -------------------------------------------------
def test_tool_panel_starts_from_given_radii(app, tmp_path):
    from annotate_tool import shortcuts

    keymap, _ = shortcuts.resolve({})
    view = ImageView()
    panel = ToolPanel(view, keymap, {Tool.BRUSH: 30.0, Tool.ERASER: 8.0})
    try:
        assert panel.radius(Tool.BRUSH) == 30.0
        assert panel.radius(Tool.ERASER) == 8.0
    finally:
        panel.deleteLater()
        view.deleteLater()


def test_window_restores_the_radius_after_restart(app):
    """立ち上げ直しても前回の太さで始まる(設定は conftest で使い捨てへ向く)。"""
    first = ViewerWindow()
    try:
        first.tool_panel._sliders[Tool.BRUSH].set_radius(30.0)
        first.tool_panel._sliders[Tool.ERASER].set_radius(8.0)
    finally:
        first.close()

    second = ViewerWindow()
    try:
        assert second.tool_panel.radius(Tool.BRUSH) == 30.0
        assert second.tool_panel.radius(Tool.ERASER) == 8.0
        # スライダーだけでなくビュー(実際に塗る側)へも届いている
        assert second.view._radii[Tool.BRUSH] == 30.0
        assert second.view._radii[Tool.ERASER] == 8.0
    finally:
        second.close()
