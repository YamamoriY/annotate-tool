"""キーボードショートカットの定義と、設定ファイルによる差し替え。

役割は2つに分かれる。

- `Shortcut` … 操作の identity(id・表示名・既定キー)。不変。
- `Keymap`   … 「いまどのキーが割り当たっているか」。既定 + 設定ファイルの上書き。

QAction もボタンの文字列も `Keymap` だけを見る。以前はボタン側に "修正 (E)" の
ような表記を直接書いていたため、キーを変えても表示だけが古いまま残った。

設定ファイル(INI)の書式は `shortcuts/<id> = キー[, キー...]`。先頭が代表キーで、
ボタンに出るのはこれだけ。壊れた行は無視して既定へ戻し、理由を `problems` で返す
(起動を止めない。設定ファイルの誤字でツールが使えなくなる方が困るため)。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from PySide6.QtGui import QKeySequence

# QKeySequence の表記 -> 画面に出す表記。載っていないキーはそのまま出す。
_KEY_DISPLAY = {
    "Left": "←",
    "Right": "→",
    "Return": "Enter",
}


@dataclass(frozen=True)
class Shortcut:
    """操作そのもの。キーは既定値だけを持ち、実際の割り当ては Keymap が決める。"""

    id: str
    label: str
    default_keys: tuple[str, ...]


PREV = Shortcut("prev_image", "前", ("Left",))
NEXT = Shortcut("next_image", "次", ("Right",))
ADD = Shortcut("add", "追加", ("A",))
EDIT = Shortcut("edit", "修正", ("E",))
FIT = Shortcut("fit", "フィット", ("F",))
OVERLAY = Shortcut("overlay", "オーバーレイ", ("V",))
FILL = Shortcut("fill", "塗り", ("B",))
# 通常時は選択解除、追加モード中はモードの取り消し(段階的に効く)。
ESCAPE = Shortcut("escape", "選択解除", ("Esc",))
# 作図中はパスを閉じる動作が優先される。Enter も従来どおり効く。
CONFIRM = Shortcut("confirm", "確定", ("S", "Return", "Enter"))
UNDO_POINT = Shortcut("undo_point", "頂点を取消", ("Ctrl+Z", "Backspace"))
DELETE = Shortcut("delete", "削除", ("Delete",))
# 描画ツールの切り替え(追加モード中のみ)。左手で 1/2/3 を押し分ける想定。
TOOL_BRUSH = Shortcut("tool_brush", "ブラシ", ("1",))
TOOL_ERASER = Shortcut("tool_eraser", "消しゴム", ("2",))
TOOL_POLYGON = Shortcut("tool_polygon", "パス", ("3",))

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
    TOOL_BRUSH,
    TOOL_ERASER,
    TOOL_POLYGON,
)

BY_ID: dict[str, Shortcut] = {s.id: s for s in ALL}


def normalize(key: str) -> str | None:
    """キー表記を Qt の正規形へ直す。解釈できなければ None。

    "ctrl+z" -> "Ctrl+Z"、"Escape" -> "Esc" のように表記ゆれを吸収する。重複判定は
    必ずこの正規形で行う("a" と "A" は同じキー)。

    QKeySequence.isEmpty() は使えない。"ほげ" や "Ctrl+" のような解釈できない
    文字列でも False を返すため。空文字になるかどうかで判断する。また、先に
    strip しないと空白だけの値が Space キーとして通ってしまう。
    """
    key = key.strip()
    if not key:
        return None
    text = QKeySequence(key).toString()
    return text or None


def _split(value: object) -> list[str]:
    """設定ファイルの値をキーのリストへ均す。

    QSettings はカンマを含む値を、書かれ方によって str と list のどちらでも
    返す(人が手で `a, b` と書けば list、引用符付きなら str)。両方来る前提で扱う。
    """
    if isinstance(value, (list, tuple)):
        parts: Iterable[str] = [str(v) for v in value]
    else:
        parts = str(value).split(",")
    return [p.strip() for p in parts if p.strip()]


class Keymap:
    """id -> 割り当てキー。表示用の文字列もここから作る。"""

    def __init__(self, assignments: Mapping[str, tuple[str, ...]]):
        self._keys = dict(assignments)

    def keys(self, shortcut: Shortcut) -> tuple[str, ...]:
        return self._keys[shortcut.id]

    def hint(self, shortcut: Shortcut) -> str:
        """ボタンに添えるキー表記(代表キーのみ)。"""
        key = self.keys(shortcut)[0]
        return _KEY_DISPLAY.get(key, key)

    def text(
        self,
        shortcut: Shortcut,
        prefix: str = "",
        suffix: str = "",
        label: str | None = None,
    ) -> str:
        """ボタン用の文字列を組み立てる。

        例: `text(EDIT, "✎")` -> `"✎ 修正 (E)"`、`text(NEXT, suffix="▶")` -> `"次 ▶ (→)"`。

        `label` は、同じキーが文脈で別の言葉になる場合だけ渡す(Esc は通常時
        「選択解除」、追加モード中は「キャンセル」)。キーの表記は共通のまま
        言葉だけ差し替わる。
        """
        parts = [p for p in (prefix, label or shortcut.label, suffix) if p]
        return f"{' '.join(parts)} ({self.hint(shortcut)})"

    def as_settings(self) -> dict[str, str]:
        """設定ファイルへ書ける形(id -> "Right, D, Space")。"""
        return {sid: ", ".join(keys) for sid, keys in self._keys.items()}


def defaults() -> Keymap:
    return Keymap({s.id: tuple(_normalized_default(s)) for s in ALL})


def _normalized_default(shortcut: Shortcut) -> list[str]:
    keys = [normalize(k) for k in shortcut.default_keys]
    # 既定値の誤りはプログラムの誤り。設定ファイルの誤字と違い、黙って直さない。
    assert all(keys), f"{shortcut.id}: 既定キーが不正 {shortcut.default_keys}"
    return [k for k in keys if k]


def resolve(overrides: Mapping[str, object]) -> tuple[Keymap, list[str]]:
    """既定へ設定ファイルの上書きを重ねる。(keymap, 問題の一覧) を返す。

    方針は「壊れた行だけ捨てて、残りは活かす」。ただしキーの重複だけは例外で、
    重複が残る場合は上書きを全部捨てて既定へ戻す。重複したキーは Qt が曖昧と
    見なしてどちらも発火させず、しかも警告が出ないため、中途半端に一部だけ
    適用すると「なぜか効かないキーがある」状態を自分で作ることになる。
    """
    problems: list[str] = []
    assignments = {s.id: tuple(_normalized_default(s)) for s in ALL}
    applied: dict[str, tuple[str, ...]] = {}

    for shortcut_id, value in overrides.items():
        if shortcut_id not in BY_ID:
            problems.append(f"{shortcut_id}: 知らない操作です(無視しました)")
            continue
        raw = _split(value)
        if not raw:
            problems.append(f"{shortcut_id}: キーが空です(既定に戻しました)")
            continue
        keys = [normalize(k) for k in raw]
        bad = [r for r, k in zip(raw, keys) if k is None]
        if bad:
            problems.append(
                f"{shortcut_id}: 解釈できないキー {', '.join(bad)}(既定に戻しました)"
            )
            continue
        applied[shortcut_id] = tuple(k for k in keys if k)

    assignments.update(applied)

    duplicates = _duplicates(assignments)
    if duplicates and applied:
        problems.append(
            f"キーの重複: {', '.join(duplicates)}。"
            "設定ファイルの割り当てをすべて無視し、既定に戻しました"
        )
        assignments = {s.id: tuple(_normalized_default(s)) for s in ALL}

    return Keymap(assignments), problems


def _duplicates(assignments: Mapping[str, tuple[str, ...]]) -> list[str]:
    """2つ以上の操作に割り当たっているキーを挙げる。"""
    owners: dict[str, list[str]] = {}
    for shortcut_id, keys in assignments.items():
        for key in keys:
            owners.setdefault(key, []).append(shortcut_id)
    return sorted(key for key, ids in owners.items() if len(ids) > 1)
