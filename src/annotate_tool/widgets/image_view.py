"""画像とセグメンテーションのオーバーレイを描画するビュー。

描画専用のウィジェットであり、アプリケーション状態は持たない。
ユーザー操作(ポリゴンのクリック)はシグナルで外へ通知するだけで、
選択をどう扱うかの判断は呼び出し側(ViewerWindow / ViewerState)に委ねる。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
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
    """ホイールでズーム、ドラッグでパンできる画像表示ビュー。"""

    instanceClicked = Signal(int)  # ポリゴンをクリックした際にそのインスタンス番号を通知

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(style.VIEW_BACKGROUND))

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._dim_item: QGraphicsRectItem | None = None
        # インスタンス番号 -> そのインスタンスを構成するポリゴンアイテム群
        self._items_by_index: list[list[QGraphicsPolygonItem]] = []
        self._show_fill = True
        self._selected = -1

    # --- シーン構築 ---------------------------------------------------------
    def set_image(self, pixmap: QPixmap) -> None:
        self._scene.clear()
        self._items_by_index = []
        self._selected = -1
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
        self._selected = -1
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
    def select_instance(self, index: int) -> None:
        """指定インスタンスを強調表示する。-1 で解除。"""
        if index == self._selected:
            return

        # 直前の選択を通常表示へ戻す
        self._restyle(self._selected, selected=False)
        self._selected = index
        self._restyle(index, selected=True, raise_z=True)

        # 選択中は非選択部へ暗幕をかける(選択インスタンスは暗幕の上に出る)
        if self._dim_item is not None:
            self._dim_item.setVisible(index >= 0)

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
            selected = idx == self._selected
            for item in items:
                item.setBrush(self._make_brush(color, selected))

    # --- ズーム / フィット / クリック ---------------------------------------
    def fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = style.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / style.ZOOM_STEP
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # 暗幕を無視し、最前面のポリゴンを拾う
            for item in self.items(event.pos()):
                if isinstance(item, QGraphicsPolygonItem):
                    idx = item.data(0)
                    if idx is not None:
                        self.instanceClicked.emit(int(idx))
                    break
        super().mousePressEvent(event)  # パン操作は従来通り
