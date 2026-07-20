"""画像ビュー左上に浮かぶ、追加モード用のツールパネル。

    [ブラシ ]  [====○==  12]
    [消しゴム]  [==○====  16]

ボタンは排他トグル(常にどちらか一方が ON)、右のスライダーはそのツールの太さ。
太さはツールごとに独立して保持する。`FloatingActionBar` と同様に親ビューへ重ね、
リサイズ追従も自身で行う。外部との接点は toolChanged / radiusChanged と
set_active のみ。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QButtonGroup,
    QGridLayout,
    QPushButton,
    QWidget,
)

from annotate_tool import style
from annotate_tool.tools import Tool
from annotate_tool.widgets.brush_slider import BrushSlider


class ToolPanel(QWidget):
    """ツール選択(トグル)と太さスライダーを行ごとに並べた浮動パネル。"""

    toolChanged = Signal(object)  # Tool
    radiusChanged = Signal(object, float)  # (Tool, 半径)

    def __init__(self, view: QAbstractScrollArea):
        super().__init__(view)
        self._view = view
        # ビューのブラシ円カーソルを継承しないよう、パネル上は通常の矢印に戻す。
        self.setCursor(Qt.ArrowCursor)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(style.FLOATING_BUTTON_SPACING)
        layout.setVerticalSpacing(style.FLOATING_BUTTON_SPACING)

        # 排他トグル。Qt に排他を任せ、どちらか一方が必ず ON の状態を保つ。
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[Tool, QPushButton] = {}
        self._sliders: dict[Tool, BrushSlider] = {}

        rows = (
            (Tool.BRUSH, "🖌 ブラシ", style.BRUSH_RADIUS),
            (Tool.ERASER, "🧽 消しゴム", style.ERASER_RADIUS),
        )
        for row, (tool, text, radius) in enumerate(rows):
            button = self._make_button(text, tool)
            slider = BrushSlider(radius, self)
            slider.radiusChanged.connect(
                lambda r, t=tool: self.radiusChanged.emit(t, r)
            )
            layout.addWidget(button, row, 0)
            layout.addWidget(slider, row, 1)
            self._buttons[tool] = button
            self._sliders[tool] = slider

        self._buttons[Tool.BRUSH].setChecked(True)
        self.adjustSize()
        self.hide()

        view.installEventFilter(self)

    def _make_button(self, text: str, tool: Tool) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        # 他の浮動ボタンと同様、フォーカスを奪わせない(一覧の自動選択を防ぐ)。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedWidth(style.TOOL_BUTTON_WIDTH)
        btn.setStyleSheet(style.TOOL_BUTTON_QSS)
        btn.clicked.connect(lambda _checked, t=tool: self.toolChanged.emit(t))
        self._group.addButton(btn)
        return btn

    # --- 値 -----------------------------------------------------------------
    def tool(self) -> Tool:
        for tool, btn in self._buttons.items():
            if btn.isChecked():
                return tool
        return Tool.BRUSH

    def radius(self, tool: Tool) -> float:
        return self._sliders[tool].radius()

    def set_tool(self, tool: Tool) -> None:
        """外部からツールを切り替える(シグナルは出さない)。"""
        self._buttons[tool].setChecked(True)

    # --- 表示制御 -----------------------------------------------------------
    def set_active(self, active: bool) -> None:
        """追加モード中だけ表示する。"""
        if active:
            self.adjustSize()
            self._reposition()
            self.show()
            self.raise_()
        else:
            self.hide()
            # QGraphicsView のビューポートは自動再描画されないため残像を消す。
            self._view.viewport().update()

    # --- 位置追従 -----------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self._view and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _reposition(self) -> None:
        # 上端は中央の浮動バーと高さを揃える。
        self.move(style.FLOATING_BUTTON_SIDE_MARGIN, style.FLOATING_BUTTON_TOP_MARGIN)
