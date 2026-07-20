"""キーボードショートカットの定義表。

キーと動作名の唯一の出どころ。QAction もボタンの文字列もここから作る。

以前はボタン側に "修正 (E)" のような表記を直接書いていたため、キーを変えても
表示だけが古いまま残った。ボタンに書いてあるキーが実際には効かない、という
ずれはユーザーから見て直しようがないので、1箇所にまとめる。

将来ユーザーがキーを変えられるようにするときは、`id` を設定ファイルのキーに
して `keys` を差し替える。表示は `hint` 経由なので追随する。
"""

from __future__ import annotations

from dataclasses import dataclass

# QKeySequence の表記 -> 画面に出す表記。載っていないキーはそのまま出す。
_KEY_DISPLAY = {
    "Left": "←",
    "Right": "→",
    "Return": "Enter",
}


@dataclass(frozen=True)
class Shortcut:
    """1つの操作と、それに割り当てられたキーの組。"""

    id: str
    label: str
    keys: tuple[str, ...]
    """割り当てるキー。先頭が代表キーで、画面に出るのはこれだけ。"""

    @property
    def hint(self) -> str:
        """ボタンに添えるキー表記。"""
        key = self.keys[0]
        return _KEY_DISPLAY.get(key, key)

    def text(self, prefix: str = "", suffix: str = "", label: str | None = None) -> str:
        """ボタン用の文字列を組み立てる。

        例: `EDIT.text("✎")` -> `"✎ 修正 (E)"`、`NEXT.text(suffix="▶")` -> `"次 ▶ (→)"`。

        `label` は、同じキーが文脈で別の言葉になる場合だけ渡す(Esc は通常時
        「選択解除」、追加モード中は「キャンセル」)。キーの表記は共通のまま
        言葉だけ差し替わる。
        """
        parts = [p for p in (prefix, label or self.label, suffix) if p]
        return f"{' '.join(parts)} ({self.hint})"


PREV = Shortcut("prev_image", "前", ("Left",))
NEXT = Shortcut("next_image", "次", ("Right", "D", "Space"))
ADD = Shortcut("add", "追加", ("A",))
EDIT = Shortcut("edit", "修正", ("E",))
FIT = Shortcut("fit", "フィット", ("F",))
OVERLAY = Shortcut("overlay", "オーバーレイ", ("V",))
FILL = Shortcut("fill", "塗り", ("B",))
# 通常時は選択解除、追加モード中はモードの取り消し(段階的に効く)。
ESCAPE = Shortcut("escape", "選択解除", ("Esc",))
# 作図中はパスを閉じる動作が優先される。
CONFIRM = Shortcut("confirm", "確定", ("Return", "Enter"))
UNDO_POINT = Shortcut("undo_point", "頂点を取消", ("Ctrl+Z", "Backspace"))
DELETE = Shortcut("delete", "削除", ("Delete",))

ALL: tuple[Shortcut, ...] = (
    PREV,
    NEXT,
    ADD,
    EDIT,
    FIT,
    OVERLAY,
    FILL,
    ESCAPE,
    CONFIRM,
    UNDO_POINT,
    DELETE,
)
