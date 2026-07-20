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
    updated: list[Annotation] = field(default_factory=list)

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

    def update_annotation(
        self, ann: Annotation, segmentation: list[list[float]]
    ) -> None:
        ann.segmentation = segmentation
        self.updated.append(ann)

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


def test_toggle_blink(dataset: StubDataset):
    state = ViewerState(dataset)
    emitted: list[bool] = []
    state.blinkEnabledChanged.connect(emitted.append)

    assert state.blink_enabled is False  # 既定は OFF
    state.toggle_blink()
    state.toggle_blink()
    assert emitted == [True, False]
    assert state.blink_enabled is False


def test_empty_dataset_is_safe():
    state = ViewerState(StubDataset())
    assert state.current_image() is None
    assert state.current_annotations() == []
    state.next_image()  # 何も起きない(例外にならない)
    state.select(0)
    assert state.selected_indices == ()


# --- 塗りつぶし編集モード(新規追加 / 既存修正)-------------------------------
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


def test_apply_painted_adds_to_memory_and_requests_save(dataset: StubDataset):
    state = ViewerState(dataset)
    refreshed: list[int] = []
    save_reqs: list[int] = []
    state.annotationsChanged.connect(lambda: refreshed.append(1))
    state.saveRequested.connect(lambda: save_reqs.append(1))

    polygons = [[0, 0, 10, 0, 10, 10, 0, 10]]
    ok = state.apply_painted(polygons)
    assert ok is True
    assert len(dataset.added) == 1
    assert dataset.added[0].image_id == 1
    assert dataset.added[0].segmentation == polygons
    assert refreshed == [1]
    assert save_reqs == [1]  # 保存は要求されるが
    assert dataset.saved is False  # まだディスクへは書かない(遅延)

    # flush_save で初めてディスク保存が走る
    state.flush_save()
    assert dataset.saved is True


def test_apply_painted_ignores_empty(dataset: StubDataset):
    state = ViewerState(dataset)
    save_reqs: list[int] = []
    state.saveRequested.connect(lambda: save_reqs.append(1))
    assert state.apply_painted([]) is False
    assert dataset.saved is False
    assert dataset.added == []
    assert save_reqs == []


# --- 修正(既存インスタンスの塗り直し)----------------------------------------
def test_enter_edit_mode_tracks_target_and_clears_selection(dataset: StubDataset):
    state = ViewerState(dataset)
    selections: list[tuple] = []
    state.selectionChanged.connect(selections.append)

    state.select(1)
    state.enter_edit_mode(1)
    assert state.add_mode is True
    assert state.edit_index == 1
    assert state.editing_annotation() is dataset.anns[1][1]
    assert state.selected_indices == ()  # 編集中は選択を外す
    assert selections[-1] == ()


def test_enter_edit_mode_ignores_invalid_index(dataset: StubDataset):
    state = ViewerState(dataset)
    state.enter_edit_mode(99)
    assert state.add_mode is False
    assert state.edit_index is None


def test_cancel_edit_mode_restores_selection(dataset: StubDataset):
    state = ViewerState(dataset)
    state.enter_edit_mode(1)
    state.cancel_add_mode()
    assert state.add_mode is False
    assert state.edit_index is None
    assert state.selected_indices == (1,)  # 修正をやめたら元の選択へ戻る


def test_apply_painted_replaces_shape_when_editing(dataset: StubDataset):
    state = ViewerState(dataset)
    target = dataset.anns[1][1]
    state.enter_edit_mode(1)

    polygons = [[0, 0, 5, 0, 5, 5, 0, 5]]
    assert state.apply_painted(polygons) is True
    assert dataset.updated == [target]  # 差し替えであって
    assert dataset.added == []  # 新規追加ではない
    assert target.segmentation == polygons


def test_apply_painted_adds_new_after_leaving_edit_mode(dataset: StubDataset):
    """修正を抜けた後の確定は、また新規追加に戻る。"""
    state = ViewerState(dataset)
    state.enter_edit_mode(1)
    state.cancel_add_mode()

    state.enter_add_mode()
    assert state.edit_index is None
    assert state.apply_painted([[0, 0, 1, 0, 1, 1]]) is True
    assert len(dataset.added) == 1
    assert dataset.updated == []


# --- 面積によるしきい値選択 ---------------------------------------------------
def area_ann(ann_id: int, image_id: int, area: float) -> Annotation:
    return Annotation(
        id=ann_id, image_id=image_id, category_id=1, segmentation=[], area=area
    )


@pytest.fixture
def area_dataset() -> StubDataset:
    """面積がばらばらで、index 順と面積順が一致しないデータ。"""
    return StubDataset(
        images=[
            ImageEntry(id=1, file_name="a.jpg", width=10, height=10),
            ImageEntry(id=2, file_name="b.jpg", width=10, height=10),
        ],
        anns={
            1: [
                area_ann(10, 1, 500.0),  # index 0
                area_ann(11, 1, 20.0),  # index 1
                area_ann(12, 1, 100.0),  # index 2
                area_ann(13, 1, 20.0),  # index 3(同点)
            ],
            2: [area_ann(20, 2, 9999.0)],
        },
    )


def test_area_threshold_selects_small_instances(area_dataset: StubDataset):
    state = ViewerState(area_dataset)
    assert sorted(state.indices_with_area_at_most(0)) == []
    assert sorted(state.indices_with_area_at_most(20)) == [1, 3]  # 境界は含む
    assert sorted(state.indices_with_area_at_most(100)) == [1, 2, 3]
    assert sorted(state.indices_with_area_at_most(10_000)) == [0, 1, 2, 3]


def test_area_threshold_feeds_normal_selection(area_dataset: StubDataset):
    """しきい値選択の結果は普通の複数選択であり、後から手で編集できる。"""
    state = ViewerState(area_dataset)
    state.set_selection(state.indices_with_area_at_most(100))
    assert state.selected_indices == (1, 2, 3)

    state.toggle(2)  # 手で1件外す
    assert state.selected_indices == (1, 3)

    state.deselect()
    assert state.selected_indices == ()


def test_area_index_follows_image_change(area_dataset: StubDataset):
    """画像を切り替えたら面積索引も作り直される(前の画像の索引が残らない)。"""
    state = ViewerState(area_dataset)
    assert sorted(state.indices_with_area_at_most(100)) == [1, 2, 3]

    state.set_image_index(1)
    assert state.indices_with_area_at_most(100) == []
    assert state.indices_with_area_at_most(9999) == [0]


def test_area_index_follows_deletion(area_dataset: StubDataset):
    """削除後の索引は、詰め直された index を返す。"""
    state = ViewerState(area_dataset)
    state.set_selection([0])  # area 500 のものを消す
    state.delete_selected()

    # 残りは [20, 100, 20] -> index 0, 1, 2
    assert sorted(state.indices_with_area_at_most(20)) == [0, 2]
    assert sorted(state.indices_with_area_at_most(500)) == [0, 1, 2]
