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
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar, QToolBar
from PySide6.QtCore import Qt

from annotate_tool import style
from annotate_tool.coco_data import CocoDataset
from annotate_tool.state import ViewerState
from annotate_tool.widgets.deselect_button import DeselectButton
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
        self.deselect_btn = DeselectButton(self.view)

        self.panel = InstancePanel(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.panel)

        self._build_actions()
        self._build_toolbar()

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

        self.act_prev = make("◀ 前 (←)", ["Left", "A"], self.state.prev_image)
        self.act_next = make("次 (→) ▶", ["Right", "D", "Space"], self.state.next_image)
        self.act_fit = make("フィット (F)", ["F"], self.view.fit)
        self.act_overlay = make("オーバーレイ (V)", ["V"], self.state.toggle_overlay)
        self.act_fill = make("塗り (B)", ["B"], self.state.toggle_fill)
        self.act_deselect = make("選択解除", ["Esc"], self.state.deselect)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Navigation", self)
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.act_prev)
        tb.addAction(self.act_next)
        tb.addSeparator()
        tb.addAction(self.act_fit)
        tb.addAction(self.act_overlay)
        tb.addAction(self.act_fill)

    def _connect_signals(self) -> None:
        # ユーザー操作 -> 状態
        self.view.instanceClicked.connect(self._on_instance_clicked)
        self.view.rectSelected.connect(self._on_rect_selected)
        self.panel.selectionChanged.connect(self._on_panel_selection)
        self.deselect_btn.clicked.connect(self.state.deselect)

        # 状態 -> 表示
        self.state.imageChanged.connect(self._load_image)
        self.state.selectionChanged.connect(self._apply_selection)
        self.state.overlayVisibleChanged.connect(self.view.set_overlay_visible)
        self.state.fillVisibleChanged.connect(self.view.set_fill_visible)

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

        annotations = self.state.current_annotations()
        self.view.set_overlays(annotations, show_fill=self.state.fill_visible)
        self.view.set_overlay_visible(self.state.overlay_visible)
        self.panel.set_annotations(annotations, dataset.category_name)
        self.deselect_btn.set_active(False)

        self._info_label.setText(
            f"{image.file_name}   "
            f"[{index + 1}/{len(dataset.images)}]   "
            f"インスタンス数: {len(annotations)}"
        )

    def _apply_selection(self, indices) -> None:
        self.view.set_selection(indices)
        self.panel.set_selection(indices)
        self.deselect_btn.set_active(bool(indices))

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
