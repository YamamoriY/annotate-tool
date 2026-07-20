"""追加(編集)モードで使う描画ツールの識別子。

ビュー(描画)とツールパネル(UI)の双方が参照するため、どちらにも依存しない
場所へ置く。Qt には依存しない。
"""

from __future__ import annotations

from enum import Enum


class Tool(Enum):
    """塗りマスクへの描き方。

    POLYGON も「塗り方の一種」であり、閉じた時点でマスクへ焼かれる。頂点そのものは
    保持しないため、確定後はブラシで塗ったものと区別がつかない。
    """

    BRUSH = "brush"  # 塗る
    ERASER = "eraser"  # 消す
    POLYGON = "polygon"  # 頂点をクリックして囲んだ範囲を塗る
