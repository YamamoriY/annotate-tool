"""筆・消しゴムの太さ(半径)を変えるスライダー。

追加モード中だけ `ToolPanel` の各行に並べて表示する。値は画像=シーン座標の
半径 px で、整数刻み(style.BRUSH_RADIUS_MIN..MAX)。外部との接点は
radiusChanged と radius / set_radius のみ。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from annotate_tool import style


class BrushSlider(QWidget):
    """半径のスライダー(つまみ + 現在値)。"""

    radiusChanged = Signal(float)

    def __init__(self, value: float = style.BRUSH_RADIUS, parent=None):
        super().__init__(parent)
        self.setStyleSheet(style.BRUSH_SLIDER_QSS)
        # 追加モード中はビューがブラシ円カーソルを持つ。子ウィジェットはそれを
        # 継承してしまうので、このバーの上では通常の矢印に戻す(子も継承する)。
        self.setCursor(Qt.ArrowCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setRange(
            int(style.BRUSH_RADIUS_MIN), int(style.BRUSH_RADIUS_MAX)
        )
        self._slider.setValue(int(value))
        self._slider.setFixedWidth(style.BRUSH_SLIDER_WIDTH)
        # ボタン類と同じく、フォーカスを奪うと一覧へ移って自動選択が起きるため防ぐ。
        self._slider.setFocusPolicy(Qt.NoFocus)
        self._slider.valueChanged.connect(self._on_value_changed)

        self._value_label = QLabel(str(self._slider.value()), self)
        # 桁が変わっても幅が動かないよう、最大値の桁で固定する。
        self._value_label.setFixedWidth(
            len(str(int(style.BRUSH_RADIUS_MAX))) * 9
        )
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)

    # --- 値 -----------------------------------------------------------------
    def radius(self) -> float:
        return float(self._slider.value())

    def set_radius(self, radius: float) -> None:
        self._slider.setValue(int(round(radius)))

    def _on_value_changed(self, value: int) -> None:
        self._value_label.setText(str(value))
        self.radiusChanged.emit(float(value))
