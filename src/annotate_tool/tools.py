"""追加(編集)モードで使う描画ツールの識別子。

ビュー(描画)とツールパネル(UI)の双方が参照するため、どちらにも依存しない
場所へ置く。Qt には依存しない。
"""

from __future__ import annotations

from enum import Enum


class Tool(Enum):
    """塗りマスクへの描き方。"""

    BRUSH = "brush"  # 塗る
    ERASER = "eraser"  # 消す
