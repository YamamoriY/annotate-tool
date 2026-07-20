"""サイドパネル内に置く、枠 + 半透明背景でまとめたボタングループ。

見出し(カテゴリ名)の下にボタンを積む。ボタンは縦積み(`add_button`)と
横並び1行(`add_row`)のどちらでも追加できる。外部との接点は追加したボタンの
シグナルのみ。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from annotate_tool import style


class ControlGroup(QWidget):
    """見出し付きのボタングループ(枠 + 半透明背景)。"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("controlGroup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.CONTROL_GROUP_QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        label = QLabel(title, self)
        label.setStyleSheet(style.CONTROL_LABEL_QSS)
        outer.addWidget(label)
        self._outer = outer

    def add_button(self, text: str, slot, *, checkable: bool = False) -> QPushButton:
        """ボタンを1つ、縦に積んで追加する。checkable=True でトグルボタン。"""
        btn = self._make_button(text, slot, checkable)
        self._outer.addWidget(btn)
        return btn

    def add_row(self, specs: Iterable[tuple[str, object]]) -> list[QPushButton]:
        """(text, slot) の並びを横1行に均等配置して追加する。"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(style.FLOATING_BUTTON_SPACING)
        buttons = []
        for text, slot in specs:
            btn = self._make_button(text, slot, False)
            row.addWidget(btn)
            buttons.append(btn)
        self._outer.addLayout(row)
        return buttons

    def add_text(self, text: str) -> QLabel:
        """説明用のテキスト行を追加する(操作方法の案内などに使う)。"""
        label = QLabel(text, self)
        label.setStyleSheet(style.CONTROL_HELP_QSS)
        label.setWordWrap(True)
        self._outer.addWidget(label)
        return label

    def add_checkbox(self, text: str, *, checked: bool = False) -> QCheckBox:
        """オン/オフの設定行を追加する(状態は返り値の isChecked() で読む)。"""
        box = QCheckBox(text, self)
        box.setCursor(Qt.PointingHandCursor)
        # ボタン同様、フォーカスを奪うと一覧側で自動選択が起きるため受け取らない。
        box.setFocusPolicy(Qt.NoFocus)
        box.setStyleSheet(style.CONTROL_CHECK_QSS)
        box.setChecked(checked)
        self._outer.addWidget(box)
        return box

    def _make_button(self, text: str, slot, checkable: bool) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない(奪うと一覧へフォーカスが移り自動選択が起きるため)。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(style.CONTROL_BUTTON_QSS)
        btn.setCheckable(checkable)
        btn.clicked.connect(slot)
        return btn
