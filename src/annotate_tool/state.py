"""アプリケーション状態の一元管理。

現在の画像・選択中インスタンス・表示フラグは、すべてこの ViewerState だけが
持つ(single source of truth)。ウィジェットは状態を保持せず、変更シグナルを
受けて表示を更新し、ユーザー操作は ViewerState のメソッド呼び出しに変換する。

これにより「ビューと一覧の選択がずれる」類のバグを構造的に防ぎ、
編集機能などを追加する際も状態の置き場所が明確になる。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QObject, Signal

from annotate_tool.coco_data import Annotation, CocoDataset, ImageEntry


class ViewerState(QObject):
    """ビューアの状態と、それを変更する操作(コマンド)を提供する。"""

    imageChanged = Signal(int)  # 現在画像の index(同じ画像の再読み込みでも発火)
    # 選択インスタンスの index 集合(ソート済み tuple)。非選択は空 tuple。
    selectionChanged = Signal(object)
    # 現在画像のアノテーション集合が変化した(削除など。画像自体は再読込しない)
    annotationsChanged = Signal()
    overlayVisibleChanged = Signal(bool)
    fillVisibleChanged = Signal(bool)

    def __init__(self, dataset: CocoDataset, parent: QObject | None = None):
        super().__init__(parent)
        self._dataset = dataset
        self._image_index = 0
        self._selected: set[int] = set()
        self._overlay_visible = True
        self._fill_visible = True

    # --- 参照系 -------------------------------------------------------------
    @property
    def dataset(self) -> CocoDataset:
        return self._dataset

    @property
    def image_index(self) -> int:
        return self._image_index

    @property
    def selected_indices(self) -> tuple[int, ...]:
        return tuple(sorted(self._selected))

    def is_selected(self, index: int) -> bool:
        return index in self._selected

    @property
    def overlay_visible(self) -> bool:
        return self._overlay_visible

    @property
    def fill_visible(self) -> bool:
        return self._fill_visible

    def current_image(self) -> ImageEntry | None:
        if not self._dataset.images:
            return None
        return self._dataset.images[self._image_index]

    def current_annotations(self) -> list[Annotation]:
        image = self.current_image()
        if image is None:
            return []
        return self._dataset.annotations_for(image.id)

    # --- 画像ナビゲーション ---------------------------------------------------
    def set_image_index(self, index: int) -> None:
        """画像を切り替える。切り替え時に選択は解除される。"""
        if not self._dataset.images:
            return
        self._image_index = index % len(self._dataset.images)
        had_selection = bool(self._selected)
        self._selected = set()
        self.imageChanged.emit(self._image_index)
        if had_selection:
            self.selectionChanged.emit(())

    def next_image(self) -> None:
        self.set_image_index(self._image_index + 1)

    def prev_image(self) -> None:
        self.set_image_index(self._image_index - 1)

    # --- 選択 ---------------------------------------------------------------
    def _valid(self, index: int) -> bool:
        return 0 <= index < len(self.current_annotations())

    def _apply(self, selection: set[int]) -> None:
        """選択集合を差し替え、変化があればシグナルを出す。"""
        if selection == self._selected:
            return
        self._selected = selection
        self.selectionChanged.emit(tuple(sorted(selection)))

    def select(self, index: int) -> None:
        """その1件だけを選択(置換)。範囲外/-1 は全解除。"""
        self._apply({index} if self._valid(index) else set())

    def toggle(self, index: int) -> None:
        """指定インスタンスを選択に追加、既に選択済みなら解除する。"""
        if not self._valid(index):
            return
        selection = set(self._selected)
        selection.discard(index) if index in selection else selection.add(index)
        self._apply(selection)

    def set_selection(self, indices: Iterable[int], additive: bool = False) -> None:
        """複数インスタンスを選択する。additive=False は置換、True は和集合。"""
        chosen = {i for i in indices if self._valid(i)}
        self._apply((self._selected | chosen) if additive else chosen)

    def deselect(self) -> None:
        self._apply(set())

    # --- 編集 ---------------------------------------------------------------
    def delete_selected(self) -> None:
        """選択中のインスタンスを削除し、JSON へ保存する。

        削除後は選択を解除し、annotationsChanged(表示の作り直し)と
        selectionChanged(選択解除)を通知する。選択が空なら何もしない。
        """
        current = self.current_annotations()
        targets = [current[i] for i in sorted(self._selected) if self._valid(i)]
        if not targets:
            return
        self._dataset.delete_annotations(targets)
        self._dataset.save()
        self._selected = set()
        self.annotationsChanged.emit()
        self.selectionChanged.emit(())

    # --- 表示トグル -----------------------------------------------------------
    def toggle_overlay(self) -> None:
        self._overlay_visible = not self._overlay_visible
        self.overlayVisibleChanged.emit(self._overlay_visible)

    def toggle_fill(self) -> None:
        self._fill_visible = not self._fill_visible
        self.fillVisibleChanged.emit(self._fill_visible)
