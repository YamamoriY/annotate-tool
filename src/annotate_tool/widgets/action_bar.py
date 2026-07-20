"""画像ビューの上部中央に浮かぶアクションバー。

選択中だけ表示し、「選択解除」「修正」「削除」を横並びに並べる。「修正」は形を
塗り直せる単一選択のときだけ出す。親ビューのリサイズへの追従(イベントフィルタ)も
自身で行い、ウィンドウ側にはレイアウトの都合を漏らさない。外部との接点は
deselectClicked / editClicked / deleteClicked シグナルと set_active のみ。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QAbstractScrollArea, QHBoxLayout, QPushButton, QWidget

from annotate_tool import shortcuts, style


class FloatingActionBar(QWidget):
    """選択中のみ表示するオーバーレイのボタン列。"""

    deselectClicked = Signal()
    editClicked = Signal()
    deleteClicked = Signal()

    def __init__(self, view: QAbstractScrollArea):
        super().__init__(view)
        self._view = view

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(style.FLOATING_BUTTON_SPACING)

        self._deselect_btn = self._make_button(
            shortcuts.ESCAPE.text("✕"), style.DESELECT_BUTTON_QSS, self.deselectClicked
        )
        self._edit_btn = self._make_button(
            shortcuts.EDIT.text("✎"), style.ADD_BUTTON_QSS, self.editClicked
        )
        self._delete_btn = self._make_button(
            shortcuts.DELETE.text("🗑"), style.DELETE_BUTTON_QSS, self.deleteClicked
        )
        layout.addWidget(self._deselect_btn)
        layout.addWidget(self._edit_btn)
        layout.addWidget(self._delete_btn)

        self.adjustSize()
        self.hide()

        # ビューのリサイズに追従して位置を更新するため監視する
        view.installEventFilter(self)

    def _make_button(self, text: str, qss: str, signal: Signal) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない。奪うと非表示化でフォーカスが一覧へ移り、
        # 空選択の QListWidget が先頭行を自動選択してしまうため。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(qss)
        btn.clicked.connect(signal)
        return btn

    def eventFilter(self, obj, event) -> bool:
        if obj is self._view and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def set_active(self, active: bool, can_edit: bool = False) -> None:
        """選択状態に応じて表示/非表示を切り替える。

        can_edit(単一選択)のときだけ「修正」を出す。複数選択では、どれを塗り
        直すのか決まらないため隠す。
        """
        if active:
            self._edit_btn.setVisible(can_edit)
            self.adjustSize()
            self._reposition()
            self.show()
            self.raise_()
        else:
            self.hide()
            # QGraphicsView のビューポートは自動では再描画されず残像が残るため、
            # 明示的に更新してバーを確実に消す。
            self._view.viewport().update()

    def _reposition(self) -> None:
        x = (self._view.width() - self.width()) // 2
        self.move(max(0, x), style.FLOATING_BUTTON_TOP_MARGIN)
