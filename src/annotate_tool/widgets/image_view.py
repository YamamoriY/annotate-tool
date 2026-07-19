"""画像とセグメンテーションのオーバーレイを描画するビュー。

描画専用のウィジェットであり、アプリケーション状態は持たない。
ユーザー操作(ポリゴンのクリック)はシグナルで外へ通知するだけで、
選択をどう扱うかの判断は呼び出し側(ViewerWindow / ViewerState)に委ねる。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from annotate_tool import style
from annotate_tool.coco_data import Annotation


class ImageView(QGraphicsView):
    """ホイールでズーム、矩形ドラッグで複数選択できる画像表示ビュー。

    パンは中ボタンドラッグ、または Space を押しながらの左ドラッグで行う。
    """

    # 単一クリック: (インスタンス番号, additive=Shift)
    instanceClicked = Signal(int, bool)
    # 矩形選択: (触れたインスタンス番号のリスト, additive=Shift)
    rectSelected = Signal(object, bool)

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
        # Space によるパン切り替えのためキーイベントを受け取れるようにする
        self.setFocusPolicy(Qt.StrongFocus)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._dim_item: QGraphicsRectItem | None = None
        # インスタンス番号 -> そのインスタンスを構成するポリゴンアイテム群
        self._items_by_index: list[list[QGraphicsPolygonItem]] = []
        self._show_fill = True
        self._selected: set[int] = set()

        # 操作状態
        self._space_held = False  # Space 押下中は左ドラッグでパン
        self._press_pos: QPoint | None = None  # 左押下位置(クリック/ドラッグ判定用)
        self._panning = False  # 中ボタンによるパン中か
        self._pan_origin: QPoint | None = None  # パン開始時のマウス位置

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

    def wheelEvent(self, event) -> None:
        factor = style.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / style.ZOOM_STEP
        self.scale(factor, factor)

    # --- パン(中ボタン / Space+左ドラッグ)------------------------------------
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
        super().keyReleaseEvent(event)

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
            # 中ボタンドラッグでパン
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._space_held:
            # クリックとドラッグ(矩形選択)を release 時に判別するため位置を記録
            self._press_pos = event.pos()
        super().mousePressEvent(event)  # ラバーバンド / Space+パンは Qt に委ねる

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_origin is not None:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self._pan_by(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_origin = None
            self.unsetCursor()
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
            # ドラッグ扱い: 矩形に触れたインスタンスをまとめて選択
            rect = QRectF(
                self.mapToScene(press_pos), self.mapToScene(event.pos())
            ).normalized()
            super().mouseReleaseEvent(event)
            self.rectSelected.emit(self._instances_in_rect(rect), additive)
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
