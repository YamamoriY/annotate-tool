"""アプリケーション状態の一元管理。

現在の画像・選択中インスタンス・表示フラグは、すべてこの ViewerState だけが
持つ(single source of truth)。ウィジェットは状態を保持せず、変更シグナルを
受けて表示を更新し、ユーザー操作は ViewerState のメソッド呼び出しに変換する。

これにより「ビューと一覧の選択がずれる」類のバグを構造的に防ぎ、
編集機能などを追加する際も状態の置き場所が明確になる。
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable

from PySide6.QtCore import QObject, Signal

from annotate_tool.coco_data import Annotation, CocoDataset, ImageEntry


class ViewerState(QObject):
    """ビューアの状態と、それを変更する操作(コマンド)を提供する。"""

    imageChanged = Signal(int)  # 現在画像の index(同じ画像の再読み込みでも発火)
    # 選択インスタンスの index 集合(ソート済み tuple)。非選択は空 tuple。
    selectionChanged = Signal(object)
    # 現在画像のアノテーション集合が変化した(削除など。画像自体は再読込しない)
    annotationsChanged = Signal()
    overlayVisibleChanged = Signal(bool)
    fillVisibleChanged = Signal(bool)
    blinkEnabledChanged = Signal(bool)  # オーバーレイの点滅表示の ON/OFF
    addModeChanged = Signal(bool)  # 追加(塗りつぶし)モードの ON/OFF
    # 未保存の変更が生じた(実際のディスク保存は呼び出し側が遅延して行う)
    saveRequested = Signal()

    datasetChanged = Signal()  # 別の COCO JSON を開いた(画像・一覧の総入れ替え)

    def __init__(self, dataset: CocoDataset, parent: QObject | None = None):
        super().__init__(parent)
        self._dataset = dataset
        self._image_index = 0
        self._selected: set[int] = set()
        self._overlay_visible = True
        self._fill_visible = True
        # 点滅は常用する見せ方ではなく「今そこを確かめたい」ときの道具なので既定は OFF。
        # 点滅の位相(いま見えているか)はここには持たない。保存にもテストにも
        # 関わらない純粋な描画の都合であり、持たせると状態が時間依存になるため。
        self._blink_enabled = False
        self._add_mode = False
        # 修正中のインスタンス index(新規追加中は None)
        self._edit_index: int | None = None

        # 面積昇順の索引(現在画像ぶん)。しきい値選択で使う。作り直しの契機は
        # 自分のシグナルから拾い、無効化の責任を呼び出し側へ散らさない。
        self._area_index: tuple[list[float], list[int]] | None = None
        self.imageChanged.connect(self._invalidate_area_index)
        self.annotationsChanged.connect(self._invalidate_area_index)

    # --- 参照系 -------------------------------------------------------------
    @property
    def dataset(self) -> CocoDataset:
        return self._dataset

    def set_dataset(self, dataset: CocoDataset) -> None:
        """開いているデータセットを差し替える。

        画像も選択も別物になるので、状態は起動直後と同じところまで戻す。
        表示フラグ(オーバーレイ・塗り)はユーザーの好みなので引き継ぐ。
        通知は datasetChanged 一本にまとめる。選択やアノテーションの変化を
        個別に出すと、受け取り側が「もう無い画像」を見に行くことになるため。
        """
        self.cancel_add_mode()  # 塗りかけを別データへ持ち越さない
        self._dataset = dataset
        self._image_index = 0
        self._selected = set()
        self._invalidate_area_index()
        self.datasetChanged.emit()

    @property
    def image_index(self) -> int:
        return self._image_index

    @property
    def selected_indices(self) -> tuple[int, ...]:
        return tuple(sorted(self._selected))

    def is_selected(self, index: int) -> bool:
        return index in self._selected

    @property
    def overlay_visible(self) -> bool:
        return self._overlay_visible

    @property
    def fill_visible(self) -> bool:
        return self._fill_visible

    @property
    def blink_enabled(self) -> bool:
        return self._blink_enabled

    @property
    def add_mode(self) -> bool:
        """塗りつぶし編集モード中か(新規追加・既存修正のどちらも含む)。"""
        return self._add_mode

    @property
    def edit_index(self) -> int | None:
        """修正中のインスタンス index。新規追加中・非編集中は None。"""
        return self._edit_index

    def current_image(self) -> ImageEntry | None:
        if not self._dataset.images:
            return None
        return self._dataset.images[self._image_index]

    def current_annotations(self) -> list[Annotation]:
        image = self.current_image()
        if image is None:
            return []
        return self._dataset.annotations_for(image.id)

    # --- 画像ナビゲーション ---------------------------------------------------
    def set_image_index(self, index: int) -> None:
        """画像を切り替える。切り替え時に選択は解除される。"""
        if not self._dataset.images:
            return
        self._image_index = index % len(self._dataset.images)
        had_selection = bool(self._selected)
        self._selected = set()
        self.imageChanged.emit(self._image_index)
        if had_selection:
            self.selectionChanged.emit(())

    def next_image(self) -> None:
        self.set_image_index(self._image_index + 1)

    def prev_image(self) -> None:
        self.set_image_index(self._image_index - 1)

    # --- 選択 ---------------------------------------------------------------
    def _valid(self, index: int) -> bool:
        return 0 <= index < len(self.current_annotations())

    def _apply(self, selection: set[int]) -> None:
        """選択集合を差し替え、変化があればシグナルを出す。"""
        if selection == self._selected:
            return
        self._selected = selection
        self.selectionChanged.emit(tuple(sorted(selection)))

    def select(self, index: int) -> None:
        """その1件だけを選択(置換)。範囲外/-1 は全解除。"""
        self._apply({index} if self._valid(index) else set())

    def toggle(self, index: int) -> None:
        """指定インスタンスを選択に追加、既に選択済みなら解除する。"""
        if not self._valid(index):
            return
        selection = set(self._selected)
        selection.discard(index) if index in selection else selection.add(index)
        self._apply(selection)

    def set_selection(self, indices: Iterable[int], additive: bool = False) -> None:
        """複数インスタンスを選択する。additive=False は置換、True は和集合。"""
        chosen = {i for i in indices if self._valid(i)}
        self._apply((self._selected | chosen) if additive else chosen)

    def deselect(self) -> None:
        self._apply(set())

    # --- 面積によるしきい値選択 ------------------------------------------------
    def _invalidate_area_index(self) -> None:
        self._area_index = None

    def _build_area_index(self) -> tuple[list[float], list[int]]:
        """現在画像のインスタンスを面積の昇順に並べた索引を作る。

        戻り値は (昇順の面積列, 対応する index 列)。面積は COCO の area を
        そのまま使う(ポリゴンからの再計算はしない)。
        """
        if self._area_index is None:
            pairs = sorted(
                (ann.area, i) for i, ann in enumerate(self.current_annotations())
            )
            self._area_index = ([a for a, _ in pairs], [i for _, i in pairs])
        return self._area_index

    def indices_with_area_at_most(self, threshold: float) -> list[int]:
        """面積が threshold 以下のインスタンス index を返す。

        面積昇順の索引を二分探索するので、走査するのは該当ぶんだけで済む。
        """
        areas, order = self._build_area_index()
        return order[: bisect_right(areas, threshold)]

    # --- 塗りつぶし編集モード(新規追加 / 既存修正)----------------------------
    def enter_add_mode(self) -> None:
        """新規インスタンスを塗って追加するモードへ入る(選択は解除される)。"""
        if self._add_mode:
            return
        self._edit_index = None
        self._add_mode = True
        self._apply(set())  # 選択があれば解除(selectionChanged を出す)
        self.addModeChanged.emit(True)

    def enter_edit_mode(self, index: int) -> None:
        """既存インスタンスの形を塗り直すモードへ入る。

        追加モードとの違いは、確定時に新規追加ではなく差し替えになる点だけ。
        選択はいったん解除し(暗幕や強調が編集の邪魔になるため)、モードを抜けた
        ときに元へ戻す。
        """
        if self._add_mode or not self._valid(index):
            return
        self._edit_index = index
        self._add_mode = True
        self._apply(set())
        self.addModeChanged.emit(True)

    def cancel_add_mode(self) -> None:
        """編集モードを抜ける(塗った内容の確定/破棄は呼び出し側の責務)。

        修正モードだった場合は、対象インスタンスの選択を復帰させる。
        """
        if not self._add_mode:
            return
        index = self._edit_index
        self._edit_index = None
        self._add_mode = False
        self.addModeChanged.emit(False)
        if index is not None and self._valid(index):
            self._apply({index})

    def editing_annotation(self) -> Annotation | None:
        """修正中のアノテーション(新規追加中・非編集中は None)。"""
        if self._edit_index is None or not self._valid(self._edit_index):
            return None
        return self.current_annotations()[self._edit_index]

    def apply_painted(self, polygons: list[list[float]]) -> bool:
        """塗ってできたポリゴン列を確定する。

        修正モードなら対象アノテーションの形を差し替え、そうでなければ新規追加する。
        反映できたら True。現在画像がない/ポリゴンが空なら何もせず False。
        ディスク保存はここでは行わず saveRequested を出す(呼び出し側が遅延保存する)。
        """
        image = self.current_image()
        if image is None or not polygons:
            return False
        target = self.editing_annotation()
        if self._edit_index is not None and target is None:
            return False  # 修正中に対象が失われた(通常は起きない)
        if target is not None:
            self._dataset.update_annotation(target, polygons)
        else:
            self._dataset.add_annotation(image.id, polygons)
        self.annotationsChanged.emit()
        self.saveRequested.emit()
        return True

    def flush_save(self) -> None:
        """保留中の変更をディスクへ書き出す(重い処理。遅延実行される想定)。"""
        self._dataset.save()

    # --- 編集 ---------------------------------------------------------------
    def delete_selected(self) -> None:
        """選択中のインスタンスを削除し、JSON へ保存する。

        削除後は選択を解除し、annotationsChanged(表示の作り直し)と
        selectionChanged(選択解除)を通知する。選択が空なら何もしない。
        """
        current = self.current_annotations()
        targets = [current[i] for i in sorted(self._selected) if self._valid(i)]
        if not targets:
            return
        self._dataset.delete_annotations(targets)
        self._dataset.save()
        self._selected = set()
        self.annotationsChanged.emit()
        self.selectionChanged.emit(())

    # --- 表示トグル -----------------------------------------------------------
    def toggle_overlay(self) -> None:
        self._overlay_visible = not self._overlay_visible
        self.overlayVisibleChanged.emit(self._overlay_visible)

    def toggle_fill(self) -> None:
        self._fill_visible = not self._fill_visible
        self.fillVisibleChanged.emit(self._fill_visible)

    def toggle_blink(self) -> None:
        self._blink_enabled = not self._blink_enabled
        self.blinkEnabledChanged.emit(self._blink_enabled)
