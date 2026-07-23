"""選択→編集→保存の往復でポリゴンが痩せないことのテスト。

_prefill_mask(ポリゴン→マスク焼き込み)と painted_polygons(findContours で
ポリゴン化)の半ピクセル規約が食い違うと、保存のたびに右端・下端が1pxずつ
削れていく。往復を繰り返しても形が縮まないことを確認する。
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from annotate_tool.coco_data import Annotation
from annotate_tool.widgets.image_view import ImageView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = ImageView()
    pm = QPixmap(200, 200)
    pm.fill()
    v.set_image(pm)
    yield v
    v.set_add_mode(False)


def make_annotation(segmentation: list[list[float]]) -> Annotation:
    return Annotation(id=1, image_id=1, category_id=1, segmentation=segmentation)


def bbox(polys: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [flat[i] for flat in polys for i in range(0, len(flat), 2)]
    ys = [flat[i] for flat in polys for i in range(1, len(flat), 2)]
    return min(xs), min(ys), max(xs), max(ys)


def roundtrip(view: ImageView, polys: list[list[float]]) -> list[list[float]]:
    """選択→編集開始(焼き込み)→何も塗らずに保存、をそのまま再現する。"""
    view.set_add_mode(True, edit_index=0, edit_annotation=make_annotation(polys))
    result = view.painted_polygons()
    view.set_add_mode(False)
    return result


def test_prefill_save_roundtrip_keeps_size(view):
    # findContours の出力と同じく、辺が境界ピクセルの中心を通る矩形から始める
    polys = [[30.0, 30.0, 170.0, 30.0, 170.0, 120.0, 30.0, 120.0]]
    original = bbox(polys)
    for _ in range(3):
        polys = roundtrip(view, polys)
        assert polys, "往復でポリゴンが消えてはいけない"
        assert bbox(polys) == pytest.approx(original), (
            "編集→保存の往復で形が縮んではいけない"
        )
