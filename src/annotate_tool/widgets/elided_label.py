"""収まらない分を「…」で省略する1行ラベル。

QLabel の wordWrap は単語境界でしか折り返せず、折り返し規則は変えられない
(QTextOption::WrapAnywhere を渡せるのは QTextEdit 系だけ)。空白を含まない
Windows のパスや長い ASCII ファイル名は全体が1つの「折り返し不能な単語」に
なり、minimumSizeHint が全文の幅まで膨らんで、置かれた先(右ドックなど)の
最小幅をそのまま押し上げてしまう。折り返す代わりに1行で省略し、全文は
ツールチップで見せる。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """全文を保持し、幅に収まらない分を「…」で省略して表示するラベル。"""

    # これより狭い幅は要求しない。レイアウトはここまで縮められ、縮んだ分は
    # resizeEvent が省略し直す。
    _MIN_WIDTH = 24

    def __init__(self, parent=None, *, mode: Qt.TextElideMode = Qt.ElideMiddle):
        super().__init__(parent)
        self._mode = mode
        self._full = ""
        # パスやファイル名には < や & が入りうるため、リッチテキストの
        # 自動判定に通さない(通すと HTML として解釈されて表示が化ける)。
        self.setTextFormat(Qt.PlainText)

    def set_full_text(self, text: str, *, tooltip: str | None = None) -> None:
        """表示する全文を差し替える。tooltip 省略時は全文をそのまま出す。"""
        self._full = text
        self.setToolTip(text if tooltip is None else tooltip)
        self._elide()

    def full_text(self) -> str:
        """省略前の全文(text() は省略後の表示文字列を返す)。"""
        return self._full

    def sizeHint(self) -> QSize:
        # 希望幅は全文の幅。余裕があるのに省略したままにしない。
        return QSize(
            self.fontMetrics().horizontalAdvance(self._full),
            super().sizeHint().height(),
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(self._MIN_WIDTH, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(
            self.fontMetrics().elidedText(self._full, self._mode, self.width())
        )
