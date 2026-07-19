"""アプリケーション状態の一元管理。

現在の画像・選択中インスタンス・表示フラグは、すべてこの ViewerState だけが
持つ(single source of truth)。ウィジェットは状態を保持せず、変更シグナルを
受けて表示を更新し、ユーザー操作は ViewerState のメソッド呼び出しに変換する。

これにより「ビューと一覧の選択がずれる」類のバグを構造的に防ぎ、
編集機能などを追加する際も状態の置き場所が明確になる。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from annotate_tool.coco_data import Annotation, CocoDataset, ImageEntry


class ViewerState(QObject):
    """ビューアの状態と、それを変更する操作(コマンド)を提供する。"""

    imageChanged = Signal(int)  # 現在画像の index(同じ画像の再読み込みでも発火)
    selectionChanged = Signal(int)  # 選択インスタンスの index、-1 は非選択
    overlayVisibleChanged = Signal(bool)
    fillVisibleChanged = Signal(bool)

    def __init__(self, dataset: CocoDataset, parent: QObject | None = None):
        super().__init__(parent)
        self._dataset = dataset
        self._image_index = 0
        self._selected = -1
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
    def selected_index(self) -> int:
        return self._selected

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
        had_selection = self._selected >= 0
        self._selected = -1
        self.imageChanged.emit(self._image_index)
        if had_selection:
            self.selectionChanged.emit(-1)

    def next_image(self) -> None:
        self.set_image_index(self._image_index + 1)

    def prev_image(self) -> None:
        self.set_image_index(self._image_index - 1)

    # --- 選択 ---------------------------------------------------------------
    def select(self, index: int) -> None:
        """インスタンスを選択する。-1 で選択解除。範囲外は解除扱い。"""
        if not (0 <= index < len(self.current_annotations())):
            index = -1
        if index == self._selected:
            return
        self._selected = index
        self.selectionChanged.emit(index)

    def deselect(self) -> None:
        self.select(-1)

    # --- 表示トグル -----------------------------------------------------------
    def toggle_overlay(self) -> None:
        self._overlay_visible = not self._overlay_visible
        self.overlayVisibleChanged.emit(self._overlay_visible)

    def toggle_fill(self) -> None:
        self._fill_visible = not self._fill_visible
        self.fillVisibleChanged.emit(self._fill_visible)
