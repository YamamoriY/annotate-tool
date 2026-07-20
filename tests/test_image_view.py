"""ImageView の純粋なヘルパのテスト。

ビュー本体はウィジェットの生成に QApplication が要るためテストしない
(このリポジトリには GUI テストの基盤が無い)。座標判定だけは切り出してあるので、
そこはここで押さえる。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint

from annotate_tool.widgets.image_view import is_within


def test_within_threshold():
    assert is_within(QPoint(10, 10), QPoint(13, 14), 5)  # 距離 5 ちょうど


def test_outside_threshold():
    assert not is_within(QPoint(10, 10), QPoint(14, 14), 5)  # 距離 ~5.66


def test_same_point():
    assert is_within(QPoint(7, 7), QPoint(7, 7), 0)


def test_uses_euclidean_not_manhattan():
    """マンハッタン距離なら 6 で外れるが、ユークリッドなら 5 で収まる。"""
    assert is_within(QPoint(0, 0), QPoint(3, 4), 5)
