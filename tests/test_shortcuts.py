"""ショートカット定義表のテスト。

QAction への結線は QApplication が要るためここでは見ない(このリポジトリは
GUI テストの基盤を持たない)。表そのものの整合と、ボタン文字列の組み立てだけ
を押さえる。キーを変えたときに壊れてほしいのはここ。
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence

from annotate_tool import shortcuts


def test_ids_are_unique():
    ids = [s.id for s in shortcuts.ALL]
    assert len(ids) == len(set(ids))


def test_no_key_is_bound_twice():
    """同じキーが2つの操作に割り当たっていないこと。

    重複すると Qt はどちらも呼ばず黙って無視するため、気づきにくい。
    """
    seen: dict[str, str] = {}
    for s in shortcuts.ALL:
        for key in s.keys:
            assert key not in seen, f"{key} が {seen.get(key)} と {s.id} で重複"
            seen[key] = s.id


def test_every_key_is_valid():
    for s in shortcuts.ALL:
        for key in s.keys:
            assert not QKeySequence(key).isEmpty(), f"{s.id}: 解釈できないキー {key}"


def test_every_shortcut_has_a_key():
    for s in shortcuts.ALL:
        assert s.keys, s.id


def test_hint_uses_the_first_key():
    """画面に出るのは代表キーだけ(次の画像は D / Space でも効くが → と出す)。"""
    assert shortcuts.NEXT.hint == "→"


def test_hint_rewrites_only_known_keys():
    assert shortcuts.ESCAPE.hint == "Esc"  # 変換表に無いものはそのまま
    assert shortcuts.CONFIRM.hint == "Enter"  # Return は Enter と出す


def test_text_places_prefix_and_suffix():
    assert shortcuts.EDIT.text("✎") == "✎ 修正 (E)"
    assert shortcuts.NEXT.text(suffix="▶") == "次 ▶ (→)"
    assert shortcuts.FIT.text() == "フィット (F)"


def test_text_label_override_keeps_the_key():
    """Esc は文脈で言葉が変わるが、キー表記は共通のまま。"""
    assert shortcuts.ESCAPE.text("✕") == "✕ 選択解除 (Esc)"
    assert shortcuts.ESCAPE.text("✕", label="キャンセル") == "✕ キャンセル (Esc)"
