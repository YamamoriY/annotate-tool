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
# 筆・消しゴムの半径(画像=シーン座標のピクセル)。スライダーで MIN..MAX を動かす。
BRUSH_RADIUS = 12.0
ERASER_RADIUS = 12.0  # 既定は筆と同じ太さ。別々に調整できるよう値は独立させる
BRUSH_RADIUS_MIN = 2.0
BRUSH_RADIUS_MAX = 60.0
PAINT_COLOR = QColor(90, 220, 150, 150)  # 塗った領域の表示色(半透明)
# 確定時にマスクを polygon 化するときのパラメータ(mask_polygon へ渡す)。
PAINT_SIMPLIFY_EPSILON = 1.5  # approxPolyDP の許容誤差[px]。大きいほど点が減る。
Z_ADD_DIM = 3.0  # 追加モードの暗幕(オーバーレイより上)
Z_PAINT = 3.5  # 塗った領域(暗幕より上)

# --- パス(頂点クリック)ツール ----------------------------------------------
# 閉じるとマスクへ焼かれるため、ここにあるのは「作図中」の見た目だけ。
PATH_MIN_POINTS = 3  # これ未満では閉じられない
PATH_CLOSE_THRESHOLD = 12  # 最初の頂点へ吸着して閉じる距離[ビュー座標 px]
PATH_VERTEX_SIZE = 8  # 頂点ハンドルの一辺[ビュー座標 px]
PATH_PEN_WIDTH = 2.0
PATH_COLOR = QColor(90, 220, 150, 230)  # 確定済みの辺(PAINT_COLOR と同系で濃いめ)
PATH_HANDLE_COLOR = QColor(255, 255, 255, 230)  # 頂点ハンドルの塗り
PATH_RUBBER_COLOR = QColor(255, 255, 255, 160)  # 最終頂点→カーソルの追従線
Z_PATH = 4.0  # 作図中のパス(塗りより上)

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

# 「画像」グループの中に出す、いま見ている画像の情報。枠は所属するグループが
# 持つので、ここでは付けない(入れ子の箱になる)。
INFO_LABEL_QSS = """
QLabel {
    color: rgba(255, 255, 255, 230);
    font-size: 14px;
    padding: 0 4px;
    background: transparent;
    border: none;
}
"""
# 2行目(インスタンス数)。1行目より淡く小さくして、主役をファイル名にする。
# QSS はラベル全体にしか効かないため、行ごとの差はこの HTML で付ける。
INFO_SUB_HTML = 'color: rgba(255, 255, 255, 150); font-size: 12px;'

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

# 設定のオン/オフ(補助テキストと同じ淡さで、チェック時だけ白く立てる)。
CONTROL_CHECK_QSS = """
QCheckBox {
    color: rgba(255, 255, 255, 150);
    font-size: 12px;
    padding: 0 4px;
    background: transparent;
    border: none;
}
QCheckBox:hover { color: rgba(255, 255, 255, 220); }
"""
# ::indicator は素のままにする。background-color を当てるとネイティブ描画が
# 止まり、チェック時の ✓ が消えて「色が変わるだけの四角」になるため。

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

# ツールパネル(追加モード中に画像ビュー左上へ浮かべる。余白は他の浮動バーと共通)。
# 幅は最長の「消しゴム (2)」の sizeHint に合わせる(枠と余白込みで 134px)。
# 足りないと Qt は文字を省略記号へ潰すだけで、黙って読めなくなる。
# ラベルにはキー表記が付くので、設定で長いキーを割り当てると溢れうる。
TOOL_BUTTON_WIDTH = 134
# トグルボタン。選択中(checked)を明るく塗って ON を一目で分かるようにする。
TOOL_BUTTON_QSS = """
QPushButton {
    background-color: rgba(40, 40, 40, 200);
    color: white;
    border: 1px solid rgba(255, 255, 255, 90);
    border-radius: 14px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton:hover { background-color: rgba(70, 70, 70, 220); }
QPushButton:checked {
    background-color: rgba(200, 200, 200, 235);
    color: rgb(20, 20, 20);
    border: 1px solid rgba(255, 255, 255, 200);
}
"""

# ブラシ太さスライダー(ツールパネルの各行に並べる)。
BRUSH_SLIDER_WIDTH = 110
BRUSH_SLIDER_QSS = """
QWidget {
    background-color: rgba(40, 40, 40, 200);
    border: 1px solid rgba(255, 255, 255, 90);
    border-radius: 14px;
}
QLabel { background: transparent; border: none; color: white; font-size: 13px; }
QSlider { background: transparent; border: none; }
QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 70);
    border: none;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px;
    margin: -5px 0;
    background: rgba(240, 240, 240, 235);
    border: none;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover { background: white; }
QSlider::sub-page:horizontal {
    background: rgba(200, 200, 200, 160);
    border-radius: 2px;
}
"""

# --- 面積しきい値スライダー(右パネル「選択」) --------------------------------
# つまみの位置は 0..AREA_SLIDER_STEPS の整数で、面積[px^2]へは指数で写す。
# 実データの面積分布が低域へ強く偏っている(中央値 2304 に対し p10 は 31)ため、
# 線形目盛りでは興味のある範囲がスライダー左端に潰れて操作できない。
#
# 範囲はデータの min/max ではなく固定値にする。データに合わせると画像ごとに
# 同じつまみ位置が違う面積を意味してしまい、「面積指定は画像をまたいで安定する」
# という利点が失われるため。
AREA_SLIDER_STEPS = 1000
AREA_SLIDER_MIN_LOG2 = 0.0  # 1 px^2
AREA_SLIDER_MAX_LOG2 = 16.0  # 65536 px^2 (相当辺長 256px)

# パネル内に直接置くスライダー(浮動バーの BRUSH_SLIDER と違い、外枠は付けない)。
PANEL_SLIDER_QSS = """
QSlider { background: transparent; border: none; }
QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 60);
    border: none;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px;
    margin: -5px 0;
    background: rgba(240, 240, 240, 235);
    border: none;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover { background: white; }
QSlider::sub-page:horizontal {
    background: rgba(200, 200, 200, 160);
    border-radius: 2px;
}
"""


# 「キャンセル」ボタン(追加モード中は常に上部へ表示)。
CANCEL_BUTTON_QSS = DESELECT_BUTTON_QSS

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


def area_from_slider(pos: int) -> float:
    """面積スライダーのつまみ位置[0..AREA_SLIDER_STEPS]を面積[px^2]へ変換する。"""
    frac = pos / AREA_SLIDER_STEPS
    span = AREA_SLIDER_MAX_LOG2 - AREA_SLIDER_MIN_LOG2
    return 2.0 ** (AREA_SLIDER_MIN_LOG2 + frac * span)


def format_area(area: float) -> str:
    """面積のしきい値を「一辺の長さ」で表示する。

    px² の生値は桁が大きく粒の大きさを掴みにくいので、同じ面積の正方形の
    一辺に直して出す。「≤」を付けて、これ以下が選ばれることを一目で示す。
    """
    return f"≤ {int(area ** 0.5)}px角"


def paint_min_area(radius: float) -> float:
    """これ未満の塗り領域はスリバーとして捨てる面積。ブラシ半径に比例させる。"""
    return (radius * 0.5) ** 2


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
