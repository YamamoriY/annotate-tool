"""画像とセグメンテーションのオーバーレイを描画するビュー。

描画専用のウィジェットであり、アプリケーション状態は持たない。
ユーザー操作(ポリゴンのクリック)はシグナルで外へ通知するだけで、
選択をどう扱うかの判断は呼び出し側(ViewerWindow / ViewerState)に委ねる。
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from annotate_tool import style
from annotate_tool.coco_data import Annotation
from annotate_tool.mask_polygon import mask_to_polygons
from annotate_tool.tools import Tool


class ImageView(QGraphicsView):
    """ホイールでズーム、矩形ドラッグで複数選択できる画像表示ビュー。

    左ドラッグは矩形選択(触れたインスタンスを選択に追加)、パンは中ボタンドラッグ。
    """

    # 単一クリック: (インスタンス番号, additive=Shift)
    instanceClicked = Signal(int, bool)
    # 矩形選択: 触れたインスタンス番号のリスト(常に選択へ追加)
    rectSelected = Signal(object)
    # 追加モードで塗り始めた(最初の一筆)
    paintStarted = Signal()
    # 消しゴムで塗りが全部消えた(確定できるものが無くなった)
    paintCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        # 左ドラッグは矩形選択(ラバーバンド)。パンは中ボタン / Space+左ドラッグ。
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(style.VIEW_BACKGROUND))

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._dim_item: QGraphicsRectItem | None = None
        # インスタンス番号 -> そのインスタンスを構成するポリゴンアイテム群
        self._items_by_index: list[list[QGraphicsPolygonItem]] = []
        self._show_fill = True
        self._selected: set[int] = set()

        # 操作状態
        self._press_pos: QPoint | None = None  # 左押下位置(クリック/ドラッグ判定用)
        self._panning = False  # 中ボタンによるパン中か
        self._pan_origin: QPoint | None = None  # パン開始時のマウス位置

        # 追加(塗りつぶし)モード。塗りは QPainterPath ではなく画像サイズのラスタ
        # マスク(_mask_image)へ焼き込む。塗るコストは筆の周辺だけに収まり、塗った
        # 時間・回数に依存しない(確定時のポリゴン化は mask_polygon が一度だけ行う)。
        self._add_mode = False
        self._painting = False  # 左ボタンで塗っている最中か
        self._paint_started = False  # このモードで一度でも塗ったか
        self._mask_image: QImage | None = None  # 塗りマスク(ARGB32・画像と同サイズ)
        self._paint_item: _MaskItem | None = None  # マスクを表示するアイテム
        self._add_dim_item: QGraphicsRectItem | None = None
        self._last_paint_pt: QPointF | None = None
        self._tool = Tool.BRUSH
        # 半径はツールごとに独立。スライダーで変わり、モードを跨いでも保持する。
        self._radii = {
            Tool.BRUSH: style.BRUSH_RADIUS,
            Tool.ERASER: style.ERASER_RADIUS,
        }
        self._min_paint_radius = style.BRUSH_RADIUS_MAX  # この回で使った最も細い筆

    # --- シーン構築 ---------------------------------------------------------
    def set_image(self, pixmap: QPixmap) -> None:
        self._scene.clear()
        self._items_by_index = []
        self._selected = set()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

        # 選択時に非選択部を暗くするための暗幕(普段は非表示)
        self._dim_item = self._scene.addRect(self._scene.sceneRect())
        self._dim_item.setPen(QPen(Qt.NoPen))
        self._dim_item.setBrush(QBrush(QColor(0, 0, 0, style.DIM_ALPHA)))
        self._dim_item.setZValue(style.Z_DIM)
        self._dim_item.setVisible(False)

        self.fit()

    def set_overlays(
        self,
        annotations: list[Annotation],
        show_fill: bool = True,
    ) -> None:
        for items in self._items_by_index:
            for item in items:
                self._scene.removeItem(item)
        self._items_by_index = []
        self._show_fill = show_fill
        self._selected = set()
        if self._dim_item is not None:
            self._dim_item.setVisible(False)

        for idx, ann in enumerate(annotations):
            color = style.instance_color(idx)
            items: list[QGraphicsPolygonItem] = []
            for poly in ann.polygons():
                qpoly = QPolygonF([QPointF(x, y) for x, y in poly])
                item = QGraphicsPolygonItem(qpoly)
                item.setData(0, idx)  # クリック時にインスタンスを特定するため
                item.setPen(self._make_pen(color, selected=False))
                item.setBrush(self._make_brush(color, selected=False))
                self._scene.addItem(item)
                items.append(item)
            self._items_by_index.append(items)

    def _make_pen(self, color: QColor, selected: bool) -> QPen:
        pen = QPen(color)
        pen.setCosmetic(True)  # ズームしても線幅を一定に保つ
        pen.setWidthF(
            style.SELECTED_PEN_WIDTH if selected else style.NORMAL_PEN_WIDTH
        )
        return pen

    def _make_brush(self, color: QColor, selected: bool) -> QBrush:
        fill = QColor(color)
        if not self._show_fill:
            fill.setAlpha(0)
        else:
            fill.setAlpha(
                style.SELECTED_FILL_ALPHA if selected else style.NORMAL_FILL_ALPHA
            )
        return QBrush(fill)

    # --- 選択 / 強調 --------------------------------------------------------
    def set_selection(self, indices: Iterable[int]) -> None:
        """指定インスタンス群を強調表示する。空で解除。"""
        new = {i for i in indices if 0 <= i < len(self._items_by_index)}
        if new == self._selected:
            return

        # 直前の選択のうち外れたものを通常表示へ戻す
        for idx in self._selected - new:
            self._restyle(idx, selected=False)
        # 新たに選択されたものを強調
        for idx in new - self._selected:
            self._restyle(idx, selected=True, raise_z=True)
        self._selected = new

        # 選択中は非選択部へ暗幕をかける(選択インスタンスは暗幕の上に出る)
        if self._dim_item is not None:
            self._dim_item.setVisible(bool(new))

    def center_on_instance(self, index: int) -> None:
        """指定インスタンスの位置へビューを寄せる。"""
        if not (0 <= index < len(self._items_by_index)):
            return
        rect = QRectF()
        for item in self._items_by_index[index]:
            rect = item.sceneBoundingRect() if rect.isEmpty() else rect.united(
                item.sceneBoundingRect()
            )
        if not rect.isEmpty():
            self.centerOn(rect.center())

    def _restyle(self, index: int, selected: bool, raise_z: bool = False) -> None:
        if not (0 <= index < len(self._items_by_index)):
            return
        color = style.instance_color(index)
        for item in self._items_by_index[index]:
            item.setPen(self._make_pen(color, selected))
            item.setBrush(self._make_brush(color, selected))
            item.setZValue(style.Z_SELECTED if raise_z else 0.0)

    # --- 表示切り替え --------------------------------------------------------
    def set_overlay_visible(self, visible: bool) -> None:
        for items in self._items_by_index:
            for item in items:
                item.setVisible(visible)

    def set_fill_visible(self, visible: bool) -> None:
        """塗りの有無を切り替える。選択状態は維持したまま再スタイルする。"""
        self._show_fill = visible
        for idx, items in enumerate(self._items_by_index):
            color = style.instance_color(idx)
            selected = idx in self._selected
            for item in items:
                item.setBrush(self._make_brush(color, selected))

    # --- ズーム / フィット / クリック ---------------------------------------
    def fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        if self._add_mode:
            self._update_brush_cursor()  # 倍率が変わったのでブラシ円を作り直す

    def wheelEvent(self, event) -> None:
        factor = style.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / style.ZOOM_STEP
        self.scale(factor, factor)
        if self._add_mode:
            self._update_brush_cursor()  # 倍率が変わったのでブラシ円を作り直す

    # --- 追加(塗りつぶし)モード --------------------------------------------
    def set_add_mode(self, active: bool) -> None:
        """塗りつぶしモードの ON/OFF。ON で全体に暗幕をかけブラシカーソルにする。"""
        self._clear_paint()
        self._add_mode = active
        self._painting = False
        self._paint_started = False
        self._last_paint_pt = None

        if active:
            if self._pixmap_item is not None:
                self._add_dim_item = self._scene.addRect(self._scene.sceneRect())
                self._add_dim_item.setPen(QPen(Qt.NoPen))
                self._add_dim_item.setBrush(
                    QBrush(QColor(0, 0, 0, style.ADD_DIM_ALPHA))
                )
                self._add_dim_item.setZValue(style.Z_ADD_DIM)

                # 画像と同サイズの透明マスクを用意し、そこへ塗る。
                self._mask_image = QImage(
                    self._pixmap_item.pixmap().size(), QImage.Format_ARGB32
                )
                self._mask_image.fill(Qt.transparent)
                self._paint_item = _MaskItem(self._mask_image)
                self._paint_item.setZValue(style.Z_PAINT)
                self._scene.addItem(self._paint_item)
            self.setDragMode(QGraphicsView.NoDrag)
            self._update_brush_cursor()
        else:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.unsetCursor()

    def set_tool(self, tool: Tool) -> None:
        """描画ツール(ブラシ / 消しゴム)を切り替える。"""
        if tool is self._tool:
            return
        self._tool = tool
        if self._add_mode:
            self._update_brush_cursor()  # 太さが変わるのでカーソルを作り直す

    def set_radius(self, tool: Tool, radius: float) -> None:
        """ツールごとの半径(画像座標 px)を変える。カーソルの円も追従させる。"""
        radius = max(style.BRUSH_RADIUS_MIN, min(radius, style.BRUSH_RADIUS_MAX))
        if radius == self._radii[tool]:
            return
        self._radii[tool] = radius
        if self._add_mode and tool is self._tool:
            self._update_brush_cursor()

    @property
    def _brush_radius(self) -> float:
        """現在選択中のツールの半径。"""
        return self._radii[self._tool]

    def _update_brush_cursor(self) -> None:
        """ブラシ半径(画像座標)を現在のズーム倍率で画面サイズに直し、
        その太さの円の輪郭をカーソルにする。ズームや太さ変更で呼び直す。"""
        scale = self.transform().m11()  # ビューは等方スケールのみ
        diameter = max(6.0, min(2.0 * self._brush_radius * scale, 512.0))
        margin = 2
        size = int(math.ceil(diameter)) + margin * 2
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        center = size / 2.0
        rect = QRectF(
            center - diameter / 2.0, center - diameter / 2.0, diameter, diameter
        )
        # 背景の明暗を問わず見えるよう、黒縁の上に白線を重ねる
        painter.setPen(QPen(QColor(0, 0, 0, 180), 3))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(255, 255, 255, 235), 1.2))
        painter.drawEllipse(rect)
        painter.end()
        self.setCursor(QCursor(pm, int(center), int(center)))

    def _clear_paint(self) -> None:
        """塗り・暗幕アイテムをシーンから取り除き、マスクを捨てる。"""
        for attr in ("_paint_item", "_add_dim_item"):
            item = getattr(self, attr)
            if item is not None:
                self._scene.removeItem(item)
                setattr(self, attr, None)
        self._mask_image = None
        self._last_paint_pt = None
        self._min_paint_radius = style.BRUSH_RADIUS_MAX

    def _paint_to(self, scene_pt: QPointF) -> None:
        """現在のツールの円をマスクへ焼き込む。前回点から掃引して隙間を埋める。

        コンポジションはブラシなら Source(上書き)、消しゴムなら Clear(消去)。
        いずれもアンチエイリアスなしで塗る。こうすると重ね塗りしても塗った画素の
        アルファは一定に保たれ、縁のにじみがマスクを削って穴を作ることがない。
        塗り直した部分だけを update() して再描画コストを抑える。
        """
        if self._mask_image is None:
            return
        r = self._brush_radius
        if self._tool is Tool.BRUSH:
            # スリバー判定の基準は「この回で使った最も細い筆」。太い筆に持ち替えた
            # 後でも細筆で打った点が捨てられないようにする(消しゴムは対象外)。
            self._min_paint_radius = min(self._min_paint_radius, r)
        last = self._last_paint_pt

        painter = QPainter(self._mask_image)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setCompositionMode(
            QPainter.CompositionMode_Clear
            if self._tool is Tool.ERASER
            else QPainter.CompositionMode_Source
        )
        if last is None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(style.PAINT_COLOR))
            painter.drawEllipse(scene_pt, r, r)
        else:
            # 前回点から今回点までを直径 2r の丸ペンで掃く(=円を連ねたのと同じ)
            pen = QPen(style.PAINT_COLOR, 2.0 * r)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(last, scene_pt)
        painter.end()

        self._last_paint_pt = scene_pt
        if self._paint_item is not None:
            self._paint_item.update(self._dirty_rect(last, scene_pt, r))

    @staticmethod
    def _dirty_rect(last: QPointF | None, cur: QPointF, r: float) -> QRectF:
        """last→cur の掃引が触れた範囲(ブラシ半径ぶん広げた矩形)を返す。"""
        pad = r + 2.0
        x0, x1 = cur.x(), cur.x()
        y0, y1 = cur.y(), cur.y()
        if last is not None:
            x0, x1 = min(x0, last.x()), max(x1, last.x())
            y0, y1 = min(y0, last.y()), max(y1, last.y())
        return QRectF(x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad)

    def _mask_alpha(self) -> np.ndarray | None:
        """塗りマスクのアルファ面(= 塗りの有無)を numpy 配列として覗く。

        ARGB32 のバッファをそのまま参照する。リトルエンディアンでは各画素は
        メモリ上 B,G,R,A の順なので、4 バイト目(index 3)がアルファになる。
        """
        img = self._mask_image
        if img is None:
            return None
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return None
        stride = img.bytesPerLine()
        buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=stride * h)
        return buf.reshape(h, stride)[:, 3 : w * 4 : 4]

    def _mask_is_empty(self) -> bool:
        """マスクに塗り残しが一切ないか。消しゴムを離したときだけ呼ぶ。"""
        alpha = self._mask_alpha()
        return alpha is None or not alpha.any()

    def painted_polygons(self) -> list[list[float]]:
        """塗ったマスクを COCO polygon 列(画像座標)へ変換して返す。空なら []。

        マスクのアルファ面を 2値化し、mask_polygon(OpenCV の輪郭抽出+間引き)へ
        渡すだけ。コストはマスクの大きさで決まり、塗った時間には依存しない。
        """
        alpha = self._mask_alpha()
        if alpha is None:
            return []
        return mask_to_polygons(
            alpha,
            epsilon=style.PAINT_SIMPLIFY_EPSILON,
            min_area=style.paint_min_area(self._min_paint_radius),
        )

    # --- パン(中ボタンドラッグ)----------------------------------------------
    def _pan_by(self, delta: QPoint) -> None:
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() - delta.x())
        v.setValue(v.value() - delta.y())

    # --- クリック / 矩形選択 --------------------------------------------------
    def _instance_at(self, pos: QPoint) -> int | None:
        """ビュー座標 pos の最前面ポリゴンのインスタンス番号(暗幕は無視)。"""
        for item in self.items(pos):
            if isinstance(item, QGraphicsPolygonItem):
                idx = item.data(0)
                if idx is not None:
                    return int(idx)
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            # 中ボタンドラッグでパン(追加モードでも使える)
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if self._add_mode and event.button() == Qt.LeftButton:
            # 追加モード: 左ドラッグで塗る(選択・矩形処理は行わない)
            self._painting = True
            self._paint_to(self.mapToScene(event.pos()))
            # 「確定」を出すのは塗った後だけ。消しゴムだけ動かしても確定は出さない。
            if self._tool is Tool.BRUSH and not self._paint_started:
                self._paint_started = True
                self.paintStarted.emit()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # クリックとドラッグ(矩形選択)を release 時に判別するため位置を記録
            self._press_pos = event.pos()
        super().mousePressEvent(event)  # ラバーバンドの描画は Qt に委ねる

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_origin is not None:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self._pan_by(delta)
            event.accept()
            return
        if self._add_mode and self._painting:
            self._paint_to(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_origin = None
            # 追加モード中はブラシカーソルへ戻す
            self._update_brush_cursor() if self._add_mode else self.unsetCursor()
            event.accept()
            return

        if self._add_mode and event.button() == Qt.LeftButton:
            # 一筆の終わり。塗った内容は保持し、次の筆も同じ領域へ足せる。
            self._painting = False
            self._last_paint_pt = None
            # 消し切ったなら「塗り始め前」の状態へ戻す(確定を引っ込めるため)。
            # 全面走査するので、消しゴムを離した瞬間だけに限る。
            if (
                self._tool is Tool.ERASER
                and self._paint_started
                and self._mask_is_empty()
            ):
                self._paint_started = False
                self._min_paint_radius = style.BRUSH_RADIUS_MAX
                self.paintCleared.emit()
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._press_pos is not None:
            press_pos = self._press_pos
            self._press_pos = None
            additive = bool(event.modifiers() & Qt.ShiftModifier)
            moved = (event.pos() - press_pos).manhattanLength()
            if moved <= style.CLICK_DRAG_THRESHOLD:
                # クリック扱い: 押下位置のポリゴンを選択
                super().mouseReleaseEvent(event)
                idx = self._instance_at(press_pos)
                if idx is not None:
                    self.instanceClicked.emit(idx, additive)
                return
            # ドラッグ扱い: 矩形に触れたインスタンスを選択へ追加(常に加算)
            rect = QRectF(
                self.mapToScene(press_pos), self.mapToScene(event.pos())
            ).normalized()
            super().mouseReleaseEvent(event)
            self.rectSelected.emit(self._instances_in_rect(rect))
            return

        super().mouseReleaseEvent(event)

    def _instances_in_rect(self, scene_rect: QRectF) -> list[int]:
        """矩形に触れた(交差した)インスタンス番号を重複なく返す。"""
        found: set[int] = set()
        for item in self._scene.items(scene_rect, Qt.IntersectsItemShape):
            if isinstance(item, QGraphicsPolygonItem):
                idx = item.data(0)
                if idx is not None:
                    found.add(int(idx))
        return sorted(found)


class _MaskItem(QGraphicsItem):
    """塗りマスク画像を表示するだけの軽量アイテム。

    paint() は画像を drawImage するだけだが、Qt は露出領域(exposedRect)しか
    転送しないため、塗った箇所だけを update() すれば毎フレームの描画コストは筆の
    周辺に収まる。画像全体を QPixmap へ変換し直す方式と違い、大きな画像でも塗りが
    重くならない。
    """

    def __init__(self, image: QImage):
        super().__init__()
        self._image = image

    def boundingRect(self) -> QRectF:
        return QRectF(self._image.rect())

    def paint(self, painter, option, widget=None) -> None:
        r = option.exposedRect
        painter.drawImage(r, self._image, r)
