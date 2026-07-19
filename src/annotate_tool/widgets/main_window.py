"""メインウィンドウ。

ここは「組み立てと配線」だけを行う composition root。
- 状態の保持・遷移      -> ViewerState
- 画像とオーバーレイ描画 -> ImageView
- インスタンス一覧      -> InstancePanel
- キーボード操作        -> QAction のショートカット(_build_actions)

ユーザー操作はすべて ViewerState のメソッド呼び出しに変換し、
ウィジェットの表示更新はすべて ViewerState のシグナル経由で行う。
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
)
from PySide6.QtCore import Qt

from annotate_tool import style
from annotate_tool.coco_data import CocoDataset
from annotate_tool.state import ViewerState
from annotate_tool.widgets.action_bar import FloatingActionBar
from annotate_tool.widgets.control_bar import FloatingControlBar
from annotate_tool.widgets.image_view import ImageView
from annotate_tool.widgets.instance_panel import InstancePanel


class ViewerWindow(QMainWindow):
    def __init__(self, dataset: CocoDataset):
        super().__init__()
        self.state = ViewerState(dataset, self)

        self.setWindowTitle("COCO Segmentation Viewer")
        self.resize(*style.WINDOW_SIZE)

        self.view = ImageView(self)
        self.setCentralWidget(self.view)
        self.action_bar = FloatingActionBar(self.view)

        self.panel = InstancePanel(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.panel)

        self._build_actions()
        self._build_control_bars()

        self.setStatusBar(QStatusBar(self))
        self._info_label = QLabel()
        self.statusBar().addPermanentWidget(self._info_label)

        self._connect_signals()

        if self.state.dataset.images:
            self._load_image(self.state.image_index)
        else:
            self.statusBar().showMessage("画像がありません")

    # --- 組み立て -----------------------------------------------------------
    def _build_actions(self) -> None:
        def make(text: str, keys: list[str], slot) -> QAction:
            action = QAction(text, self)
            action.setShortcuts([QKeySequence(k) for k in keys])
            action.triggered.connect(slot)
            self.addAction(action)  # ツールバー未追加でもショートカットを有効にする
            return action

        # ショートカットのみ(ボタンはビュー上の浮動バーが担う)。
        make("前", ["Left", "A"], self.state.prev_image)
        make("次", ["Right", "D", "Space"], self.state.next_image)
        make("フィット", ["F"], self.view.fit)
        make("オーバーレイ", ["V"], self.state.toggle_overlay)
        make("塗り", ["B"], self.state.toggle_fill)
        make("選択解除", ["Esc"], self.state.deselect)
        make("削除", ["Delete"], self._delete_selected)

    def _build_control_bars(self) -> None:
        """ビューの左下(「表示」カテゴリ)と右上(画像送り)へ操作ボタンを浮かべる。"""
        display = FloatingControlBar(self.view, anchor="bottom-left", title="表示")
        display.add_button("フィット (F)", self.view.fit)
        self._overlay_btn = display.add_button(
            "オーバーレイ (V)", self.state.toggle_overlay, checkable=True
        )
        self._fill_btn = display.add_button("塗り (B)", self.state.toggle_fill, checkable=True)
        self._overlay_btn.setChecked(self.state.overlay_visible)
        self._fill_btn.setChecked(self.state.fill_visible)
        self.control_bar_display = display

        nav = FloatingControlBar(self.view, anchor="top-right")
        nav.add_button("◀ 前", self.state.prev_image)
        nav.add_button("次 ▶", self.state.next_image)
        self.control_bar_nav = nav

    def _connect_signals(self) -> None:
        # ユーザー操作 -> 状態
        self.view.instanceClicked.connect(self._on_instance_clicked)
        self.view.rectSelected.connect(self._on_rect_selected)
        self.panel.selectionChanged.connect(self._on_panel_selection)
        self.action_bar.deselectClicked.connect(self.state.deselect)
        self.action_bar.deleteClicked.connect(self._delete_selected)

        # 状態 -> 表示
        self.state.imageChanged.connect(self._load_image)
        self.state.selectionChanged.connect(self._apply_selection)
        self.state.annotationsChanged.connect(self._refresh_overlays)
        self.state.overlayVisibleChanged.connect(self.view.set_overlay_visible)
        self.state.fillVisibleChanged.connect(self.view.set_fill_visible)
        # トグルボタンの見た目を状態に追従させる(ショートカット操作でも更新される)
        self.state.overlayVisibleChanged.connect(self._overlay_btn.setChecked)
        self.state.fillVisibleChanged.connect(self._fill_btn.setChecked)

    # --- 状態 -> 表示 --------------------------------------------------------
    def _load_image(self, index: int) -> None:
        dataset = self.state.dataset
        image = dataset.images[index]
        path = dataset.image_path(image)

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.statusBar().showMessage(f"画像を読み込めません: {path}")
            return

        self.view.set_image(pixmap)
        self._refresh_overlays()
        self.action_bar.set_active(False)

    def _refresh_overlays(self) -> None:
        """現在画像のオーバーレイと一覧・情報表示を作り直す(画像は再読込しない)。"""
        dataset = self.state.dataset
        image = self.state.current_image()
        annotations = self.state.current_annotations()

        self.view.set_overlays(annotations, show_fill=self.state.fill_visible)
        self.view.set_overlay_visible(self.state.overlay_visible)
        self.panel.set_annotations(annotations, dataset.category_name)

        if image is not None:
            self._info_label.setText(
                f"{image.file_name}   "
                f"[{self.state.image_index + 1}/{len(dataset.images)}]   "
                f"インスタンス数: {len(annotations)}"
            )

    def _apply_selection(self, indices) -> None:
        self.view.set_selection(indices)
        self.panel.set_selection(indices)
        self.action_bar.set_active(bool(indices))

    # --- ユーザー操作 -> 状態 -------------------------------------------------
    def _on_instance_clicked(self, index: int, additive: bool) -> None:
        if additive:
            self.state.toggle(index)
        else:
            self.state.select(index)

    def _on_rect_selected(self, indices) -> None:
        # 矩形選択は常に現在の選択へ追加する
        self.state.set_selection(indices, additive=True)

    def _on_panel_selection(self, rows) -> None:
        self.state.set_selection(rows)
        if len(rows) == 1:
            # 一覧から単一選択したときだけ、そのインスタンスへビューを寄せる
            self.view.center_on_instance(rows[0])

    def _delete_selected(self) -> None:
        count = len(self.state.selected_indices)
        if count == 0:
            return
        # JSON へ上書き保存する破壊的操作なので確認する
        reply = QMessageBox.question(
            self,
            "インスタンスの削除",
            f"選択中の {count} 件のインスタンスを削除して保存します。よろしいですか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.state.delete_selected()
