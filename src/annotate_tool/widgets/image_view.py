"""画像とセグメンテーションのオーバーレイを描画するビュー。

描画専用のウィジェットであり、アプリケーション状態は持たない。
ユーザー操作(ポリゴンのクリック)はシグナルで外へ通知するだけで、
選択をどう扱うかの判断は呼び出し側(ViewerWindow / ViewerState)に委ねる。
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
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


def is_within(a: QPoint, b: QPoint, threshold: float) -> bool:
    """2点がビュー座標で threshold px 以内にあるか(パスを閉じる吸着判定)。"""
    dx = a.x() - b.x()
    dy = a.y() - b.y()
    return dx * dx + dy * dy <= threshold * threshold


class _OverlayPolygonItem(QGraphicsPolygonItem):
    """輪郭を二度描き(暗い縁 → 本線)するポリゴン。

    既定の QGraphicsPolygonItem はペンを1本しか持てないので、縁取りのために
    アイテムを二重に持つ代わりに描画側で二度打つ。当たり判定もアイテム数も
    増えないぶん、選択まわりのコードには手を入れずに済む。
    """

    def __init__(self, polygon: QPolygonF) -> None:
        super().__init__(polygon)
        self._halo_pen: QPen | None = None

    def set_halo_pen(self, pen: QPen | None) -> None:
        self._halo_pen = pen
        self.update()

    def boundingRect(self) -> QRectF:
        rect = super().boundingRect()
        if self._halo_pen is None:
            return rect
        # 縁は本線より外へ張り出すぶん、既定の矩形では描画が欠ける。ペンは
        # コスメティック(画面ピクセル幅)で、ズームアウト時はシーン座標での
        # 張り出しが 1/scale 倍になるため、余白は固定値で大きめに取る。
        margin = style.HALO_BOUNDS_MARGIN
        return rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        poly = self.polygon()
        painter.setRenderHint(QPainter.Antialiasing, True)

        brush = self.brush()
        if brush.color().alpha() > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(brush)
            painter.drawPolygon(poly)

        painter.setBrush(Qt.NoBrush)
        if self._halo_pen is not None:
            painter.setPen(self._halo_pen)
            painter.drawPolygon(poly)
        painter.setPen(self.pen())
        painter.drawPolygon(poly)


class _OverlayLayerItem(QGraphicsItem):
    """全インスタンスを事前レンダリングした1枚のラスタを表示するアイテム。

    数百のポリゴンアイテムを毎フレーム描くとパンのたびにフルフレームの
    ベクタ描画が走って重い(実測: 454個で ~46ms/フレーム)。代わりに
    非選択インスタンスをここへ焼き込み、パン中は画像1枚の転送(~1ms)で済ませる。
    QGIS など地図キャンバスのレイヤキャッシュと同じ方式。
    """

    def __init__(self) -> None:
        super().__init__()
        self._pixmap = QPixmap()
        self._target = QRectF()  # レイヤが覆うシーン上の範囲
        self._source = QRectF()  # ピクスマップ中の有効範囲(端数の余白を除く)

    def set_layer(self, pixmap: QPixmap, target: QRectF, source: QRectF) -> None:
        self.prepareGeometryChange()
        self._pixmap = pixmap
        self._target = QRectF(target)
        self._source = QRectF(source)
        self.update()

    def clear_layer(self) -> None:
        self.set_layer(QPixmap(), QRectF(), QRectF())

    def boundingRect(self) -> QRectF:
        return self._target

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        if self._pixmap.isNull():
            return
        # ズーム直後の焼き直し待ちの間は倍率が合わないまま伸縮されるので、
        # 補間を効かせて破綻を抑える(焼き直し後は等倍転送になる)。
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(self._target, self._pixmap, self._source)


class ImageView(QGraphicsView):
    """ホイールでズーム、矩形ドラッグで複数選択できる画像表示ビュー。

    左ドラッグは矩形選択(触れたインスタンスを選択に追加)、パンは中ボタンドラッグ。
    """

    # 単一クリック: (インスタンス番号, additive=Shift)
    instanceClicked = Signal(int, bool)
    # 矩形選択: 触れたインスタンス番号のリスト(常に選択へ追加)
    rectSelected = Signal(object)
    # 何もない場所の単一クリック(Esc と同じく選択解除の合図)
    backgroundClicked = Signal()
    # 追加モードで塗り始めた(最初の一筆)
    paintStarted = Signal()
    # 消しゴムで塗りが全部消えた(確定できるものが無くなった)
    paintCleared = Signal()
    # 作図中のパスの頂点が増減した(has_path() の結果が変わりうる)。
    # 頂点はマウス操作で増減するため、これが無いとウィンドウ側は
    # 「取消できるか」を知る手段が無い。
    pathChanged = Signal()

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
        self._dim_forced = False  # 選択が空でも暗幕を出す(面積スライダー操作中)
        # インスタンス番号 -> そのインスタンスを構成するポリゴンアイテム群
        self._items_by_index: list[list[_OverlayPolygonItem]] = []
        self._show_fill = True
        self._selected: set[int] = set()

        # オーバーレイのレイヤキャッシュ。非選択インスタンスはポリゴンアイテムを
        # 直接描かず(ItemHasNoContents)、ここへ焼いた1枚のラスタで表示する。
        # ポリゴンアイテム自体は当たり判定(クリック・矩形選択)と選択時の強調
        # 描画のために残す。
        self._layer_item: _OverlayLayerItem | None = None
        self._layer_scale = 0.0  # レイヤを焼いたときのビュー倍率
        self._layer_rect = QRectF()  # レイヤが覆うシーン範囲
        self._layer_timer = QTimer(self)
        self._layer_timer.setSingleShot(True)
        self._layer_timer.setInterval(style.LAYER_RENDER_DELAY_MS)
        self._layer_timer.timeout.connect(self._render_overlay_layer)

        # 点滅表示。実際に点滅するかは「ユーザーが有効にしたか」と「塗り編集中で
        # ないか」の両方で決まるので、二つを別々に持ち _update_blink に集約する。
        self._blink_enabled = False  # ユーザー設定
        self._blink_paused = False  # 塗り編集中の一時停止
        self._blink_on = True  # いまの位相(True = 見えている)
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(style.BLINK_INTERVAL_MS)
        self._blink_timer.timeout.connect(self._blink_tick)

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
        # 修正中に隠しているポリゴンアイテム(モードを抜けたら戻す)
        self._hidden_items: list[_OverlayPolygonItem] = []
        self._tool = Tool.BRUSH
        # 半径はツールごとに独立。スライダーで変わり、モードを跨いでも保持する。
        # パスには半径の概念が無いため、ここに Tool.POLYGON は入れない。
        self._radii = {
            Tool.BRUSH: style.BRUSH_RADIUS,
            Tool.ERASER: style.ERASER_RADIUS,
        }
        self._min_paint_radius = style.BRUSH_RADIUS_MAX  # この回で使った最も細い筆

        # パス(頂点クリック)ツールの作図中状態。閉じた時点でマスクへ焼くので、
        # ここにあるのは一時的な見た目だけ。頂点は確定後まで持ち越さない。
        self._path_points: list[QPointF] = []  # 打った頂点(シーン座標)
        self._path_item: QGraphicsPathItem | None = None  # 確定済みの辺
        self._path_rubber: QGraphicsLineItem | None = None  # 最終頂点→カーソル
        self._path_handles: list[QGraphicsRectItem] = []  # 頂点ハンドル
        # ボタンを押していなくてもラバーバンドを追従させるため
        self.setMouseTracking(True)

    # --- シーン構築 ---------------------------------------------------------
    def set_image(self, pixmap: QPixmap) -> None:
        self._scene.clear()  # 旧レイヤアイテムもここで破棄される
        self._items_by_index = []
        self._selected = set()
        self._layer_item = None
        self._layer_timer.stop()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

        # オーバーレイのレイヤ(Z は画像と同じ 0。後から追加したぶん画像の上、
        # 暗幕 Z_DIM より下に入る)
        self._layer_item = _OverlayLayerItem()
        self._scene.addItem(self._layer_item)
        self._layer_scale = 0.0
        self._layer_rect = QRectF()

        # 選択時に非選択部を暗くするための暗幕(普段は非表示)
        self._dim_item = self._scene.addRect(self._scene.sceneRect())
        self._dim_item.setPen(QPen(Qt.NoPen))
        self._dim_item.setBrush(QBrush(QColor(0, 0, 0, style.DIM_ALPHA)))
        self._dim_item.setZValue(style.Z_DIM)
        self._dim_item.setVisible(False)

        self.fit()

    def clear_image(self) -> None:
        """表示中の画像とオーバーレイを全て捨てる(何も開いていない状態)。

        set_image と違い、次に置く画像が無いのでシーン矩形も畳む。残しておくと
        空の領域へスクロール・ズームできてしまい、読み込み失敗と区別が付かない。
        """
        self._scene.clear()  # 中のアイテムは削除されるので参照を全て手放す
        self._items_by_index = []
        self._hidden_items = []
        self._selected = set()
        self._pixmap_item = None
        self._dim_item = None
        self._layer_item = None
        self._layer_timer.stop()
        self._scene.setSceneRect(0, 0, 0, 0)

    def set_overlays(
        self,
        annotations: list[Annotation],
        show_fill: bool = True,
    ) -> None:
        for items in self._items_by_index:
            for item in items:
                self._scene.removeItem(item)
        self._items_by_index = []
        self._hidden_items = []  # 作り直すので隠し中の参照も捨てる
        self._show_fill = show_fill
        self._selected = set()
        # 画像やインスタンスが入れ替わればスライダー操作の文脈も切れる。ここで
        # 落としておかないと、押しっぱなしのまま状況が変わったとき暗いまま戻らない。
        self._dim_forced = False
        self._update_dim()

        for idx, ann in enumerate(annotations):
            color = style.instance_color(idx)
            items: list[_OverlayPolygonItem] = []
            for poly in ann.polygons():
                qpoly = QPolygonF([QPointF(x, y) for x, y in poly])
                item = _OverlayPolygonItem(qpoly)
                item.setData(0, idx)  # クリック時にインスタンスを特定するため
                item.setPen(self._make_pen(color, selected=False))
                item.set_halo_pen(self._make_halo_pen(selected=False))
                item.setBrush(self._make_brush(color, selected=False))
                # 非選択の間は自前で描かない(表示はレイヤキャッシュが担う)。
                # アイテム自体は当たり判定のために残す。
                item.setFlag(QGraphicsItem.ItemHasNoContents, True)
                self._scene.addItem(item)
                items.append(item)
            self._items_by_index.append(items)

        # 作り直したアイテムは不透明度が既定(1.0)に戻っているので位相を塗り直す。
        # これを忘れると、消えている位相での画像送りや追加確定のあと、次の点滅まで
        # オーバーレイが出たままになる。
        self._apply_blink()
        self._render_overlay_layer()

    def _pen_width(self, selected: bool) -> float:
        """本線の幅。塗りを消しているときは境界判定用に太くする。"""
        if self._show_fill:
            return style.SELECTED_PEN_WIDTH if selected else style.NORMAL_PEN_WIDTH
        return (
            style.CONTOUR_SELECTED_PEN_WIDTH
            if selected
            else style.CONTOUR_PEN_WIDTH
        )

    def _make_pen(self, color: QColor, selected: bool) -> QPen:
        pen = QPen(color)
        pen.setCosmetic(True)  # ズームしても線幅を一定に保つ
        pen.setWidthF(self._pen_width(selected))
        return pen

    def _make_halo_pen(self, selected: bool) -> QPen:
        """本線の下に敷く暗い縁。本線より太いぶんだけ外側へはみ出す。"""
        pen = QPen(QColor(style.HALO_COLOR))
        pen.setCosmetic(True)
        pen.setWidthF(self._pen_width(selected) + style.HALO_EXTRA_WIDTH)
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
        self._update_dim()

    def set_dim_forced(self, on: bool) -> None:
        """選択が空でも暗幕をかけたままにする(面積スライダーの操作中に使う)。

        しきい値が最小インスタンスに届くまでは選択が空のままなので、選択の有無だけで
        暗幕を出し入れすると、つまみを動かし始めた瞬間に画面が明るく戻ってしまう。
        操作中は暗いままにして、増えていく選択を見比べられるようにする。
        """
        if self._dim_forced == on:
            return
        self._dim_forced = on
        self._update_dim()

    def _update_dim(self) -> None:
        """非選択部の暗幕の出し入れ(選択インスタンスは暗幕の上に出る)。"""
        if self._dim_item is not None:
            self._dim_item.setVisible(bool(self._selected) or self._dim_forced)

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
            item.set_halo_pen(self._make_halo_pen(selected))
            item.setBrush(self._make_brush(color, selected))
            item.setZValue(style.Z_SELECTED if raise_z else 0.0)
            # 選択中だけ自前で描く(暗幕の上に強調表示を出すため)。非選択に
            # 戻ったら描画をやめ、表示をレイヤキャッシュへ返す。レイヤには
            # 非選択スタイルが焼かれたままなので、焼き直しは要らない。
            item.setFlag(QGraphicsItem.ItemHasNoContents, not selected)

    # --- 表示切り替え --------------------------------------------------------
    def set_overlay_visible(self, visible: bool) -> None:
        for items in self._items_by_index:
            for item in items:
                item.setVisible(visible)
        if self._layer_item is not None:
            self._layer_item.setVisible(visible)

    def set_fill_visible(self, visible: bool) -> None:
        """塗りの有無を切り替える。選択状態は維持したまま再スタイルする。

        塗りを消したときは線幅も変わる(_pen_width)ので、ペンごと引き直す。
        """
        self._show_fill = visible
        for idx, items in enumerate(self._items_by_index):
            color = style.instance_color(idx)
            selected = idx in self._selected
            for item in items:
                item.setPen(self._make_pen(color, selected))
                item.set_halo_pen(self._make_halo_pen(selected))
                item.setBrush(self._make_brush(color, selected))
        self._render_overlay_layer()  # 非選択スタイルが変わったので焼き直す

    # --- 点滅表示 ------------------------------------------------------------
    def set_blink_enabled(self, enabled: bool) -> None:
        """オーバーレイの点滅表示を切り替える。"""
        self._blink_enabled = enabled
        self._update_blink()

    def _set_blink_paused(self, paused: bool) -> None:
        """塗り編集中は点滅を止める(基準にしている形が消えると塗りにくい)。"""
        self._blink_paused = paused
        self._update_blink()

    def _update_blink(self) -> None:
        """タイマーと位相を、いまの設定に合わせて整える(点滅まわりの唯一の入口)。

        点滅していない間は必ず位相を「見えている」へ戻す。止めた瞬間がたまたま
        消えている位相だと、オーバーレイが消えたまま固まってしまうため。
        """
        running = self._blink_enabled and not self._blink_paused
        if running:
            if not self._blink_timer.isActive():
                self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink_on = True
        self._apply_blink()

    def _blink_tick(self) -> None:
        self._blink_on = not self._blink_on
        self._apply_blink()

    def _apply_blink(self) -> None:
        """いまの位相を全オーバーレイへ反映する。

        暗幕(_dim_item)は点滅させない。一緒に消すと、選択中は暗幕だけが残って
        「何も選んでいない」ように見えてしまう。
        """
        opacity = 1.0 if self._blink_on else style.BLINK_OFF_OPACITY
        for items in self._items_by_index:
            for item in items:
                item.setOpacity(opacity)
        if self._layer_item is not None:
            self._layer_item.setOpacity(opacity)

    # --- ズーム / フィット / クリック ---------------------------------------
    def fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        if self._add_mode:
            self._apply_cursor()  # 倍率が変わったのでブラシ円を作り直す
        self._maybe_rerender_layer()

    def wheelEvent(self, event) -> None:
        factor = style.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / style.ZOOM_STEP
        self.scale(factor, factor)
        if self._add_mode:
            self._apply_cursor()  # 倍率が変わったのでブラシ円を作り直す
        self._maybe_rerender_layer()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        # パン(中ボタン・スクロールバー・centerOn いずれも)でレイヤの
        # マージンを使い切ったら焼き直しを予約する。__init__ 中にも呼ばれうる
        # ので属性の有無を確かめる。
        if getattr(self, "_layer_item", None) is not None:
            self._maybe_rerender_layer()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_layer_item", None) is not None:
            self._maybe_rerender_layer()

    # --- オーバーレイのレイヤキャッシュ --------------------------------------
    def _visible_scene_rect(self) -> QRectF:
        """ビューポートが映しているシーン範囲(シーン矩形へ切り詰め)。"""
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        return visible.intersected(self._scene.sceneRect())

    def _maybe_rerender_layer(self) -> None:
        """レイヤが今の表示に合わなくなっていたら焼き直しを予約する。

        ホイールズームや慣性的な連続パンで毎回焼くと本末転倒なので、
        操作が途切れてから1回だけ焼く(その間は古いレイヤが伸縮表示される)。
        """
        if self._layer_item is None or not self._items_by_index:
            return
        scale = self.transform().m11()
        stale_zoom = abs(scale - self._layer_scale) > self._layer_scale * 1e-3
        stale_pan = not self._layer_rect.contains(self._visible_scene_rect())
        if stale_zoom or stale_pan:
            self._layer_timer.start()

    def _render_overlay_layer(self) -> None:
        """非選択インスタンスを「ビューポート+マージン」の範囲へ焼き込む。

        現在のズーム倍率のピクセル密度で焼くので、コスメティックペン
        (画面上で一定の線幅)の見た目がそのまま保たれる。マージン内の
        パンでは再レンダリング不要になる。
        """
        self._layer_timer.stop()
        if self._layer_item is None or self._pixmap_item is None:
            return
        if not self._items_by_index:
            self._layer_item.clear_layer()
            return

        visible = self._visible_scene_rect()
        if visible.isEmpty():
            return
        mx = visible.width() * style.LAYER_MARGIN_FRAC
        my = visible.height() * style.LAYER_MARGIN_FRAC
        rect = visible.adjusted(-mx, -my, mx, my).intersected(
            self._scene.sceneRect()
        )
        if rect.isEmpty():
            return

        # 焼き込み解像度は「ビュー倍率 × デバイス倍率」。高DPI環境でも線が
        # 甘くならない。画素数が上限を超えるときだけ解像度を落とす。
        scale = self.transform().m11()
        dpr = self.viewport().devicePixelRatioF()
        eff = scale * dpr
        w = rect.width() * eff
        h = rect.height() * eff
        if w * h > style.LAYER_MAX_PIXELS:
            eff *= (style.LAYER_MAX_PIXELS / (w * h)) ** 0.5
            w = rect.width() * eff
            h = rect.height() * eff

        image = QImage(
            max(1, math.ceil(w)), max(1, math.ceil(h)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.scale(eff, eff)
        painter.translate(-rect.x(), -rect.y())

        # コスメティックペンの張り出しを見込んで、範囲判定は少し外側まで拾う
        cull = rect.adjusted(-style.HALO_BOUNDS_MARGIN, -style.HALO_BOUNDS_MARGIN,
                             style.HALO_BOUNDS_MARGIN, style.HALO_BOUNDS_MARGIN)
        for idx, items in enumerate(self._items_by_index):
            color = style.instance_color(idx)
            pen = self._make_pen(color, selected=False)
            halo = self._make_halo_pen(selected=False)
            brush = self._make_brush(color, selected=False)
            for item in items:
                if item in self._hidden_items:
                    continue  # 修正中のインスタンスはレイヤにも出さない
                poly = item.polygon()
                if not poly.boundingRect().intersects(cull):
                    continue
                if brush.color().alpha() > 0:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(brush)
                    painter.drawPolygon(poly)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(halo)
                painter.drawPolygon(poly)
                painter.setPen(pen)
                painter.drawPolygon(poly)
        painter.end()

        self._layer_item.set_layer(
            QPixmap.fromImage(image), rect, QRectF(0, 0, w, h)
        )
        self._layer_scale = scale
        self._layer_rect = QRectF(rect)

    # --- 追加(塗りつぶし)モード --------------------------------------------
    def set_add_mode(
        self,
        active: bool,
        edit_index: int | None = None,
        edit_annotation: Annotation | None = None,
    ) -> None:
        """塗りつぶしモードの ON/OFF。ON で全体に暗幕をかけブラシカーソルにする。

        修正対象(index とその Annotation)を渡すと、その形をマスクへ焼いた状態で
        始まる。元のポリゴンは塗りと二重に見えるため隠す。
        """
        self._clear_paint()
        self._restore_hidden()
        self._add_mode = active
        self._painting = False
        self._paint_started = False
        self._last_paint_pt = None
        self._set_blink_paused(active)

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
                if edit_annotation is not None and edit_index is not None:
                    self._prefill_mask(edit_index, edit_annotation)
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.RubberBandDrag)
        self._apply_cursor()

    def _prefill_mask(self, index: int, ann: Annotation) -> None:
        """修正対象の形をマスクへ焼き、元のポリゴン表示を隠す。

        既に「塗った」状態から始めるので `_paint_started` を立てる。スリバー判定の
        基準も最小半径にしておく(既存の細い部分を確定時に落とさないため)。
        """
        if self._mask_image is None:
            return
        painter = QPainter(self._mask_image)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(style.PAINT_COLOR))
        for pts in ann.polygons():
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        painter.end()

        self._paint_started = True
        self._min_paint_radius = style.BRUSH_RADIUS_MIN
        self._hide_instance(index)
        if self._paint_item is not None:
            self._paint_item.update()

    def _hide_instance(self, index: int) -> None:
        """修正中は元のポリゴンを隠す(塗りと二重に見えるのを防ぐ)。"""
        if not 0 <= index < len(self._items_by_index):
            return
        for item in self._items_by_index[index]:
            self._hidden_items.append(item)
            item.setVisible(False)
        self._render_overlay_layer()  # レイヤからも消す

    def _restore_hidden(self) -> None:
        if not self._hidden_items:
            return
        for item in self._hidden_items:
            item.setVisible(True)
        self._hidden_items = []
        self._render_overlay_layer()  # レイヤへ戻す

    def set_tool(self, tool: Tool) -> None:
        """描画ツール(ブラシ / 消しゴム / パス)を切り替える。

        作図中のパスは持ち越さず破棄する。別のツールへ移った後も宙に浮いた頂点が
        残っていると、Enter や Esc の意味が読めなくなるため。
        """
        if tool is self._tool:
            return
        self._clear_path()
        self._tool = tool
        if self._add_mode:
            self._apply_cursor()  # 太さが変わるのでカーソルを作り直す

    def set_radius(self, tool: Tool, radius: float) -> None:
        """ツールごとの半径(画像座標 px)を変える。カーソルの円も追従させる。"""
        if tool not in self._radii:
            return  # パスなど半径を持たないツール
        radius = max(style.BRUSH_RADIUS_MIN, min(radius, style.BRUSH_RADIUS_MAX))
        if radius == self._radii[tool]:
            return
        self._radii[tool] = radius
        if self._add_mode and tool is self._tool:
            self._apply_cursor()

    @property
    def _brush_radius(self) -> float:
        """現在選択中のツールの半径(半径を持たないツールでは既定値)。"""
        return self._radii.get(self._tool, style.BRUSH_RADIUS)

    @property
    def _is_path_tool(self) -> bool:
        """パスツールを選択中か(マウス操作の分岐が塗りと大きく違うため)。"""
        return self._tool is Tool.POLYGON

    def _apply_cursor(self) -> None:
        """現在のモードとツールに合ったカーソルを出す。

        カーソルを変える必要がある箇所(モード切替・ツール切替・ズーム・パン終了)は
        すべてここを通す。個別に setCursor すると分岐の追加漏れが起きるため。
        """
        if not self._add_mode:
            self.unsetCursor()
        elif self._tool is Tool.POLYGON:
            self.setCursor(Qt.CrossCursor)  # パスは太さが無いので円を出さない
        else:
            self._update_brush_cursor()

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
        self._clear_path()
        for attr in ("_paint_item", "_add_dim_item"):
            item = getattr(self, attr)
            if item is not None:
                self._scene.removeItem(item)
                setattr(self, attr, None)
        self._mask_image = None
        self._last_paint_pt = None
        self._min_paint_radius = style.BRUSH_RADIUS_MAX

    # --- パス(頂点クリック)ツール ------------------------------------------
    def has_path(self) -> bool:
        """作図中のパス(頂点が1つ以上)があるか。"""
        return bool(self._path_points)

    def cancel_path(self) -> None:
        """作図中のパスだけを破棄する(編集モードは抜けない)。"""
        self._clear_path()

    def undo_path_point(self) -> None:
        """直前に打った頂点を1つ取り消す。"""
        if not self._path_points:
            return
        self._path_points.pop()
        if self._path_points:
            self._refresh_path_items()
        else:
            # 全部消えたら作図前の状態へ戻す。この時点で既に空なので
            # _clear_path は通知を出さない(下でまとめて出す)。
            self._clear_path()
        self.pathChanged.emit()

    def close_path(self) -> bool:
        """作図中のパスを閉じ、囲んだ範囲をマスクへ焼く。閉じられたら True。

        ここを通った時点でパスはただの塗りになる。頂点は保存されない。
        """
        pts = self._path_points
        if len(pts) < style.PATH_MIN_POINTS or self._mask_image is None:
            return False

        poly = QPolygonF(pts)
        # 設定は _prefill_mask / _paint_to と揃える。アンチエイリアスを切るのは、
        # 縁のにじみがマスクを削って穴を作るのを防ぐため。
        painter = QPainter(self._mask_image)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(style.PAINT_COLOR))
        painter.drawPolygon(poly)
        painter.end()

        # 小さく囲んだ領域が確定時にスリバーとして捨てられないようにする
        # (筆の太さで面積を決める既定値は、パスには当てはまらないため)。
        self._min_paint_radius = min(self._min_paint_radius, style.BRUSH_RADIUS_MIN)

        dirty = poly.boundingRect().adjusted(-2.0, -2.0, 2.0, 2.0)
        self._clear_path()
        if self._paint_item is not None:
            self._paint_item.update(dirty)
        if not self._paint_started:
            self._paint_started = True
            self.paintStarted.emit()  # 上部に「確定」を出す
        return True

    def _clear_path(self) -> None:
        """作図中のパスの一時アイテムをすべて捨てる。マスクには触れない。"""
        had_points = bool(self._path_points)
        self._path_points = []
        while self._path_handles:
            self._scene.removeItem(self._path_handles.pop())
        for attr in ("_path_item", "_path_rubber"):
            item = getattr(self, attr)
            if item is not None:
                self._scene.removeItem(item)
                setattr(self, attr, None)
        if had_points:
            self.pathChanged.emit()

    def _add_path_point(self, view_pos: QPoint) -> None:
        """クリック位置に頂点を足す。最初の頂点の近くなら代わりに閉じる。"""
        if len(self._path_points) >= style.PATH_MIN_POINTS and self._near_first(
            view_pos
        ):
            self.close_path()
            return
        self._path_points.append(self.mapToScene(view_pos))
        self._refresh_path_items()
        self.pathChanged.emit()

    def _near_first(self, view_pos: QPoint) -> bool:
        """クリック位置が最初の頂点へ吸着する距離にあるか。

        判定はビュー座標で行う。シーン座標だとズーム倍率で当たり判定の体感が
        変わってしまうため。
        """
        if not self._path_points:
            return False
        first = self.mapFromScene(self._path_points[0])
        return is_within(view_pos, first, style.PATH_CLOSE_THRESHOLD)

    def _refresh_path_items(self) -> None:
        """打った頂点から、辺と頂点ハンドルの表示を作り直す。"""
        pts = self._path_points
        if not pts:
            return
        if self._path_item is None:
            pen = QPen(style.PATH_COLOR, style.PATH_PEN_WIDTH)
            pen.setCosmetic(True)  # ズームしても線幅を一定に保つ
            self._path_item = QGraphicsPathItem()
            self._path_item.setPen(pen)
            self._path_item.setBrush(QBrush(Qt.NoBrush))
            self._path_item.setZValue(style.Z_PATH)
            self._scene.addItem(self._path_item)

        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        self._path_item.setPath(path)
        self._sync_path_handles()

    def _sync_path_handles(self) -> None:
        """頂点ハンドルの個数と位置を頂点列に合わせる。"""
        pts = self._path_points
        while len(self._path_handles) < len(pts):
            size = style.PATH_VERTEX_SIZE
            item = QGraphicsRectItem(-size / 2.0, -size / 2.0, size, size)
            # ズームしてもハンドルの見かけの大きさを変えない(拡大時に画面を
            # 埋め尽くさないため)。位置は setPos で与える。
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            item.setPen(QPen(style.PATH_COLOR, 1.0))
            item.setBrush(QBrush(style.PATH_HANDLE_COLOR))
            item.setZValue(style.Z_PATH)
            self._scene.addItem(item)
            self._path_handles.append(item)
        while len(self._path_handles) > len(pts):
            self._scene.removeItem(self._path_handles.pop())
        for item, pt in zip(self._path_handles, pts):
            item.setPos(pt)

    def _update_rubber(self, scene_pt: QPointF) -> None:
        """最終頂点からカーソルへの追従線を引く。頂点が無ければ何もしない。"""
        if not self._path_points:
            return
        if self._path_rubber is None:
            pen = QPen(style.PATH_RUBBER_COLOR, style.PATH_PEN_WIDTH)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)  # 確定済みの辺と区別する
            self._path_rubber = QGraphicsLineItem()
            self._path_rubber.setPen(pen)
            self._path_rubber.setZValue(style.Z_PATH)
            self._scene.addItem(self._path_rubber)
        self._path_rubber.setLine(QLineF(self._path_points[-1], scene_pt))

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
        if self._add_mode and self._is_path_tool and event.button() == Qt.LeftButton:
            # 押した瞬間の位置で頂点を確定する。release まで待つとドラッグ判定に
            # 引っかかり、マウスを動かしながらのクリックで頂点が打てなくなる。
            self._add_path_point(event.pos())
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
        if self._add_mode and self._is_path_tool:
            self._update_rubber(self.mapToScene(event.pos()))
            event.accept()
            return
        if self._add_mode and self._painting:
            self._paint_to(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # ダブルクリックでも閉じられるようにする(1回目のクリックで打たれた頂点は
        # そのまま活かす。これは各種アノテーションツール共通の挙動)。
        if self._add_mode and self._is_path_tool and event.button() == Qt.LeftButton:
            self.close_path()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_origin = None
            self._apply_cursor()  # 追加モード中は描画用カーソルへ戻す
            event.accept()
            return

        if self._add_mode and self._is_path_tool and event.button() == Qt.LeftButton:
            # 頂点は press で確定済み。ここでは選択処理へ落とさないだけ。
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
                elif not additive:
                    # 何もない場所 = 選択解除。Shift 併用時は積み上げ中なので残す。
                    self.backgroundClicked.emit()
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
