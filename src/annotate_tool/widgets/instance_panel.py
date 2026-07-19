"""インスタンス一覧を表示するドックパネル。

QListWidget のシグナル抑止(blockSignals)による同期処理はこのクラス内に
閉じ込める。外部とのやり取りは set_annotations / set_selection と
selectionChanged シグナルのみ。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
)

from annotate_tool import style
from annotate_tool.coco_data import Annotation


class InstancePanel(QDockWidget):
    """インスタンス一覧。選択行の変更を selectionChanged(index のリスト) で通知する。"""

    selectionChanged = Signal(object)  # 選択行 index のリスト(空リストで解除)

    def __init__(self, parent=None):
        super().__init__("インスタンス一覧", parent)
        self._list = QListWidget(self)
        self._list.setUniformItemSizes(True)
        # Ctrl/Shift で一覧からも複数選択できるようにする
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.itemSelectionChanged.connect(self._emit_selection)

        self.setWidget(self._list)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )
        self.setMinimumWidth(style.DOCK_MIN_WIDTH)

    def set_annotations(
        self,
        annotations: list[Annotation],
        category_name: Callable[[int], str],
    ) -> None:
        """一覧を作り直す。選択は解除された状態になる(シグナルは出さない)。"""
        self._list.blockSignals(True)
        self._list.clear()
        for idx, ann in enumerate(annotations):
            label = f"#{ann.id}  {category_name(ann.category_id)}"
            if ann.area:
                label += f"  (area {int(ann.area)})"
            item = QListWidgetItem(style.color_icon(style.instance_color(idx)), label)
            item.setData(Qt.UserRole, idx)
            self._list.addItem(item)
        self._list.clearSelection()
        self._list.setCurrentRow(-1)
        self._list.blockSignals(False)

    def set_selection(self, indices) -> None:
        """外部からの選択状態の反映。selectionChanged は発火させない。"""
        wanted = set(indices)
        if wanted == self._selected_rows():
            return
        self._list.blockSignals(True)
        self._list.clearSelection()
        for row in wanted:
            item = self._list.item(row)
            if item is not None:
                item.setSelected(True)
        # 代表行(currentItem)も選択内に置く。空なら解除。
        self._list.setCurrentRow(min(wanted) if wanted else -1)
        self._list.blockSignals(False)

    def _selected_rows(self) -> set[int]:
        return {item.data(Qt.UserRole) for item in self._list.selectedItems()}

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(sorted(self._selected_rows()))
