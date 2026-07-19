"""インスタンス一覧を表示するドックパネル。

QListWidget のシグナル抑止(blockSignals)による同期処理はこのクラス内に
閉じ込める。外部とのやり取りは set_annotations / set_selected と
selectionChanged シグナルのみ。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem

from annotate_tool import style
from annotate_tool.coco_data import Annotation


class InstancePanel(QDockWidget):
    """インスタンス一覧。行の選択変更を selectionChanged(-1 で解除) で通知する。"""

    selectionChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__("インスタンス一覧", parent)
        self._list = QListWidget(self)
        self._list.setUniformItemSizes(True)
        self._list.currentRowChanged.connect(self.selectionChanged)

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
        self._list.setCurrentRow(-1)
        self._list.blockSignals(False)

    def set_selected(self, index: int) -> None:
        """外部からの選択状態の反映。selectionChanged は発火させない。"""
        if index == self._list.currentRow():
            return
        self._list.blockSignals(True)
        self._list.setCurrentRow(index)
        if index < 0:
            self._list.clearSelection()
        self._list.blockSignals(False)
