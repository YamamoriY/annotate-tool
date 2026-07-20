"""画像エリア右側の作業用サイドパネル(ドック)。

現状は将来の UI を置くための余白(プレースホルダ)。左のインスタンス一覧と
同じ幅を確保する。中身は `add_widget` で上から積み増せる。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from annotate_tool import style
from annotate_tool.widgets.control_group import make_control_button


class SidePanel(QDockWidget):
    """右側に固定幅で置く作業用パネル。中身は後から追加する。"""

    def __init__(self, title: str = "パネル", parent=None):
        super().__init__(title, parent)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addStretch(1)  # 追加ウィジェットは上詰めにする
        self._layout = layout

        self.setWidget(container)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )
        self.setMinimumWidth(style.DOCK_MIN_WIDTH)

    def add_button_row(self, specs: Iterable[tuple[str, object]]) -> list[QPushButton]:
        """(text, slot) の並びを横1行に均等配置して、パネルへ直接置く。

        見出しを付けるほどでもない操作(画像送りなど)向け。ControlGroup を使うと
        枠と見出しが付いてしまうため、ここでは素のまま置く。
        """
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(style.FLOATING_BUTTON_SPACING)
        buttons = []
        for text, slot in specs:
            btn = make_control_button(text, slot, row)
            layout.addWidget(btn)
            buttons.append(btn)
        self.add_widget(row)
        return buttons

    def add_widget(self, widget: QWidget) -> None:
        """パネルの内容を上から順に追加する(末尾の伸縮スペースの手前へ挿入)。"""
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def add_widget_bottom(self, widget: QWidget) -> None:
        """伸縮スペースの後ろへ追加する(パネル下端に貼り付ける)。"""
        self._layout.addWidget(widget)
