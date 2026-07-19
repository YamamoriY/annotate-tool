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
    saved: bool = False
    added: list[Annotation] = field(default_factory=list)

    def annotations_for(self, image_id: int) -> list[Annotation]:
        return self.anns.get(image_id, [])

    def delete_annotations(self, annotations: list[Annotation]) -> None:
        targets = {id(a) for a in annotations}
        for image_id, lst in self.anns.items():
            self.anns[image_id] = [a for a in lst if id(a) not in targets]

    def add_annotation(
        self,
        image_id: int,
        segmentation: list[list[float]],
        category_id: int | None = None,
    ) -> Annotation:
        ann = Annotation(
            id=100 + len(self.added),
            image_id=image_id,
            category_id=category_id or 1,
            segmentation=segmentation,
        )
        self.anns.setdefault(image_id, []).append(ann)
        self.added.append(ann)
        return ann

    def save(self) -> None:
        self.saved = True


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


def test_delete_selected_removes_saves_and_clears(dataset: StubDataset):
    state = ViewerState(dataset)
    ann_changes: list[bool] = []
    selections: list[tuple[int, ...]] = []
    state.annotationsChanged.connect(lambda: ann_changes.append(True))
    state.selectionChanged.connect(selections.append)

    state.set_selection([0])  # 現在画像の先頭(ann id 10)を選択
    state.delete_selected()

    assert [a.id for a in state.current_annotations()] == [11]
    assert state.selected_indices == ()
    assert dataset.saved is True
    assert ann_changes == [True]
    assert selections[-1] == ()  # 削除後に選択解除が通知される


def test_delete_selected_noop_when_empty(dataset: StubDataset):
    state = ViewerState(dataset)
    ann_changes: list[bool] = []
    state.annotationsChanged.connect(lambda: ann_changes.append(True))

    state.delete_selected()  # 選択なし

    assert ann_changes == []
    assert dataset.saved is False
    assert [a.id for a in state.current_annotations()] == [10, 11]


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


# --- 追加(塗りつぶし)モード -----------------------------------------------
def test_enter_and_cancel_add_mode(dataset: StubDataset):
    state = ViewerState(dataset)
    changes: list[bool] = []
    state.addModeChanged.connect(changes.append)

    assert state.add_mode is False
    state.enter_add_mode()
    assert state.add_mode is True
    state.enter_add_mode()  # 二重呼び出しは無視される
    state.cancel_add_mode()
    assert state.add_mode is False
    state.cancel_add_mode()  # 二重呼び出しは無視される
    assert changes == [True, False]


def test_enter_add_mode_clears_selection(dataset: StubDataset):
    state = ViewerState(dataset)
    selections: list[tuple] = []
    state.selectionChanged.connect(selections.append)

    state.set_selection([0, 1])
    assert state.selected_indices == (0, 1)
    state.enter_add_mode()
    assert state.selected_indices == ()
    assert selections[-1] == ()  # 選択解除が通知される


def test_add_painted_adds_annotation_and_saves(dataset: StubDataset):
    state = ViewerState(dataset)
    refreshed: list[int] = []
    state.annotationsChanged.connect(lambda: refreshed.append(1))

    polygons = [[0, 0, 10, 0, 10, 10, 0, 10]]
    ok = state.add_painted(polygons)
    assert ok is True
    assert dataset.saved is True
    assert len(dataset.added) == 1
    assert dataset.added[0].image_id == 1
    assert dataset.added[0].segmentation == polygons
    assert refreshed == [1]


def test_add_painted_ignores_empty(dataset: StubDataset):
    state = ViewerState(dataset)
    assert state.add_painted([]) is False
    assert dataset.saved is False
    assert dataset.added == []
