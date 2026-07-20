"""オーバーレイの点滅表示のテスト。

タイマーの発火は待たない。位相を進める `_blink_tick` を直接呼ぶことで、
実時間に依存せずに「消える/戻る」を確かめる。

ここで押さえたいのは見た目そのものより、消えたまま戻らなくなる経路が
無いことと、消えている間もインスタンスを選べること。
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from annotate_tool import style
from annotate_tool.coco_data import Annotation
from annotate_tool.widgets.image_view import ImageView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_anns(count: int = 2) -> list[Annotation]:
    return [
        Annotation(
            id=i,
            image_id=1,
            category_id=1,
            segmentation=[[0, 0, 5, 0, 5, 5, 0, 5]],
        )
        for i in range(count)
    ]


@pytest.fixture
def view(app):
    v = ImageView()
    v.set_image(QPixmap(10, 10))
    v.set_overlays(make_anns())
    yield v
    v.deleteLater()


def opacities(view: ImageView) -> list[float]:
    return [item.opacity() for items in view._items_by_index for item in items]


def test_off_by_default(view: ImageView):
    assert not view._blink_timer.isActive()
    assert opacities(view) == [1.0, 1.0]


def test_tick_hides_and_restores(view: ImageView):
    view.set_blink_enabled(True)
    assert view._blink_timer.isActive()

    view._blink_tick()
    assert opacities(view) == [style.BLINK_OFF_OPACITY] * 2
    view._blink_tick()
    assert opacities(view) == [1.0, 1.0]


def test_disabling_while_hidden_restores(view: ImageView):
    """消えている位相で止めても、消えたままにならない。"""
    view.set_blink_enabled(True)
    view._blink_tick()
    view.set_blink_enabled(False)

    assert not view._blink_timer.isActive()
    assert opacities(view) == [1.0, 1.0]


def test_hidden_phase_survives_overlay_rebuild(view: ImageView):
    """画像送りなどでアイテムを作り直しても位相が引き継がれる。"""
    view.set_blink_enabled(True)
    view._blink_tick()
    view.set_overlays(make_anns(3))

    assert opacities(view) == [style.BLINK_OFF_OPACITY] * 3


def test_add_mode_pauses_and_restores(view: ImageView):
    """塗り編集中は止まり、抜けたら設定に従って再開する。"""
    view.set_blink_enabled(True)
    view._blink_tick()

    view.set_add_mode(True)
    assert not view._blink_timer.isActive()
    assert opacities(view) == [1.0, 1.0]  # 基準の形は出したまま

    view.set_add_mode(False)
    assert view._blink_timer.isActive()


def test_add_mode_does_not_start_blink_when_disabled(view: ImageView):
    view.set_add_mode(True)
    view.set_add_mode(False)
    assert not view._blink_timer.isActive()


def test_hidden_items_stay_clickable(view: ImageView):
    """消えている間もクリックで選べる(setVisible ではなく不透明度で消すこと)。

    setVisible(False) にすると当たり判定ごと消え、点滅の半分の時間は
    インスタンスを選べなくなる。
    """
    view.set_blink_enabled(True)
    view._blink_tick()

    for items in view._items_by_index:
        for item in items:
            assert item.isVisible()
