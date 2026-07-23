"""一筆単位の取り消し(undo_mask)のテスト。

マウスイベントの合成は環境依存が強いので、press/release の塗り分岐と同じ
順序でビューの内部メソッドを呼ぶヘルパで一筆を再現する。
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from annotate_tool import style
from annotate_tool.tools import Tool
from annotate_tool.widgets.image_view import ImageView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = ImageView()
    pm = QPixmap(40, 40)
    pm.fill()
    v.set_image(pm)
    v.set_add_mode(True)
    yield v
    v.set_add_mode(False)


def stroke(view: ImageView, *points: QPointF, tool: Tool | None = None) -> None:
    """mousePress/Move/Release の塗り分岐と同じ順序で一筆を打つ。"""
    if tool is not None:
        view.set_tool(tool)
    view._painting = True
    view._begin_stroke()
    for pt in points:
        view._paint_to(pt)
    if view._tool is Tool.BRUSH and not view._paint_started:
        view._paint_started = True
        view.paintStarted.emit()
    view._painting = False
    view._last_paint_pt = None
    view._end_stroke()
    if view._tool is Tool.ERASER and view._paint_started and view._mask_is_empty():
        view._paint_started = False
        view._min_paint_radius = style.BRUSH_RADIUS_MAX
        view.paintCleared.emit()


def alpha(view: ImageView) -> np.ndarray:
    return view._mask_alpha().copy()


def test_undo_restores_previous_stroke_pixels(view):
    stroke(view, QPointF(8, 8))
    first = alpha(view)
    stroke(view, QPointF(30, 30))
    assert not np.array_equal(alpha(view), first)

    view.undo_mask()
    assert np.array_equal(alpha(view), first)
    assert view.has_mask_history(), "一筆目はまだ取り消せる"

    view.undo_mask()
    assert not alpha(view).any(), "全部取り消すと空のマスクへ戻る"
    assert not view.has_mask_history()


def test_undo_restores_erased_pixels(view):
    stroke(view, QPointF(8, 8))
    painted = alpha(view)
    stroke(view, QPointF(8, 8), tool=Tool.ERASER)
    assert not np.array_equal(alpha(view), painted)

    view.undo_mask()
    assert np.array_equal(alpha(view), painted)


def test_undo_unbakes_closed_path(view):
    view._path_points = [QPointF(5, 5), QPointF(30, 5), QPointF(30, 30)]
    assert view.close_path()
    assert alpha(view).any()
    assert view.has_mask_history()

    view.undo_mask()
    assert not alpha(view).any()
    assert not view._paint_started, "焼く前は何も塗っていなかった"


def test_erase_all_then_undo_reemits_paint_started(view):
    events: list[str] = []
    view.paintStarted.connect(lambda: events.append("started"))
    view.paintCleared.connect(lambda: events.append("cleared"))

    stroke(view, QPointF(8, 8))
    min_radius = view._min_paint_radius
    # 画像全面(40x40)を覆う太さで消し切る
    view.set_radius(Tool.ERASER, style.BRUSH_RADIUS_MAX)
    stroke(view, QPointF(20, 20), tool=Tool.ERASER)
    assert events == ["started", "cleared"]
    assert view._min_paint_radius == style.BRUSH_RADIUS_MAX  # クリアでリセット済み

    view.undo_mask()
    assert events == ["started", "cleared", "started"], "「確定」を出し直す"
    assert view._min_paint_radius == min_radius, "スリバー判定の基準も戻る"


def test_undo_first_stroke_emits_paint_cleared(view):
    events: list[str] = []
    view.paintCleared.connect(lambda: events.append("cleared"))
    stroke(view, QPointF(8, 8))
    view.undo_mask()
    assert events == ["cleared"], "「確定」を引っ込める"
    assert not view._paint_started


def test_noop_eraser_stroke_pushes_nothing(view):
    stroke(view, QPointF(35, 35), tool=Tool.ERASER)  # 空白を消しても何も変わらない
    assert not view.has_mask_history()


def test_history_is_capped(view, monkeypatch):
    monkeypatch.setattr(style, "MASK_UNDO_LIMIT", 2)
    for pt in (QPointF(5, 5), QPointF(20, 20), QPointF(35, 35)):
        stroke(view, pt)
    assert len(view._mask_history) == 2
    assert view._mask_history_bytes == sum(
        r.width() * r.height() * 4 for r, *_ in view._mask_history
    )


def test_undo_is_ignored_while_painting(view):
    stroke(view, QPointF(8, 8))
    before = alpha(view)
    view._painting = True
    view.undo_mask()
    assert view.has_mask_history()
    assert np.array_equal(alpha(view), before)


def test_history_dies_with_the_session(view):
    stroke(view, QPointF(8, 8))
    view.set_add_mode(False)
    view.set_add_mode(True)
    assert not view.has_mask_history()
