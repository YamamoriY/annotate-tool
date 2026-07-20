"""画像ビュー上部中央に浮かぶ、追加モード用のボタン。

状態に応じて表示を切り替える:
- 通常時(未選択): 「追加」
- 追加モード中: 「キャンセル (Esc)」。塗り始めた後は「確定 (Enter)」も並ぶ。

`FloatingActionBar` と同様に親ビューへ重ね、リサイズ追従も自身で行う。外部との
接点は addClicked / cancelClicked / confirmClicked と
show_add / show_adding / hide_all のみ。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QAbstractScrollArea, QHBoxLayout, QPushButton, QWidget

from annotate_tool import style


class AddBar(QWidget):
    """追加モードの入口(追加)と確定ボタンをまとめた浮動バー。"""

    addClicked = Signal()
    cancelClicked = Signal()
    confirmClicked = Signal()

    def __init__(self, view: QAbstractScrollArea):
        super().__init__(view)
        self._view = view

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(style.FLOATING_BUTTON_SPACING)

        self._add_btn = self._make_button(
            "＋ 追加 (A)", style.ADD_BUTTON_QSS, self.addClicked
        )
        self._cancel_btn = self._make_button(
            "✕ キャンセル (Esc)", style.CANCEL_BUTTON_QSS, self.cancelClicked
        )
        self._confirm_btn = self._make_button(
            "✓ 確定 (Enter)", style.CONFIRM_BUTTON_QSS, self.confirmClicked
        )
        layout.addWidget(self._add_btn)
        layout.addWidget(self._cancel_btn)
        layout.addWidget(self._confirm_btn)

        for btn in (self._add_btn, self._cancel_btn, self._confirm_btn):
            btn.hide()
        self.hide()

        view.installEventFilter(self)

    def _make_button(self, text: str, qss: str, signal: Signal) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない(奪うと一覧へフォーカスが移り自動選択が起きるため)。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(qss)
        btn.clicked.connect(signal)
        return btn

    # --- 表示制御 -----------------------------------------------------------
    def show_add(self) -> None:
        self._show_only(self._add_btn)

    def show_adding(self, can_confirm: bool) -> None:
        """追加モード中の表示。キャンセルは常に出し、確定は塗った後だけ出す。"""
        buttons = [self._cancel_btn]
        if can_confirm:
            buttons.append(self._confirm_btn)
        self._show_only(*buttons)

    def hide_all(self) -> None:
        self.hide()
        self._view.viewport().update()  # 残像を消す

    def _show_only(self, *buttons: QPushButton) -> None:
        for btn in (self._add_btn, self._cancel_btn, self._confirm_btn):
            btn.setVisible(btn in buttons)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

    # --- 位置追従 -----------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self._view and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _reposition(self) -> None:
        x = (self._view.width() - self.width()) // 2
        self.move(max(0, x), style.FLOATING_BUTTON_TOP_MARGIN)
