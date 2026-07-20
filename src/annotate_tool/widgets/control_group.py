"""サイドパネル内に置く、枠 + 半透明背景でまとめたボタングループ。

見出し(カテゴリ名)の下にボタンを積む。ボタンは縦積み(`add_button`)と
横並び1行(`add_row`)のどちらでも追加できる。外部との接点は追加したボタンの
シグナルのみ。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
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

    def add_widget(self, widget: QWidget) -> None:
        """任意のウィジェットを1つ、縦に積んで追加する。

        用意された行(ボタン・説明・スライダー)に当てはまらないものを置くための口。
        """
        widget.setParent(self)
        self._outer.addWidget(widget)

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

    def add_slider(
        self,
        *,
        minimum: int,
        maximum: int,
        value: int,
        formatter: Callable[[int], str],
    ) -> tuple[QSlider, QLabel]:
        """つまみと、その下の読み取り行(左=現在値 / 右=補足)を追加する。

        現在値は formatter(つまみ位置) の文字列で、つまみが動くたびに更新される。
        右側は空の補足ラベルとして返すので、呼び出し側が結果(件数など)を入れる。
        読み取り行は常に置いたままにする(空文字で更新する)。出し入れすると
        グループの高さが変わってスライダーが上下にずれるため。

        返すのは (QSlider, 補足ラベル)。QSlider をそのまま返すので、呼び出し側は
        valueChanged だけでなく sliderPressed(値が変わらない「触っただけ」)も拾える。
        """
        slider = QSlider(Qt.Horizontal, self)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        # ボタン類と同じく、フォーカスを奪うと一覧へ移って自動選択が起きるため防ぐ。
        slider.setFocusPolicy(Qt.NoFocus)
        slider.setCursor(Qt.PointingHandCursor)
        slider.setStyleSheet(style.PANEL_SLIDER_QSS)

        value_label = QLabel(formatter(value), self)
        # 読み取り行は左右とも補足情報。片方だけ強調すると、しきい値の方が
        # 結果より重要に見えてしまうため、右の件数と同じ見た目に揃える。
        value_label.setStyleSheet(style.CONTROL_HELP_QSS)
        slider.valueChanged.connect(lambda v: value_label.setText(formatter(v)))

        note_label = QLabel("", self)
        note_label.setStyleSheet(style.CONTROL_HELP_QSS)
        note_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        readout = QHBoxLayout()
        readout.setContentsMargins(0, 0, 0, 0)
        readout.setSpacing(6)
        readout.addWidget(value_label)
        readout.addStretch(1)
        readout.addWidget(note_label)

        self._outer.addWidget(slider)
        self._outer.addLayout(readout)
        return slider, note_label

    def _make_button(self, text: str, slot, checkable: bool) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない(奪うと一覧へフォーカスが移り自動選択が起きるため)。
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(style.CONTROL_BUTTON_QSS)
        btn.setCheckable(checkable)
        btn.clicked.connect(slot)
        return btn
