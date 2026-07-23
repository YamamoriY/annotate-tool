"""「画像」グループに出す、いま見ている画像の情報表示。

1行目 = ファイル名(太字) + 枚数 [n/N]、2行目 = インスタンス数。以前は HTML を
組んだ1枚の QLabel だったが、長い ASCII ファイル名が折り返し不能な1単語になり
パネルの最小幅を押し上げるため(ElidedLabel の docstring 参照)、ファイル名だけ
省略表示のラベルに分けた。行ごとの見た目の差も HTML ではなく QSS で付ける。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from annotate_tool import style
from annotate_tool.widgets.elided_label import ElidedLabel


class ImageInfoLabel(QWidget):
    """現在画像のファイル名・枚数・補足を2行で表示する。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 0, 4, 0)  # 旧ラベルの padding(0 4px)相当
        outer.setSpacing(0)

        self.name_label = ElidedLabel(self)
        self.name_label.setStyleSheet(style.INFO_NAME_QSS)
        self.pos_label = QLabel(self)
        self.pos_label.setStyleSheet(style.INFO_POS_QSS)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)  # 旧表示でファイル名と枚数を区切っていた半角スペース相当
        row.addWidget(self.name_label)
        row.addWidget(self.pos_label)
        row.addStretch(1)  # 余りはここが吸う(枚数をファイル名の直後に置く)
        outer.addLayout(row)

        self.sub_label = QLabel(self)
        self.sub_label.setStyleSheet(style.INFO_SUB_QSS)
        outer.addWidget(self.sub_label)

    def set_info(self, file_name: str, position: str, sub_text: str) -> None:
        """ファイル名・枚数表示([n/N])・2行目の補足を表示する。"""
        self.name_label.set_full_text(file_name)
        self.pos_label.setText(position)
        self.sub_label.setText(sub_text)
        self.pos_label.show()
        self.sub_label.show()

    def set_message(self, text: str) -> None:
        """「画像がありません」など、1行のメッセージだけを出す。"""
        self.name_label.set_full_text(text, tooltip="")
        self.pos_label.hide()
        self.sub_label.hide()
