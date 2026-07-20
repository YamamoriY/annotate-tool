"""画像ビュー上部中央に浮かぶ、追加モード用のボタン。

状態に応じて表示を切り替える:
- 通常時(未選択): 「追加」
- 追加モード中: 「キャンセル (Esc)」。塗り始めた後は「確定 (Enter)」も並ぶ。

ツールの選択と太さは左上の `ToolPanel` が受け持つ(ここはアクションのみ)。
`FloatingActionBar` と同様に親ビューへ重ね、リサイズ追従も自身で行う。外部との
接点は addClicked / cancelClicked / confirmClicked と
show_add / show_adding / hide_all のみ。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QAbstractScrollArea, QHBoxLayout, QPushButton, QWidget

from annotate_tool import shortcuts, style


class AddBar(QWidget):
    """追加モードの入口(追加)・キャンセル・確定をまとめた浮動バー。"""

    addClicked = Signal()
    cancelClicked = Signal()
    confirmClicked = Signal()

    def __init__(self, view: QAbstractScrollArea, keymap: shortcuts.Keymap):
        super().__init__(view)
        self._view = view

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(style.FLOATING_BUTTON_SPACING)

        self._add_btn = self._make_button(
            keymap.text(shortcuts.ADD, "＋"), style.ADD_BUTTON_QSS, self.addClicked
        )
        # Esc は通常時の「選択解除」と同じキー。追加モード中は言葉だけ変える。
        self._cancel_btn = self._make_button(
            keymap.text(shortcuts.ESCAPE, "✕", label="キャンセル"),
            style.CANCEL_BUTTON_QSS,
            self.cancelClicked,
        )
        self._confirm_btn = self._make_button(
            keymap.text(shortcuts.CONFIRM, "✓"),
            style.CONFIRM_BUTTON_QSS,
            self.confirmClicked,
        )
        # 表示順: 追加 / キャンセル / 確定(同時に出るのは後ろ2つだけ)
        self._widgets = (self._add_btn, self._cancel_btn, self._confirm_btn)
        for w in self._widgets:
            layout.addWidget(w)
            w.hide()
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
        """追加モード中の表示。キャンセルは常に出し、確定は塗った後だけ。"""
        shown = [self._cancel_btn]
        if can_confirm:
            shown.append(self._confirm_btn)
        self._show_only(*shown)

    def hide_all(self) -> None:
        self.hide()
        self._view.viewport().update()  # 残像を消す

    def _show_only(self, *shown: QWidget) -> None:
        for w in self._widgets:
            w.setVisible(w in shown)
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
