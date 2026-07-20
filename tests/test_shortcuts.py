"""ショートカットの定義表と、設定ファイルによる差し替えのテスト。

QAction への結線は QApplication が要るため test_action_enabled.py が見る。
ここは表そのものの整合と、設定値の解釈だけを押さえる。
"""

from __future__ import annotations

from annotate_tool import shortcuts


# --- 定義表そのもの -------------------------------------------------------
def test_ids_are_unique():
    ids = [s.id for s in shortcuts.ALL]
    assert len(ids) == len(set(ids))


def test_no_default_key_is_bound_twice():
    """既定の割り当てにキーの重複が無いこと。

    Qt は同じキーに有効な QAction が2つあると曖昧と見なし、どちらも発火させない。
    例外も警告も出ずキーが黙って死ぬため、ここで止める。
    """
    assert shortcuts._duplicates(shortcuts.defaults()._keys) == []


def test_every_default_key_is_valid():
    for s in shortcuts.ALL:
        assert s.default_keys, s.id
        for key in s.default_keys:
            assert shortcuts.normalize(key), f"{s.id}: 解釈できないキー {key}"


def test_add_and_confirm_keys():
    """追加は A、確定は S(Enter も従来どおり効く)。"""
    keymap = shortcuts.defaults()
    assert keymap.hint(shortcuts.ADD) == "A"
    assert keymap.hint(shortcuts.CONFIRM) == "S"
    assert "Return" in keymap.keys(shortcuts.CONFIRM)


# --- キー表記の正規化 -----------------------------------------------------
def test_normalize_absorbs_notation_differences():
    assert shortcuts.normalize("ctrl+z") == "Ctrl+Z"
    assert shortcuts.normalize("a") == "A"
    assert shortcuts.normalize("Escape") == shortcuts.normalize("Esc")


def test_normalize_rejects_garbage():
    """QKeySequence.isEmpty() では弾けないものを弾く。

    "ほげ" や "Ctrl+" は isEmpty() が False を返すため、そちらで判定すると
    「空のキー」が有効な割り当てとして通ってしまう。
    """
    assert shortcuts.normalize("ほげ") is None
    assert shortcuts.normalize("Ctrl+") is None
    assert shortcuts.normalize("") is None


def test_normalize_rejects_whitespace_only():
    """空白だけの値は Space キーに化けるため、strip してから判定する。"""
    assert shortcuts.normalize("   ") is None


# --- 表示文字列 -----------------------------------------------------------
def test_hint_uses_the_first_key():
    """画面に出るのは代表キーだけ(次の画像は D / Space でも効くが → と出す)。"""
    assert shortcuts.defaults().hint(shortcuts.NEXT) == "→"


def test_text_places_prefix_and_suffix():
    keymap = shortcuts.defaults()
    assert keymap.text(shortcuts.EDIT, "✎") == "✎ 修正 (E)"
    assert keymap.text(shortcuts.NEXT, suffix="▶") == "次 ▶ (→)"
    assert keymap.text(shortcuts.FIT) == "フィット (F)"


def test_text_label_override_keeps_the_key():
    """Esc は文脈で言葉が変わるが、キー表記は共通のまま。"""
    keymap = shortcuts.defaults()
    assert keymap.text(shortcuts.ESCAPE, "✕") == "✕ 選択解除 (Esc)"
    assert keymap.text(shortcuts.ESCAPE, "✕", label="キャンセル") == "✕ キャンセル (Esc)"


def test_display_follows_the_override():
    """キーを差し替えたらボタンの表記も追随する(ここが二重管理の再発点)。"""
    keymap, problems = shortcuts.resolve({"edit": "Ctrl+E"})
    assert problems == []
    assert keymap.text(shortcuts.EDIT, "✎") == "✎ 修正 (Ctrl+E)"


# --- 設定ファイルの解釈 ---------------------------------------------------
def test_resolve_without_overrides_gives_defaults():
    keymap, problems = shortcuts.resolve({})
    assert problems == []
    assert keymap.keys(shortcuts.ADD) == ("A",)


def test_resolve_accepts_a_comma_string():
    """引用符付きで書かれた値は str で届く。"""
    keymap, problems = shortcuts.resolve({"next_image": "Right, D"})
    assert problems == []
    assert keymap.keys(shortcuts.NEXT) == ("Right", "D")


def test_resolve_accepts_a_list():
    """人が手で `a, b` と書くと QSettings は list で返す。両方受ける。"""
    keymap, problems = shortcuts.resolve({"next_image": ["Right", "D"]})
    assert problems == []
    assert keymap.keys(shortcuts.NEXT) == ("Right", "D")


def test_resolve_normalizes_overrides():
    keymap, _ = shortcuts.resolve({"undo_point": "ctrl+z"})
    assert keymap.keys(shortcuts.UNDO_POINT) == ("Ctrl+Z",)


def test_resolve_keeps_other_overrides_when_one_line_is_broken():
    """壊れた行だけ捨てて、残りは活かす。"""
    keymap, problems = shortcuts.resolve({"edit": "ほげ", "fit": "G"})
    assert keymap.keys(shortcuts.EDIT) == ("E",)  # 既定へ戻る
    assert keymap.keys(shortcuts.FIT) == ("G",)  # こちらは活きる
    assert any("edit" in p for p in problems)


def test_resolve_reports_unknown_id():
    keymap, problems = shortcuts.resolve({"no_such_action": "G"})
    assert any("no_such_action" in p for p in problems)
    assert keymap.keys(shortcuts.FIT) == ("F",)


def test_resolve_reports_empty_value():
    keymap, problems = shortcuts.resolve({"fit": "  "})
    assert keymap.keys(shortcuts.FIT) == ("F",)
    assert any("fit" in p for p in problems)


def test_duplicate_discards_every_override():
    """重複が残るなら上書きを全部捨てる。

    一部だけ適用すると、Qt が曖昧と見なして黙って無視するキーを自分で作って
    しまう。全部戻せば「効かないキーがある」状態には決してならない。
    """
    keymap, problems = shortcuts.resolve({"fit": "E", "overlay": "G"})
    assert keymap.keys(shortcuts.FIT) == ("F",)
    assert keymap.keys(shortcuts.OVERLAY) == ("V",)  # 巻き添えだが既定なので安全
    assert any("重複" in p for p in problems)


def test_duplicate_detection_uses_the_normalized_form():
    """"e" と "E" は同じキー。表記が違うだけの重複を見逃さない。"""
    _, problems = shortcuts.resolve({"fit": "e"})
    assert any("重複" in p for p in problems)


def test_swapping_two_keys_is_not_a_duplicate():
    """入れ替えは重複ではない(同時に指定すれば通る)。"""
    keymap, problems = shortcuts.resolve({"add": "S", "confirm": "A, Return, Enter"})
    assert problems == []
    assert keymap.keys(shortcuts.ADD) == ("S",)
    assert keymap.hint(shortcuts.CONFIRM) == "A"


def test_as_settings_round_trips():
    """書き出した形が、そのまま読み戻せること。"""
    written = shortcuts.defaults().as_settings()
    keymap, problems = shortcuts.resolve(written)
    assert problems == []
    assert keymap.keys(shortcuts.NEXT) == shortcuts.defaults().keys(shortcuts.NEXT)
