"""mask_polygon(マスク→COCO polygon 変換)のテスト。

cv2 / numpy だけを使い Qt には依存しない。ポリゴンの厳密な頂点座標は間引き
アルゴリズム依存で脆いため、点数ではなく「面積・個数・位置」の性質で検証する。
"""

import numpy as np

from annotate_tool.mask_polygon import mask_to_polygons


def _bounds(flat: list[float]) -> tuple[float, float, float, float]:
    xs = flat[0::2]
    ys = flat[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def test_empty_mask_returns_nothing():
    mask = np.zeros((50, 50), dtype=np.uint8)
    assert mask_to_polygons(mask, epsilon=1.5, min_area=10) == []


def test_single_square_becomes_one_polygon():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:60, 30:80] = 1  # 高さ40 x 幅50 の矩形
    polys = mask_to_polygons(mask, epsilon=1.5, min_area=10)

    assert len(polys) == 1
    x0, y0, x1, y1 = _bounds(polys[0])
    # 矩形の外周に概ね一致する(1px 程度の誤差は許容)
    assert abs(x0 - 30) <= 1 and abs(y0 - 20) <= 1
    assert abs(x1 - 79) <= 1 and abs(y1 - 59) <= 1
    # 矩形なので頂点は 4 前後に間引かれる
    assert len(polys[0]) // 2 <= 6


def test_two_disjoint_blobs_become_two_polygons():
    mask = np.zeros((100, 200), dtype=np.uint8)
    mask[20:60, 10:50] = 1   # 左の塊
    mask[20:60, 150:190] = 1  # 右の塊
    polys = mask_to_polygons(mask, epsilon=1.5, min_area=10)

    assert len(polys) == 2
    centers = sorted((min(p[0::2]) + max(p[0::2])) / 2 for p in polys)
    assert centers[0] < 100 < centers[1]  # 左右に分かれている


def test_small_speck_is_dropped_by_min_area():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:50, 10:50] = 1  # 大きい塊(残る)
    mask[80:83, 80:83] = 1  # 3x3 の小さな点(捨てられる)
    polys = mask_to_polygons(mask, epsilon=1.5, min_area=50)

    assert len(polys) == 1
    x0, y0, _, _ = _bounds(polys[0])
    assert x0 < 60 and y0 < 60  # 残ったのは大きい塊のほう


def test_hole_is_ignored():
    mask = np.zeros((120, 120), dtype=np.uint8)
    mask[20:100, 20:100] = 1
    mask[50:70, 50:70] = 0  # 中央に穴
    polys = mask_to_polygons(mask, epsilon=1.5, min_area=10)

    # 外周ひとつだけ。穴は別ポリゴンにしない(RETR_EXTERNAL)。
    assert len(polys) == 1
    x0, y0, x1, y1 = _bounds(polys[0])
    assert abs(x0 - 20) <= 1 and abs(x1 - 99) <= 1


def test_non_uint8_mask_is_accepted():
    mask = np.zeros((60, 60), dtype=bool)
    mask[10:40, 10:40] = True
    polys = mask_to_polygons(mask, epsilon=1.5, min_area=10)
    assert len(polys) == 1
