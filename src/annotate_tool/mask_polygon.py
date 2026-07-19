"""塗りマスク(2値ビットマップ)を COCO polygon 列へ変換する純粋ロジック。

ブラシで塗った領域はラスタのマスクとして持ち、確定時にここで一度だけ輪郭を
抽出してポリゴン化する。コストは「塗った時間」ではなく「マスクの大きさ」に依存
するため、いくら長く塗っても確定が重くならない(業界標準のマスク方式)。

輪郭抽出は OpenCV の findContours(周囲追跡)+ approxPolyDP(Douglas-Peucker
による点間引き)。CVAT / Roboflow などの mask→polygon と同じ流儀。GUI(Qt)には
依存しないので、numpy 配列だけで単体テストできる。
"""

from __future__ import annotations

import cv2
import numpy as np


def mask_to_polygons(
    mask: np.ndarray,
    *,
    epsilon: float,
    min_area: float,
) -> list[list[float]]:
    """2値マスクの各連結領域の外周を COCO polygon 列へ変換して返す。

    - mask: 塗った画素が非ゼロの 2次元配列(dtype は問わない)。座標はそのまま
      画像座標として扱う(呼び出し側でマスクは画像と同サイズ・同原点にすること)。
    - epsilon: approxPolyDP の許容誤差[px]。大きいほど点が減り輪郭が滑らかに粗くなる。
    - min_area: これ未満の面積[px^2]の領域は捨てる(塗りムラ・スリバー除去)。

    返り値は [[x1, y1, x2, y2, ...], ...](各要素が1つの外周ポリゴン)。穴は
    RETR_EXTERNAL により無視する(従来の「逆巻きの穴は塗り領域にしない」と同じ)。
    """
    binary = np.ascontiguousarray((mask != 0).astype(np.uint8))
    if not binary.any():
        return []

    # RETR_EXTERNAL: 各連結領域の外周だけを取る(穴は無視)。
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    result: list[list[float]] = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        approx = cv2.approxPolyDP(contour, epsilon, True)  # 閉曲線として間引く
        pts = approx.reshape(-1, 2)
        if len(pts) < 3:
            continue  # 面積を持たない退化ポリゴンは捨てる
        flat: list[float] = []
        for x, y in pts:
            flat.extend((round(float(x), 2), round(float(y), 2)))
        result.append(flat)
    return result
