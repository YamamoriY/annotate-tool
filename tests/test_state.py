"""ViewerState(状態管理層)のテスト。

QObject のシグナルのみ使うため QApplication は不要。dataset は
ViewerState が使うインターフェース(images / annotations_for)だけを
持つスタブで代替する。
"""

from dataclasses import dataclass, field

import pytest

from annotate_tool.coco_data import Annotation, ImageEntry
from annotate_tool.state import ViewerState


@dataclass
class StubDataset:
    images: list[ImageEntry] = field(default_factory=list)
    anns: dict[int, list[Annotation]] = field(default_factory=dict)

    def annotations_for(self, image_id: int) -> list[Annotation]:
        return self.anns.get(image_id, [])


def make_ann(ann_id: int, image_id: int) -> Annotation:
    return Annotation(id=ann_id, image_id=image_id, category_id=1, segmentation=[])


@pytest.fixture
def dataset() -> StubDataset:
    return StubDataset(
        images=[
            ImageEntry(id=1, file_name="a.jpg", width=10, height=10),
            ImageEntry(id=2, file_name="b.jpg", width=10, height=10),
            ImageEntry(id=3, file_name="c.jpg", width=10, height=10),
        ],
        anns={
            1: [make_ann(10, 1), make_ann(11, 1)],
            2: [make_ann(12, 2)],
        },
    )


def test_initial_state(dataset: StubDataset):
    state = ViewerState(dataset)
    assert state.image_index == 0
    assert state.selected_indices == ()
    assert state.overlay_visible is True
    assert state.fill_visible is True
    assert state.current_image().id == 1
    assert [a.id for a in state.current_annotations()] == [10, 11]


def test_navigation_wraps(dataset: StubDataset):
    state = ViewerState(dataset)
    emitted: list[int] = []
    state.imageChanged.connect(emitted.append)

    state.next_image()
    state.next_image()
    state.next_image()  # 3 枚なので先頭へ戻る
    assert emitted == [1, 2, 0]

    state.prev_image()  # 先頭から末尾へ戻る
    assert state.image_index == 2


def test_image_change_clears_selection(dataset: StubDataset):
    state = ViewerState(dataset)
    selections: list[tuple[int, ...]] = []
    state.selectionChanged.connect(selections.append)

    state.select(1)
    state.next_image()
    assert state.selected_indices == ()
    assert selections == [(1,), ()]


def test_select_replaces(dataset: StubDataset):
    state = ViewerState(dataset)
    selections: list[tuple[int, ...]] = []
    state.selectionChanged.connect(selections.append)

    state.select(0)
    state.select(0)  # 同じ選択は再発火しない
    state.select(1)  # 単一選択は置換
    state.deselect()
    assert selections == [(0,), (1,), ()]


def test_toggle_adds_and_removes(dataset: StubDataset):
    state = ViewerState(dataset)
    selections: list[tuple[int, ...]] = []
    state.selectionChanged.connect(selections.append)

    state.toggle(0)
    state.toggle(1)  # 追加
    state.toggle(0)  # 解除
    assert state.selected_indices == (1,)
    assert selections == [(0,), (0, 1), (1,)]


def test_set_selection_replace_and_additive(dataset: StubDataset):
    state = ViewerState(dataset)
    state.set_selection([0])
    state.set_selection([1], additive=True)  # 和集合
    assert state.selected_indices == (0, 1)
    state.set_selection([1])  # 置換
    assert state.selected_indices == (1,)


def test_selection_ignores_out_of_range(dataset: StubDataset):
    state = ViewerState(dataset)
    state.select(0)
    state.select(99)  # 現在画像のアノテーション数を超える index -> 全解除
    assert state.selected_indices == ()

    state.set_selection([0, 99])  # 範囲外は無視
    assert state.selected_indices == (0,)

    state.toggle(99)  # 範囲外は無視(変化なし)
    assert state.selected_indices == (0,)


def test_toggles(dataset: StubDataset):
    state = ViewerState(dataset)
    overlay: list[bool] = []
    fill: list[bool] = []
    state.overlayVisibleChanged.connect(overlay.append)
    state.fillVisibleChanged.connect(fill.append)

    state.toggle_overlay()
    state.toggle_fill()
    state.toggle_fill()
    assert overlay == [False]
    assert fill == [False, True]
    assert state.overlay_visible is False
    assert state.fill_visible is True


def test_empty_dataset_is_safe():
    state = ViewerState(StubDataset())
    assert state.current_image() is None
    assert state.current_annotations() == []
    state.next_image()  # 何も起きない(例外にならない)
    state.select(0)
    assert state.selected_indices == ()
