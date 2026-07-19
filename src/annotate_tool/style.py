"""色・スタイル・レイアウトに関する定数とヘルパ。

見た目の調整はこのモジュールに集約する。ウィジェット側にマジックナンバーを
直接書かないこと。
"""

from __future__ import annotations

import colorsys

from PySide6.QtGui import QColor, QIcon, QPixmap

# --- ポリゴン描画 -----------------------------------------------------------
NORMAL_PEN_WIDTH = 1.5
SELECTED_PEN_WIDTH = 3.5
NORMAL_FILL_ALPHA = 70
SELECTED_FILL_ALPHA = 130
DIM_ALPHA = 165  # 選択時に非選択部へかける暗幕の濃さ

# Z 値: 画像とオーバーレイは 0、暗幕は 0.5、選択インスタンスは 1
Z_DIM = 0.5
Z_SELECTED = 1.0

# --- ビュー操作 -------------------------------------------------------------
ZOOM_STEP = 1.25  # ホイール 1 ノッチあたりの拡大率
VIEW_BACKGROUND = QColor(30, 30, 30)
# 左ドラッグをクリックと矩形選択のどちらに扱うかの閾値(ビュー座標のピクセル)
CLICK_DRAG_THRESHOLD = 4

# --- ウィンドウレイアウト ---------------------------------------------------
WINDOW_SIZE = (1400, 900)
DOCK_MIN_WIDTH = 240
FLOATING_BUTTON_TOP_MARGIN = 12
COLOR_ICON_SIZE = 12

# --- 浮動「選択解除」ボタン --------------------------------------------------
DESELECT_BUTTON_QSS = """
QPushButton {
    background-color: rgba(40, 40, 40, 200);
    color: white;
    border: 1px solid rgba(255, 255, 255, 90);
    border-radius: 14px;
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover { background-color: rgba(70, 70, 70, 220); }
QPushButton:pressed { background-color: rgba(20, 20, 20, 230); }
"""


def instance_color(index: int) -> QColor:
    """インスタンス番号から見分けやすい色を生成する(黄金比で色相を回す)。"""
    hue = (index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def color_icon(color: QColor, size: int = COLOR_ICON_SIZE) -> QIcon:
    """一覧用の小さな色見本アイコンを作る。"""
    pm = QPixmap(size, size)
    pm.fill(color)
    return QIcon(pm)
