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

# --- 追加(塗りつぶし)モード -----------------------------------------------
ADD_DIM_ALPHA = 130  # 追加モード中に全体へかける暗幕の濃さ
BRUSH_RADIUS = 12.0  # 塗りブラシの半径(画像=シーン座標のピクセル)
PAINT_COLOR = QColor(90, 220, 150, 150)  # 塗った領域の表示色(半透明)
Z_ADD_DIM = 3.0  # 追加モードの暗幕(オーバーレイより上)
Z_PAINT = 3.5  # 塗った領域(暗幕より上)

# --- ビュー操作 -------------------------------------------------------------
ZOOM_STEP = 1.25  # ホイール 1 ノッチあたりの拡大率
VIEW_BACKGROUND = QColor(30, 30, 30)
# 左ドラッグをクリックと矩形選択のどちらに扱うかの閾値(ビュー座標のピクセル)
CLICK_DRAG_THRESHOLD = 4

# --- ウィンドウレイアウト ---------------------------------------------------
WINDOW_SIZE = (1400, 900)
DOCK_MIN_WIDTH = 240
FLOATING_BUTTON_TOP_MARGIN = 12
FLOATING_BUTTON_BOTTOM_MARGIN = 12  # 下端に寄せる浮動バーの余白
FLOATING_BUTTON_SIDE_MARGIN = 12  # 左右端に寄せる浮動バーの余白
COLOR_ICON_SIZE = 12

# --- 浮動アクションバー(選択中に表示)--------------------------------------
FLOATING_BUTTON_SPACING = 8  # バー内のボタン間隔

# 常時表示する操作ボタン(左下=「表示」トグル、右上=前/次)。
# トグルは checked 状態を灰色に強調して ON/OFF を一目で分かるようにする。
CONTROL_BUTTON_QSS = """
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
QPushButton:checked {
    background-color: rgba(120, 120, 120, 230);
    border: 1px solid rgba(220, 220, 220, 150);
}
QPushButton:checked:hover { background-color: rgba(140, 140, 140, 240); }
"""

# 浮動バーのカテゴリ見出し(例: 「表示」)。
CONTROL_LABEL_QSS = """
QLabel {
    color: rgba(255, 255, 255, 180);
    font-size: 11px;
    font-weight: bold;
    padding: 0 4px;
    background: transparent;
    border: none;
}
"""

# 操作説明などの補助テキスト(見出しより淡く、少し小さめ)。
CONTROL_HELP_QSS = """
QLabel {
    color: rgba(255, 255, 255, 150);
    font-size: 12px;
    padding: 0 4px;
    background: transparent;
    border: none;
}
"""

# カテゴリでまとめる浮動バーの外枠(枠線 + 半透明背景)。
CONTROL_GROUP_QSS = """
#controlGroup {
    background-color: rgba(30, 30, 30, 140);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 12px;
}
"""

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

DELETE_BUTTON_QSS = """
QPushButton {
    background-color: rgba(150, 40, 40, 210);
    color: white;
    border: 1px solid rgba(255, 160, 160, 120);
    border-radius: 14px;
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover { background-color: rgba(190, 55, 55, 230); }
QPushButton:pressed { background-color: rgba(120, 25, 25, 240); }
"""

# ステータスバー右下の「保存中…」表示(遅延保存の進捗)。
SAVING_LABEL_QSS = "QLabel { color: rgba(230, 230, 230, 200); font-size: 12px; }"
SAVE_DELAY_MS = 40  # 確定後、通常画面を描画してから保存するまでの遅延
SAVE_DONE_HOLD_MS = 900  # 「保存しました」を表示しておく時間

# 「追加」ボタン(通常時に上部へ表示)。
ADD_BUTTON_QSS = """
QPushButton {
    background-color: rgba(40, 40, 40, 200);
    color: white;
    border: 1px solid rgba(255, 255, 255, 90);
    border-radius: 14px;
    padding: 6px 18px;
    font-size: 13px;
}
QPushButton:hover { background-color: rgba(70, 70, 70, 220); }
QPushButton:pressed { background-color: rgba(20, 20, 20, 230); }
"""

# 「確定」ボタン(塗り始めたら上部へ表示)。
CONFIRM_BUTTON_QSS = """
QPushButton {
    background-color: rgba(45, 140, 90, 220);
    color: white;
    border: 1px solid rgba(160, 240, 200, 140);
    border-radius: 14px;
    padding: 6px 18px;
    font-size: 13px;
}
QPushButton:hover { background-color: rgba(55, 165, 105, 235); }
QPushButton:pressed { background-color: rgba(35, 110, 70, 240); }
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
