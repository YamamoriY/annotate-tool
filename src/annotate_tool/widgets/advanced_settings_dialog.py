"""上級者設定を並べる別ウィンドウ。

サイドパネルの「設定」に置くほど頻繁には触らない項目の置き場。チェックの
変更は呼び出し側がその場で書き出す(OK/キャンセルの二段構えにしないのは、
項目ごとに独立した ON/OFF で、まとめて取り消したい場面がないため)。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout, QWidget

from annotate_tool import style


class AdvancedSettingsDialog(QDialog):
    """チェックボックスを縦に積むだけの設定ウィンドウ。

    ControlGroup と同じく、外部との接点は追加したチェックボックスのシグナル
    のみ。設定の読み書きは呼び出し側が受け持つ。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("上級者設定")
        self.setStyleSheet(style.ADVANCED_DIALOG_QSS)
        # 「?」ボタンは使わない(項目の説明はラベル自身に書き切る)。
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 16, 20, 16)
        self._outer.setSpacing(10)

    def add_checkbox(self, text: str, *, checked: bool = False) -> QCheckBox:
        """オン/オフの設定行を追加する(状態は返り値のシグナルで拾う)。"""
        box = QCheckBox(text, self)
        box.setCursor(Qt.PointingHandCursor)
        box.setChecked(checked)
        self._outer.addWidget(box)
        return box
