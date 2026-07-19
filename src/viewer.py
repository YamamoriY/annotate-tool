"""COCO instance-segmentation のビューア。

画像を中央に表示し、矢印キーで画像を切り替えられる。各画像上には
instance segmentation のポリゴンをインスタンスごとに色分けして重ねて表示する。
左側のパネルにインスタンス一覧を表示し、一覧とビューを双方向に連動させる。
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QToolBar,
)

from coco_data import Annotation, CocoDataset

_NORMAL_PEN_WIDTH = 1.5
_SELECTED_PEN_WIDTH = 3.5
_NORMAL_FILL_ALPHA = 70
_SELECTED_FILL_ALPHA = 130
_DIM_ALPHA = 165  # 選択時に非選択部へかける暗幕の濃さ

# Z 値: 画像とオーバーレイは 0、暗幕は 0.5、選択インスタンスは 1
_Z_DIM = 0.5
_Z_SELECTED = 1.0


def instance_color(index: int) -> QColor:
    """インスタンス番号から見分けやすい色を生成する（黄金比で色相を回す）。"""
    hue = (index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def color_icon(color: QColor, size: int = 12) -> QIcon:
    """一覧用の小さな色見本アイコンを作る。"""
    pm = QPixmap(size, size)
    pm.fill(color)
    return QIcon(pm)


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
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

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

        # 選択時に非選択部を暗くするための暗幕（普段は非表示）
        self._dim_item = self._scene.addRect(self._scene.sceneRect())
        self._dim_item.setPen(QPen(Qt.NoPen))
        self._dim_item.setBrush(QBrush(QColor(0, 0, 0, _DIM_ALPHA)))
        self._dim_item.setZValue(_Z_DIM)
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
            color = instance_color(idx)
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
        pen.setWidthF(_SELECTED_PEN_WIDTH if selected else _NORMAL_PEN_WIDTH)
        return pen

    def _make_brush(self, color: QColor, selected: bool) -> QBrush:
        fill = QColor(color)
        if not self._show_fill:
            fill.setAlpha(0)
        else:
            fill.setAlpha(_SELECTED_FILL_ALPHA if selected else _NORMAL_FILL_ALPHA)
        return QBrush(fill)

    # --- 選択 / 強調 --------------------------------------------------------
    def select_instance(self, index: int, center: bool = False) -> None:
        """指定インスタンスを強調表示する。center=True でその位置へ寄せる。"""
        if index == self._selected:
            if center:
                self._center_on(index)
            return

        # 直前の選択を通常表示へ戻す
        self._restyle(self._selected, selected=False)
        self._selected = index
        self._restyle(index, selected=True, raise_z=True)

        # 選択中は非選択部へ暗幕をかける（選択インスタンスは暗幕の上に出る）
        if self._dim_item is not None:
            self._dim_item.setVisible(index >= 0)

        if center and index >= 0:
            self._center_on(index)

    def _restyle(self, index: int, selected: bool, raise_z: bool = False) -> None:
        if not (0 <= index < len(self._items_by_index)):
            return
        color = instance_color(index)
        for item in self._items_by_index[index]:
            item.setPen(self._make_pen(color, selected))
            item.setBrush(self._make_brush(color, selected))
            item.setZValue(_Z_SELECTED if raise_z else 0.0)

    def _center_on(self, index: int) -> None:
        if not (0 <= index < len(self._items_by_index)):
            return
        rect = QRectF()
        for item in self._items_by_index[index]:
            rect = item.sceneBoundingRect() if rect.isEmpty() else rect.united(
                item.sceneBoundingRect()
            )
        if not rect.isEmpty():
            self.centerOn(rect.center())

    def set_overlay_visible(self, visible: bool) -> None:
        for items in self._items_by_index:
            for item in items:
                item.setVisible(visible)

    # --- ズーム / フィット / クリック ---------------------------------------
    def fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
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


class ViewerWindow(QMainWindow):
    def __init__(self, dataset: CocoDataset):
        super().__init__()
        self.dataset = dataset
        self.index = 0
        self.show_overlay = True
        self.show_fill = True

        self.setWindowTitle("COCO Segmentation Viewer")
        self.resize(1400, 900)

        self.view = ImageView(self)
        self.view.instanceClicked.connect(self._on_instance_clicked)
        self.setCentralWidget(self.view)

        self._build_deselect_button()
        self._build_instance_panel()
        self._build_toolbar()
        self.setStatusBar(QStatusBar(self))
        self._info_label = QLabel()
        self.statusBar().addPermanentWidget(self._info_label)

        if self.dataset.images:
            self.load_current()
        else:
            self.statusBar().showMessage("画像がありません")

    def _build_deselect_button(self) -> None:
        """画像ビューの上部中央に浮かぶ「選択解除」ボタン。選択中のみ表示。"""
        self.deselect_btn = QPushButton("✕ 選択解除 (Esc)", self.view)
        self.deselect_btn.setCursor(Qt.PointingHandCursor)
        # フォーカスを奪わせない。奪うと非表示化でフォーカスが一覧へ移り、
        # 空選択の QListWidget が先頭行を自動選択してしまうため。
        self.deselect_btn.setFocusPolicy(Qt.NoFocus)
        self.deselect_btn.setStyleSheet(
            """
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
        )
        self.deselect_btn.clicked.connect(self.deselect)
        self.deselect_btn.adjustSize()
        self.deselect_btn.hide()
        # ビューのリサイズに追従して位置を更新するため監視する
        self.view.installEventFilter(self)

    def _reposition_deselect_button(self) -> None:
        btn = self.deselect_btn
        x = (self.view.width() - btn.width()) // 2
        btn.move(max(0, x), 12)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.view and event.type() == QEvent.Resize:
            self._reposition_deselect_button()
        return super().eventFilter(obj, event)

    def _set_selection_ui(self, selected: bool) -> None:
        """選択状態に応じて浮動ボタンの表示/非表示を切り替える。"""
        if selected:
            self.deselect_btn.adjustSize()
            self._reposition_deselect_button()
            self.deselect_btn.show()
            self.deselect_btn.raise_()
        else:
            self.deselect_btn.hide()
            # QGraphicsView のビューポートは自動では再描画されず残像が残るため、
            # 明示的に更新してボタンを確実に消す。
            self.view.viewport().update()

    def _build_instance_panel(self) -> None:
        self.instance_list = QListWidget()
        self.instance_list.setUniformItemSizes(True)
        self.instance_list.currentRowChanged.connect(self._on_list_row_changed)

        dock = QDockWidget("インスタンス一覧", self)
        dock.setWidget(self.instance_list)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock.setMinimumWidth(240)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Navigation", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addAction("◀ 前 (←)", self.prev_image)
        tb.addAction("次 (→) ▶", self.next_image)
        tb.addSeparator()
        tb.addAction("フィット (F)", self.view.fit)
        tb.addAction("オーバーレイ (V)", self.toggle_overlay)
        tb.addAction("塗り (B)", self.toggle_fill)

    # --- 画像の読み込み ------------------------------------------------------
    def load_current(self) -> None:
        image = self.dataset.images[self.index]
        path: Path = self.dataset.image_path(image)

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.statusBar().showMessage(f"画像を読み込めません: {path}")
            return

        self.view.set_image(pixmap)

        annotations = self.dataset.annotations_for(image.id)
        self.view.set_overlays(annotations, show_fill=self.show_fill)
        self.view.set_overlay_visible(self.show_overlay)
        self._populate_instance_list(annotations)

        self._info_label.setText(
            f"{image.file_name}   "
            f"[{self.index + 1}/{len(self.dataset.images)}]   "
            f"インスタンス数: {len(annotations)}"
        )

    def _populate_instance_list(self, annotations: list[Annotation]) -> None:
        self.instance_list.blockSignals(True)
        self.instance_list.clear()
        for idx, ann in enumerate(annotations):
            cat = self.dataset.category_name(ann.category_id)
            label = f"#{ann.id}  {cat}"
            if ann.area:
                label += f"  (area {int(ann.area)})"
            item = QListWidgetItem(color_icon(instance_color(idx)), label)
            item.setData(Qt.UserRole, idx)
            self.instance_list.addItem(item)
        self.instance_list.setCurrentRow(-1)
        self.instance_list.blockSignals(False)
        self.deselect_btn.hide()  # 画像切替で選択は解除される

    # --- 一覧 <-> ビュー 連動 -----------------------------------------------
    def _on_list_row_changed(self, row: int) -> None:
        self._set_selection_ui(row >= 0)
        if row < 0:
            self.view.select_instance(-1)
            return
        self.view.select_instance(row, center=True)

    def _on_instance_clicked(self, index: int) -> None:
        # ビューでクリック -> 一覧の選択を合わせる（シグナルループを避ける）
        self.instance_list.blockSignals(True)
        self.instance_list.setCurrentRow(index)
        self.instance_list.blockSignals(False)
        self.view.select_instance(index)
        self._set_selection_ui(index >= 0)

    def deselect(self) -> None:
        """選択を解除する（一覧・ビューの強調・暗幕・ボタンをすべて元に戻す）。"""
        # シグナル任せにせず、その場で確実に解除する。
        self.instance_list.blockSignals(True)
        self.instance_list.setCurrentRow(-1)
        self.instance_list.clearSelection()
        self.instance_list.blockSignals(False)
        self.view.select_instance(-1)
        self._set_selection_ui(False)

    # --- ナビゲーション ------------------------------------------------------
    def next_image(self) -> None:
        if not self.dataset.images:
            return
        self.index = (self.index + 1) % len(self.dataset.images)
        self.load_current()

    def prev_image(self) -> None:
        if not self.dataset.images:
            return
        self.index = (self.index - 1) % len(self.dataset.images)
        self.load_current()

    def toggle_overlay(self) -> None:
        self.show_overlay = not self.show_overlay
        self.view.set_overlay_visible(self.show_overlay)

    def toggle_fill(self) -> None:
        self.show_fill = not self.show_fill
        image = self.dataset.images[self.index]
        self.view.set_overlays(
            self.dataset.annotations_for(image.id), show_fill=self.show_fill
        )
        self.view.set_overlay_visible(self.show_overlay)
        # 選択状態を復元
        row = self.instance_list.currentRow()
        if row >= 0:
            self.view.select_instance(row)

    # --- キーボード ----------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D, Qt.Key_Space):
            self.next_image()
        elif key in (Qt.Key_Left, Qt.Key_A):
            self.prev_image()
        elif key == Qt.Key_F:
            self.view.fit()
        elif key == Qt.Key_V:
            self.toggle_overlay()
        elif key == Qt.Key_B:
            self.toggle_fill()
        elif key == Qt.Key_Escape:
            self.deselect()
        else:
            super().keyPressEvent(event)
