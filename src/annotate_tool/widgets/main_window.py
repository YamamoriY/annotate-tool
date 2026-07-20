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

from html import escape
from pathlib import Path

from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
)
from PySide6.QtCore import Qt, QTimer, QUrl

from annotate_tool import settings, shortcuts, style
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
    # ショートカットと、それが選ぶ描画ツール(ツールパネルの並びと同じ順)
    _TOOL_SHORTCUTS = (
        (shortcuts.TOOL_BRUSH, Tool.BRUSH),
        (shortcuts.TOOL_ERASER, Tool.ERASER),
        (shortcuts.TOOL_POLYGON, Tool.POLYGON),
    )

    def __init__(self, dataset: CocoDataset | None = None):
        super().__init__()
        # 何も渡されなければ空のデータセットで立ち上げる。開くファイルは
        # 右パネルの「開く」で後から決められるので、起動を止める理由はない。
        self.state = ViewerState(dataset or CocoDataset(), self)
        self.settings = settings.load()
        # キー割り当ては設定ファイルで差し替えられる。壊れた行は既定へ戻し、
        # 理由は起動後にステータスバーへ出す(起動は止めない)。
        self.keymap, self._keymap_problems = shortcuts.resolve(
            settings.shortcut_overrides(self.settings)
        )
        # 何が書けるのか分かるよう、未記載の項目を既定値で書き出しておく
        settings.write_missing_shortcuts(self.settings, self.keymap.as_settings())
        self._did_initial_fit = False
        self._painting_started = False  # 追加モードで塗り始めたか(上部ボタン制御用)
        self._save_dirty = False  # 未保存の変更があるか(遅延保存用)
        # 面積スライダー起因の選択変更を処理中か(つまみの巻き戻しと再入を防ぐ)
        self._area_syncing = False

        self.setWindowTitle("COCO Segmentation Viewer")
        self.resize(*style.WINDOW_SIZE)

        self.view = ImageView(self)
        self.setCentralWidget(self.view)
        self.action_bar = FloatingActionBar(self.view, self.keymap)
        self.add_bar = AddBar(self.view, self.keymap)
        # 左上。追加モード中だけ出す
        self.tool_panel = ToolPanel(self.view, self.keymap)

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

        self._connect_signals()

        self._on_dataset_changed()  # 初期表示も「開いた直後」と同じ道を通す

        if self._keymap_problems:
            # 黙って既定へ戻すと「設定したのに効かない」と受け取られるため必ず出す。
            # 画像の読み込みより後に出して、こちらを残す。
            self.statusBar().showMessage(
                "ショートカット設定: " + " / ".join(self._keymap_problems)
            )

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
        """定義表(shortcuts)の各項目へ、このウィンドウの処理を結びつける。

        キーと動作名は表側が持つ。ここが決めるのは「どれが何を呼ぶか」だけ。
        """

        self._actions: dict[str, QAction] = {}

        def make(shortcut: shortcuts.Shortcut, slot) -> QAction:
            action = QAction(shortcut.label, self)
            action.setShortcuts([QKeySequence(k) for k in self.keymap.keys(shortcut)])
            action.triggered.connect(slot)
            self.addAction(action)  # ツールバー未追加でもショートカットを有効にする
            self._actions[shortcut.id] = action
            return action

        # ショートカットのみ(ボタンはビュー上の浮動バーが担う)。
        make(shortcuts.PREV, self.state.prev_image)
        make(shortcuts.NEXT, self.state.next_image)
        make(shortcuts.ADD, self._on_add_shortcut)
        make(shortcuts.EDIT, self._edit_selected)
        make(shortcuts.FIT, self.view.fit)
        make(shortcuts.OVERLAY, self.state.toggle_overlay)
        make(shortcuts.FILL, self.state.toggle_fill)
        make(shortcuts.BLINK, self.state.toggle_blink)
        make(shortcuts.ESCAPE, self._on_escape)
        make(shortcuts.CONFIRM, self._confirm_add)
        make(shortcuts.UNDO_POINT, self._undo_path_point)
        make(shortcuts.DELETE, self._delete_selected)
        for shortcut, tool in self._TOOL_SHORTCUTS:
            # triggered は checked を渡してくるので受け流す
            make(shortcut, lambda _checked=False, t=tool: self._select_tool(t))

        # 「その操作がいま可能か」の唯一の出どころ。
        # キー(QAction の有効/無効)もボタンの表示もここだけを見る。以前は同じ条件を
        # スロット側とボタン側で別々に書いていたため、片方だけ直すと食い違った。
        # ここに無いものは常に可能(フィット・表示切替・Esc)。
        self._enabled = {
            # 編集モード中の画像送りは禁止(送ってしまうと塗りかけが失われる)
            shortcuts.PREV.id: lambda: not self.state.add_mode,
            shortcuts.NEXT.id: lambda: not self.state.add_mode,
            # 塗る先の画像が無ければ追加もできない(データ未読込のとき)
            shortcuts.ADD.id: lambda: (
                not self.state.add_mode
                and not self.state.selected_indices
                and self.state.current_image() is not None
            ),
            # 塗り直す対象が決まるのは単一選択のときだけ
            shortcuts.EDIT.id: lambda: (
                not self.state.add_mode and len(self.state.selected_indices) == 1
            ),
            # 確定するものが無いうちは効かせない(「確定」ボタンが出る条件と同じ)。
            # 何も塗らずに押して黙ってモードが終わると、何が起きたのか分からない。
            # 抜けたいときは Esc。
            shortcuts.CONFIRM.id: lambda: self.state.add_mode
            and (self._painting_started or self.view.has_path()),
            shortcuts.UNDO_POINT.id: lambda: (
                self.state.add_mode and self.view.has_path()
            ),
            shortcuts.DELETE.id: lambda: bool(self.state.selected_indices),
        }
        # ツールの持ち替えは、ツールパネルが出ている追加モード中だけ
        for shortcut, _tool in self._TOOL_SHORTCUTS:
            self._enabled[shortcut.id] = lambda: self.state.add_mode

    def _can(self, shortcut: shortcuts.Shortcut) -> bool:
        """その操作がいま可能か。判断は `_enabled` の1箇所だけが持つ。"""
        predicate = self._enabled.get(shortcut.id)
        return predicate() if predicate else True

    def _update_actions(self) -> None:
        """各ショートカットの有効/無効を現在の状態から決め直す。

        無効な QAction はキーを押しても発火しないため、スロット側で条件を
        再確認する必要はない(ボタンからも呼ばれるものだけ `_can` で門を残す)。
        """
        for shortcut in shortcuts.ALL:
            self._actions[shortcut.id].setEnabled(self._can(shortcut))

    def _build_side_controls(self) -> None:
        """右パネルに現在の画像の情報と、操作グループを積む。"""
        # 最上段は「どのデータを開いているか」。ここが決まらないと他の操作は
        # 何の意味も持たないので、画像より上に置く。
        file_group = ControlGroup("ファイル")
        file_group.add_button("COCO JSON を開く…", self._open_dataset_dialog)
        self._path_label = QLabel()
        self._path_label.setStyleSheet(style.CONTROL_HELP_QSS)
        self._path_label.setWordWrap(True)  # パネル幅に収まらないため折り返す
        # 表示専用。ただし選択はできるようにする(パスを他所へ貼れると助かる)。
        self._path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_group.add_widget(self._path_label)
        self.side_panel.add_widget(file_group)

        # 次は「いまどの画像か」と、その送り。見る対象と移動手段をまとめる。
        image_group = ControlGroup("画像")
        self._info_label = QLabel()
        self._info_label.setStyleSheet(style.INFO_LABEL_QSS)
        self._info_label.setWordWrap(True)  # パネル幅では収まらないため折り返す
        image_group.add_widget(self._info_label)
        image_group.add_row(
            [
                (self.keymap.text(shortcuts.PREV, prefix="◀"), self.state.prev_image),
                (self.keymap.text(shortcuts.NEXT, suffix="▶"), self.state.next_image),
            ]
        )
        self.side_panel.add_widget(image_group)

        guide = ControlGroup("操作方法")
        guide.add_text("左ドラッグ： 範囲選択")
        guide.add_text("中ドラッグ： 画像の移動")
        guide.add_text("ホイール： ズーム")
        self.side_panel.add_widget(guide)

        display = ControlGroup("表示")
        display.add_button(self.keymap.text(shortcuts.FIT), self.view.fit)
        self._overlay_btn = display.add_button(
            self.keymap.text(shortcuts.OVERLAY), self.state.toggle_overlay, checkable=True
        )
        self._fill_btn = display.add_button(
            self.keymap.text(shortcuts.FILL), self.state.toggle_fill, checkable=True
        )
        # 点滅も「オーバーレイの見せ方」の一つなので、同じ並びの同じ形で置く。
        self._blink_btn = display.add_button(
            self.keymap.text(shortcuts.BLINK), self.state.toggle_blink, checkable=True
        )
        self._overlay_btn.setChecked(self.state.overlay_visible)
        self._fill_btn.setChecked(self.state.fill_visible)
        self._blink_btn.setChecked(self.state.blink_enabled)
        self.side_panel.add_widget(display)

        # 見出しがそのまま操作の説明になっているので、注釈行は置かない。
        select = ControlGroup("面積で選択")
        self._area_slider, self._area_count_label = select.add_slider(
            minimum=0,
            maximum=style.AREA_SLIDER_STEPS,
            value=0,
            formatter=lambda pos: style.format_area(style.area_from_slider(pos)),
        )
        self.side_panel.add_widget(select)

        setting_group = ControlGroup("設定")
        self._confirm_delete_box = setting_group.add_checkbox(
            "削除時に確認メッセージを表示",
            checked=settings.confirm_delete(self.settings),
        )
        # 切り替えた時点で書き出す(終了時にまとめて書くと、強制終了で失われる)
        self._confirm_delete_box.toggled.connect(
            lambda checked: settings.set_confirm_delete(self.settings, checked)
        )
        # ↗ は「別の場所(エクスプローラー)が開く」ことを示す慣用のしるし
        setting_group.add_button("キーボードショートカット ↗", self._open_settings_folder)
        self.side_panel.add_widget_bottom(setting_group)

    # --- データセットを開く ---------------------------------------------------
    def _open_dataset_dialog(self) -> None:
        """COCO JSON をファイル選択で開く。

        初期位置は今開いているファイルの隣。連番や派生ファイルを続けて開く
        ことが多く、毎回同じ場所までたどり直すのは無駄なため。
        """
        current = self.state.dataset.json_path
        start = str(current.parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "COCO JSON を開く", start, "COCO JSON (*.json);;すべてのファイル (*)"
        )
        if path:
            self.open_dataset(Path(path))

    def open_dataset(self, path: Path) -> bool:
        """COCO JSON を読み込んで表示を総入れ替えする。成功したら True。

        読み込みに失敗しても今の内容は保ったままにする(壊れたファイルを
        選んだだけで作業中の状態を失うのは割に合わない)。
        """
        try:
            dataset = CocoDataset(path)
        except (OSError, ValueError) as exc:
            # ValueError は JSONDecodeError を含む(不正な JSON)
            self.statusBar().showMessage(f"開けません: {path} ({exc})")
            return False

        # 遅延保存が残っていると、切り替えた後に前のデータへ書きに行ってしまう
        self._flush_pending_save()
        self.state.set_dataset(dataset)
        # 次の起動でこれを開き直す。切り替えた時点で書き出す(終了時にまとめて
        # 書くと、強制終了で失われる)。
        settings.set_last_json(self.settings, str(path))
        return True

    def _on_dataset_changed(self) -> None:
        """データセット差し替え後の表示の作り直し。"""
        self._update_path_label()
        if self.state.dataset.images:
            self._load_image(self.state.image_index)
        else:
            # 前のデータの画像が残ると「開けた」ように見えてしまうので消す
            self.view.clear_image()
            self._refresh_overlays()
            self.statusBar().showMessage("画像がありません")
        self._apply_selection(self.state.selected_indices)

    def _update_path_label(self) -> None:
        path = self.state.dataset.json_path
        self._path_label.setText(escape(str(path)) if path else "未選択")

    def _open_settings_folder(self) -> None:
        """設定ファイルの置き場をエクスプローラーで開く。

        キー割り当ての変更は INI を直接編集する方式なので、まずファイルへ
        たどり着けることが要る(パスを覚えている人はいない)。

        ファイルではなくフォルダを開くのは、INI に紐づくアプリが環境によって
        違い、開いた先が編集できるとは限らないため。
        """
        settings.flush(self.settings)  # 未書き出しのまま開くと空フォルダに見える
        folder = Path(self.settings.fileName()).parent
        folder.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            # 開けなくても、パスさえ分かれば手でたどれる
            self.statusBar().showMessage(f"設定フォルダを開けません: {folder}")

    def _connect_signals(self) -> None:
        # ユーザー操作 -> 状態
        self.view.instanceClicked.connect(self._on_instance_clicked)
        self.view.rectSelected.connect(self._on_rect_selected)
        self.view.backgroundClicked.connect(self.state.deselect)
        self.view.paintStarted.connect(self._on_paint_started)
        self.view.paintCleared.connect(self._on_paint_cleared)
        # 頂点の増減で「頂点を取消」の可否が変わる(マウス操作で起きるため通知が要る)
        self.view.pathChanged.connect(self._update_actions)
        self.panel.selectionChanged.connect(self._on_panel_selection)
        self.action_bar.deselectClicked.connect(self.state.deselect)
        self.action_bar.editClicked.connect(self._edit_selected)
        self.action_bar.deleteClicked.connect(self._delete_selected)
        self.add_bar.addClicked.connect(self.state.enter_add_mode)
        self.add_bar.cancelClicked.connect(self.state.cancel_add_mode)
        self.tool_panel.toolChanged.connect(self.view.set_tool)
        self.tool_panel.radiusChanged.connect(self.view.set_radius)
        self.add_bar.confirmClicked.connect(self._confirm_add)
        # 面積スライダーは「もう一つの選択ソース」。つまみを動かさず触っただけでも
        # 選び直せるよう sliderPressed も拾う。
        self._area_slider.valueChanged.connect(self._on_area_slider)
        self._area_slider.sliderPressed.connect(self._on_area_slider_pressed)
        self._area_slider.sliderReleased.connect(
            lambda: self.view.set_dim_forced(False)
        )

        # 状態 -> 表示
        self.state.datasetChanged.connect(self._on_dataset_changed)
        self.state.imageChanged.connect(self._load_image)
        self.state.selectionChanged.connect(self._apply_selection)
        self.state.annotationsChanged.connect(self._refresh_overlays)
        self.state.overlayVisibleChanged.connect(self.view.set_overlay_visible)
        self.state.fillVisibleChanged.connect(self.view.set_fill_visible)
        self.state.blinkEnabledChanged.connect(self.view.set_blink_enabled)
        self.state.addModeChanged.connect(self._on_add_mode_changed)
        self.state.saveRequested.connect(self._schedule_save)
        # トグルボタンの見た目を状態に追従させる(ショートカット操作でも更新される)
        self.state.overlayVisibleChanged.connect(self._overlay_btn.setChecked)
        self.state.fillVisibleChanged.connect(self._fill_btn.setChecked)
        self.state.blinkEnabledChanged.connect(self._blink_btn.setChecked)

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
            # 横長のステータスバーではなく縦長のパネルに出すため、行で分ける
            # (1行目=どの画像か、2行目=その中身)。行ごとに見た目を変えるので
            # HTML で組む。ファイル名は任意の文字列なのでエスケープする。
            self._info_label.setText(
                f"<b>{escape(image.file_name)}</b> "
                f"[{self.state.image_index + 1}/{len(dataset.images)}]"
                f"<br><span style='{style.INFO_SUB_HTML}'>"
                f"インスタンス数: {len(annotations)}</span>"
            )
        else:
            # 前のデータの画像名が残ると、何を見ているのか分からなくなる
            self._info_label.setText("画像がありません")

    def _apply_selection(self, indices) -> None:
        self.view.set_selection(indices)
        self.panel.set_selection(indices)
        # 「修正」は単一選択のときだけ(どれを塗り直すか決まるのはそのときだけ)
        self._update_actions()
        self.action_bar.set_active(bool(indices), can_edit=self._can(shortcuts.EDIT))
        self._update_top_bar()
        self._area_count_label.setText(f"{len(indices)}件" if indices else "")
        if not indices and not self._area_syncing:
            # 選択が解除されたらつまみも戻す(残すと、何も選ばれていないのに
            # 面積を指したままになり表示が嘘になる)。
            #
            # ただしスライダー操作の最中は戻さない。しきい値がまだ最小インスタンス
            # に届いていない間は選択が空になるので、そこで戻すとドラッグ中の
            # つまみを毎回 0 へ引き戻してしまう。
            self._area_slider.setValue(0)

    def _on_area_slider_pressed(self) -> None:
        """つまみを掴んだ時点で、動かさなくても選び直す(「触ったら始まる」)。"""
        if self.state.add_mode:
            return
        self.view.set_dim_forced(True)  # 操作中は選択が空でも暗いままにする
        self._on_area_slider(self._area_slider.value())

    def _on_area_slider(self, pos: int) -> None:
        """面積スライダーの値を選択へ反映する(既存の選択は置き換える)。

        出来上がるのは普通の複数選択なので、この後クリックで増減させたり
        Delete したりできる。手で編集した後にまたつまみを動かすと、しきい値から
        作り直される。
        """
        if self.state.add_mode or self._area_syncing:
            return
        threshold = style.area_from_slider(pos)
        self._area_syncing = True
        try:
            self.state.set_selection(self.state.indices_with_area_at_most(threshold))
        finally:
            self._area_syncing = False

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
            # 前回使ったツールをそのまま引き継ぐ(ツールパネルはモードを抜けても
            # 選択状態を保持しているので、そこから読む)
            self.view.set_tool(self.tool_panel.tool())
        self.tool_panel.set_active(active)
        self._update_top_bar()

    def _select_tool(self, tool: Tool) -> None:
        """ツールを持ち替える(1/2/3 キー)。

        パネルのボタンを押したときと同じ状態にするため、パネルとビューの両方へ
        伝える。ToolPanel.set_tool はシグナルを出さないので、ビューへは自分で
        渡す必要がある。
        """
        if not self._can(shortcuts.TOOL_BRUSH):  # 3つとも条件は同じ(追加モード中)
            return
        self.tool_panel.set_tool(tool)
        self.view.set_tool(tool)

    def _on_add_shortcut(self) -> None:
        if self._can(shortcuts.ADD):
            self.state.enter_add_mode()

    def _edit_selected(self) -> None:
        """選択中の1件を塗り直すモードへ入る。"""
        if self._can(shortcuts.EDIT):
            self.state.enter_edit_mode(self.state.selected_indices[0])

    def _on_paint_started(self) -> None:
        self._painting_started = True
        self._update_top_bar()  # 塗り始めたら「確定」を出す

    def _on_paint_cleared(self) -> None:
        self._painting_started = False
        self._update_top_bar()  # 消し切ったら「確定」を引っ込める

    def _undo_path_point(self) -> None:
        """作図中のパスの直前の頂点を取り消す。

        作図中のときだけ効く。将来アプリ全体の undo を入れるなら、
        作図中でない場合の分岐をここへ足すこと。
        """
        if self._can(shortcuts.UNDO_POINT):
            self.view.undo_path_point()

    def _confirm_add(self) -> None:
        """塗った領域を確定する(新規追加、または修正対象の差し替え)。

        パスを作図中なら、まず「パスを閉じる」を優先する。囲い終える前に確定して
        しまうと、打った頂点が黙って捨てられるため。
        """
        if not self._can(shortcuts.CONFIRM):
            return
        if self.view.has_path():
            self.view.close_path()
            return
        was_edit = self.state.editing_annotation() is not None
        polygons = self.view.painted_polygons()
        if polygons:
            self.state.apply_painted(polygons)
        self.state.cancel_add_mode()
        # 修正から抜けると対象が選択へ戻る(取消時は都合が良い)。確定したときは
        # 作業が済んだ合図として選択を外す。
        if was_edit:
            self.state.deselect()

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
        self._update_actions()
        if self.state.add_mode:
            self.add_bar.show_adding(self._painting_started)
        elif self._can(shortcuts.ADD):
            self.add_bar.show_add()
        else:
            self.add_bar.hide_all()

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

    def _flush_pending_save(self) -> None:
        """遅延保存が残っていれば、その場で書き出す。

        終了時や、対象データセットが入れ替わる直前など「後で書く」が
        成り立たなくなる場面で呼ぶ。
        """
        if self._save_dirty:
            self._save_dirty = False
            self.state.flush_save()

    def closeEvent(self, event) -> None:
        # 遅延保存が残ったまま終了すると変更が失われるため、確実に書き出す
        self._flush_pending_save()
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
        if not self._can(shortcuts.DELETE):
            return
        count = len(self.state.selected_indices)
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
