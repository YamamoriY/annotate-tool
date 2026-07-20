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
from PySide6.QtCore import Qt, QTimer

from annotate_tool import style
from annotate_tool.coco_data import CocoDataset
from annotate_tool.state import ViewerState
from annotate_tool.tools import Tool
from annotate_tool.widgets.action_bar import FloatingActionBar
from annotate_tool.widgets.add_bar import AddBar
from annotate_tool.widgets.control_group import ControlGroup
from annotate_tool.widgets.image_view import ImageView
from annotate_tool.widgets.instance_panel import InstancePanel
from annotate_tool.widgets.side_panel import SidePanel
from annotate_tool.widgets.tool_panel import ToolPanel


class ViewerWindow(QMainWindow):
    def __init__(self, dataset: CocoDataset):
        super().__init__()
        self.state = ViewerState(dataset, self)
        self._did_initial_fit = False
        self._painting_started = False  # 追加モードで塗り始めたか(上部ボタン制御用)
        self._save_dirty = False  # 未保存の変更があるか(遅延保存用)

        self.setWindowTitle("COCO Segmentation Viewer")
        self.resize(*style.WINDOW_SIZE)

        self.view = ImageView(self)
        self.setCentralWidget(self.view)
        self.action_bar = FloatingActionBar(self.view)
        self.add_bar = AddBar(self.view)
        self.tool_panel = ToolPanel(self.view)  # 左上。追加モード中だけ出す

        self.panel = InstancePanel(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.panel)

        # 右側は操作パネル(左の一覧と同じ幅を確保)。移動・表示の操作を置く。
        self.side_panel = SidePanel("操作", parent=self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.side_panel)

        self._build_actions()
        self._build_side_controls()

        self.setStatusBar(QStatusBar(self))
        self._saving_label = QLabel()  # 右下の「保存中…」表示(遅延保存)
        self._saving_label.setStyleSheet(style.SAVING_LABEL_QSS)
        self.statusBar().addPermanentWidget(self._saving_label)
        self._info_label = QLabel()
        self.statusBar().addPermanentWidget(self._info_label)

        self._connect_signals()

        if self.state.dataset.images:
            self._load_image(self.state.image_index)
        else:
            self.statusBar().showMessage("画像がありません")

        self._update_top_bar()  # 起動時は「追加」を表示

    def showEvent(self, event) -> None:
        # 初回表示までビューポートは最終サイズにならないため、表示後に一度フィットする
        # (__init__ 内の fit は起動時のサイズを基準にしてしまいずれる)。
        super().showEvent(event)
        if not self._did_initial_fit:
            self._did_initial_fit = True
            self.view.fit()

    # --- 組み立て -----------------------------------------------------------
    def _build_actions(self) -> None:
        def make(text: str, keys: list[str], slot) -> QAction:
            action = QAction(text, self)
            action.setShortcuts([QKeySequence(k) for k in keys])
            action.triggered.connect(slot)
            self.addAction(action)  # ツールバー未追加でもショートカットを有効にする
            return action

        # ショートカットのみ(ボタンはビュー上の浮動バーが担う)。
        make("前", ["Left"], self.state.prev_image)
        make("次", ["Right", "D", "Space"], self.state.next_image)
        make("追加", ["A"], self._on_add_shortcut)
        make("修正", ["E"], self._edit_selected)
        make("フィット", ["F"], self.view.fit)
        make("オーバーレイ", ["V"], self.state.toggle_overlay)
        make("塗り", ["B"], self.state.toggle_fill)
        make("選択解除 / 追加取消", ["Esc"], self._on_escape)
        make("確定 / パスを閉じる", ["Return", "Enter"], self._confirm_add)
        make("頂点を取消", ["Ctrl+Z", "Backspace"], self._undo_path_point)
        make("削除", ["Delete"], self._delete_selected)

    def _build_side_controls(self) -> None:
        """右パネルに「画像の移動」と「表示」の操作グループを積む。"""
        nav = ControlGroup("画像の移動")
        nav.add_row(
            [("◀ 前 (←)", self.state.prev_image), ("次 ▶ (→)", self.state.next_image)]
        )
        self.side_panel.add_widget(nav)

        guide = ControlGroup("操作方法")
        guide.add_text("左ドラッグ： 範囲選択")
        guide.add_text("中ドラッグ： 画像の移動")
        guide.add_text("ホイール： ズーム")
        self.side_panel.add_widget(guide)

        display = ControlGroup("表示")
        display.add_button("フィット (F)", self.view.fit)
        self._overlay_btn = display.add_button(
            "オーバーレイ (V)", self.state.toggle_overlay, checkable=True
        )
        self._fill_btn = display.add_button("塗り (B)", self.state.toggle_fill, checkable=True)
        self._overlay_btn.setChecked(self.state.overlay_visible)
        self._fill_btn.setChecked(self.state.fill_visible)
        self.side_panel.add_widget(display)

        settings = ControlGroup("設定")
        self._confirm_delete_box = settings.add_checkbox("削除時に確認する", checked=True)
        self.side_panel.add_widget_bottom(settings)

    def _connect_signals(self) -> None:
        # ユーザー操作 -> 状態
        self.view.instanceClicked.connect(self._on_instance_clicked)
        self.view.rectSelected.connect(self._on_rect_selected)
        self.view.backgroundClicked.connect(self.state.deselect)
        self.view.paintStarted.connect(self._on_paint_started)
        self.view.paintCleared.connect(self._on_paint_cleared)
        self.panel.selectionChanged.connect(self._on_panel_selection)
        self.action_bar.deselectClicked.connect(self.state.deselect)
        self.action_bar.editClicked.connect(self._edit_selected)
        self.action_bar.deleteClicked.connect(self._delete_selected)
        self.add_bar.addClicked.connect(self.state.enter_add_mode)
        self.add_bar.cancelClicked.connect(self.state.cancel_add_mode)
        self.tool_panel.toolChanged.connect(self.view.set_tool)
        self.tool_panel.radiusChanged.connect(self.view.set_radius)
        self.add_bar.confirmClicked.connect(self._confirm_add)

        # 状態 -> 表示
        self.state.imageChanged.connect(self._load_image)
        self.state.selectionChanged.connect(self._apply_selection)
        self.state.annotationsChanged.connect(self._refresh_overlays)
        self.state.overlayVisibleChanged.connect(self.view.set_overlay_visible)
        self.state.fillVisibleChanged.connect(self.view.set_fill_visible)
        self.state.addModeChanged.connect(self._on_add_mode_changed)
        self.state.saveRequested.connect(self._schedule_save)
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
        # 「修正」は単一選択のときだけ(どれを塗り直すか決まるのはそのときだけ)
        self.action_bar.set_active(bool(indices), can_edit=len(indices) == 1)
        self._update_top_bar()

    # --- 塗りつぶし編集モード(新規追加 / 既存修正)----------------------------
    def _on_add_mode_changed(self, active: bool) -> None:
        # 修正モードなら、対象の形をマスクへ焼いた状態でビューを立ち上げる
        edit_index = self.state.edit_index
        self.view.set_add_mode(
            active,
            edit_index=edit_index,
            edit_annotation=self.state.editing_annotation(),
        )
        # 編集中は一覧・サイドパネルの操作(選択・画像送り)を止める
        self.panel.setEnabled(not active)
        self.side_panel.setEnabled(not active)
        if active:
            # 修正は既に塗られた状態から始まるので、最初から「確定」を出す
            self._painting_started = edit_index is not None
            entry = self._entry_tool()
            self.tool_panel.set_tool(entry)
            self.view.set_tool(entry)
        self.tool_panel.set_active(active)
        self._update_top_bar()

    def _entry_tool(self) -> Tool:
        """編集モードに入るときのツール。前回の選択を引き継ぐ。

        引き継ぐのは「描く側」(ブラシ / パス)だけ。消しゴムのまま入ると、まだ何も
        塗られていないマスクを消そうとして何も起きず戸惑うため、ブラシへ戻す。
        ツールパネルはモードを抜けても選択状態を保持しているので、そこから読む。
        """
        tool = self.tool_panel.tool()
        return Tool.BRUSH if tool is Tool.ERASER else tool

    def _on_add_shortcut(self) -> None:
        # A キーは「追加」ボタンが出ているとき(通常時・未選択)だけ有効にする
        if not self.state.add_mode and not self.state.selected_indices:
            self.state.enter_add_mode()

    def _edit_selected(self) -> None:
        """選択中の1件を塗り直すモードへ入る。

        E キーからも呼ばれるため、「修正」ボタンが出ている状況(編集中でなく
        単一選択)に限る。
        """
        indices = self.state.selected_indices
        if not self.state.add_mode and len(indices) == 1:
            self.state.enter_edit_mode(indices[0])

    def _on_paint_started(self) -> None:
        self._painting_started = True
        self._update_top_bar()  # 塗り始めたら「確定」を出す

    def _on_paint_cleared(self) -> None:
        self._painting_started = False
        self._update_top_bar()  # 消し切ったら「確定」を引っ込める

    def _undo_path_point(self) -> None:
        """作図中のパスの直前の頂点を取り消す。

        編集モードで作図中のときだけ効く。将来アプリ全体の undo を入れるなら、
        作図中でない場合の分岐をここへ足すこと。
        """
        if self.state.add_mode:
            self.view.undo_path_point()

    def _confirm_add(self) -> None:
        """塗った領域を確定する(新規追加、または修正対象の差し替え)。

        パスを作図中なら、まず「パスを閉じる」を優先する。囲い終える前に確定して
        しまうと、打った頂点が黙って捨てられるため。
        """
        if not self.state.add_mode:
            return
        if self.view.has_path():
            self.view.close_path()
            return
        polygons = self.view.painted_polygons()
        if polygons:
            self.state.apply_painted(polygons)
        self.state.cancel_add_mode()

    def _on_escape(self) -> None:
        # 編集モード中は塗りを破棄して抜ける。通常時は選択解除。
        # ただしパスを作図中なら、まずパスだけを捨てる(モードは維持)。塗った内容まで
        # 巻き添えで消えると、囲み損ねただけで最初からやり直しになるため。
        if self.state.add_mode and self.view.has_path():
            self.view.cancel_path()
        elif self.state.add_mode:
            self.state.cancel_add_mode()
        else:
            self.state.deselect()

    def _update_top_bar(self) -> None:
        """上部ボタン(追加 / 確定)の表示を状態から決める。

        - 追加モード中: 常に「キャンセル」、塗り始めたら「確定」も並べる。
        - 通常時: 未選択なら「追加」、選択中(範囲選択含む)は「追加」を隠す。
        """
        if self.state.add_mode:
            self.add_bar.show_adding(self._painting_started)
        elif self.state.selected_indices:
            self.add_bar.hide_all()
        else:
            self.add_bar.show_add()

    # --- 遅延保存 -----------------------------------------------------------
    def _schedule_save(self) -> None:
        """保存要求を受けたら「保存中…」を出し、描画を挟んでから遅延保存する。"""
        self._save_dirty = True
        self._saving_label.setText("保存中…")
        # 通常画面と「保存中…」を先に描画させるため、少し遅らせて保存する
        QTimer.singleShot(style.SAVE_DELAY_MS, self._do_save)

    def _do_save(self) -> None:
        if not self._save_dirty:
            return
        self._save_dirty = False
        self.state.flush_save()  # 重い処理(この間だけ短時間ブロック)
        # 保存中に新たな要求が来ていれば、それは別の singleShot が拾う
        if not self._save_dirty:
            self._saving_label.setText("保存しました")
            QTimer.singleShot(style.SAVE_DONE_HOLD_MS, self._clear_saved_label)

    def _clear_saved_label(self) -> None:
        # 表示中に次の保存が始まっていたら消さない
        if not self._save_dirty:
            self._saving_label.clear()

    def closeEvent(self, event) -> None:
        # 遅延保存が残ったまま終了すると変更が失われるため、確実に書き出す
        if self._save_dirty:
            self._save_dirty = False
            self.state.flush_save()
        super().closeEvent(event)

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
        if not self._confirm_delete_box.isChecked():
            self.state.delete_selected()
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
