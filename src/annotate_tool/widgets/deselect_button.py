"""画像ビューの上部中央に浮かぶ「選択解除」ボタン。

親ビューのリサイズへの追従(イベントフィルタ)も自身で行い、
ウィンドウ側にはレイアウトの都合を漏らさない。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QPushButton

from annotate_tool import style


class DeselectButton(QPushButton):
    """選択中のみ表示するオーバーレイボタン。"""

    def __init__(self, view: QAbstractScrollArea):
        super().__init__("✕ 選択解除 (Esc)", view)
        self._view = view

        self.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない。奪うと非表示化でフォーカスが一覧へ移り、
        # 空選択の QListWidget が先頭行を自動選択してしまうため。
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(style.DESELECT_BUTTON_QSS)
        self.adjustSize()
        self.hide()

        # ビューのリサイズに追従して位置を更新するため監視する
        view.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._view and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def set_active(self, active: bool) -> None:
        """選択状態に応じて表示/非表示を切り替える。"""
        if active:
            self.adjustSize()
            self._reposition()
            self.show()
            self.raise_()
        else:
            self.hide()
            # QGraphicsView のビューポートは自動では再描画されず残像が残るため、
            # 明示的に更新してボタンを確実に消す。
            self._view.viewport().update()

    def _reposition(self) -> None:
        x = (self._view.width() - self.width()) // 2
        self.move(max(0, x), style.FLOATING_BUTTON_TOP_MARGIN)
