"""画像ビューの四隅いずれかに常時浮かぶ操作バー。

用途は2つ:
- 左下「表示」: フィット・オーバーレイ表示・塗り表示(後ろ2つはトグルボタン)
- 右上: 前 / 次の画像送り

`FloatingActionBar` と同様に親ビューへ重ねて描画し、リサイズへの追従も自身で
行う。任意の見出し(カテゴリ名)を上に付けられる。外部との接点は `add_button` で
追加したボタンのシグナルのみで、レイアウトの都合をウィンドウ側へ漏らさない。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from annotate_tool import style


class FloatingControlBar(QWidget):
    """ビューの四隅いずれかに寄せて常時表示するボタン列。

    anchor は "top-left" / "top-right" / "bottom-left" / "bottom-right"。
    title を渡すとボタン列の上にカテゴリ見出しを表示する。
    """

    def __init__(
        self,
        view: QAbstractScrollArea,
        anchor: str = "top-left",
        title: str | None = None,
    ):
        super().__init__(view)
        vertical, horizontal = anchor.split("-")
        assert vertical in ("top", "bottom") and horizontal in ("left", "right")
        self._view = view
        self._vertical = vertical
        self._horizontal = horizontal

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        if title:
            label = QLabel(title, self)
            label.setStyleSheet(style.CONTROL_LABEL_QSS)
            outer.addWidget(label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(style.FLOATING_BUTTON_SPACING)
        outer.addLayout(row)
        self._row = row

        # ビューのリサイズに追従して位置を更新するため監視する
        view.installEventFilter(self)

    def add_button(self, text: str, slot, *, checkable: bool = False) -> QPushButton:
        """ボタンを1つ追加して返す。checkable=True でトグルボタンにする。"""
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない(奪うと一覧へフォーカスが移り自動選択が起きるため)。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(style.CONTROL_BUTTON_QSS)
        btn.setCheckable(checkable)
        btn.clicked.connect(slot)
        self._row.addWidget(btn)
        self.adjustSize()
        self._reposition()
        return btn

    def eventFilter(self, obj, event) -> bool:
        if obj is self._view and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reposition()
        self.raise_()

    def _reposition(self) -> None:
        if self._horizontal == "left":
            x = style.FLOATING_BUTTON_SIDE_MARGIN
        else:
            x = self._view.width() - self.width() - style.FLOATING_BUTTON_SIDE_MARGIN

        if self._vertical == "top":
            y = style.FLOATING_BUTTON_TOP_MARGIN
        else:
            y = self._view.height() - self.height() - style.FLOATING_BUTTON_BOTTOM_MARGIN

        self.move(max(0, x), max(0, y))
