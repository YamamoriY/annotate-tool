"""ユーザー設定の永続化。

保存先は %APPDATA%\\tree-log\\annotate-tool.ini (INI 形式)。
レジストリではなくファイルにするのは、中身を直接読めて、消したいときは
ファイルを1つ捨てるだけで済むため。

対象はアノテーションではなく「ツールの使い勝手」の設定だけ。
アノテーションの保存は CocoDataset 側が持つ。
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

ORGANIZATION = "tree-log"
APPLICATION = "annotate-tool"

KEY_CONFIRM_DELETE = "ui/confirm_delete"
DEFAULT_CONFIRM_DELETE = True

# タッチパッドモード。ON でホイール(2本指スクロール)がパンになり、ズームは
# Ctrl+ホイール(タッチパッドのピンチはこれに合成される)で行う。OFF なら従来
# どおりホイール=ズーム。マウスとタッチパッドはイベントだけでは確実に区別
# できない(特に Windows)ため、どちらの流儀で読むかをユーザーに決めてもらう。
KEY_TOUCHPAD_MODE = "ui/touchpad_mode"
DEFAULT_TOUCHPAD_MODE = False

# 最後に開いた COCO JSON。次の起動でこれを開き直す(引数なしで起動できるように)。
KEY_LAST_JSON = "io/last_json"


def load() -> QSettings:
    """設定ファイルを開く。

    フォーマットとスコープは明示する。QSettings(org, app) の2引数版は
    プラットフォーム既定(Windows ではレジストリ)になってしまうため。
    """
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        ORGANIZATION,
        APPLICATION,
    )


SHORTCUT_GROUP = "shortcuts"


def shortcut_overrides(settings: QSettings) -> dict[str, object]:
    """[shortcuts] セクションを id -> 値 で読み出す。

    値の型は QSettings 任せ(カンマの書き方で str と list のどちらにもなる)。
    解釈は shortcuts 側が引き受けるので、ここでは素通しする。
    """
    settings.beginGroup(SHORTCUT_GROUP)
    try:
        return {key: settings.value(key) for key in settings.allKeys()}
    finally:
        settings.endGroup()


def write_missing_shortcuts(settings: QSettings, assignments: dict[str, str]) -> None:
    """まだ書かれていない項目だけ既定値で書き出す。

    設定ファイルに実物が並んでいないと、ユーザーは id もキーの書式も分からない。
    既にある値は上書きしない(ユーザーの変更を消さないため)。
    """
    settings.beginGroup(SHORTCUT_GROUP)
    try:
        existing = set(settings.allKeys())
        for shortcut_id, keys in assignments.items():
            if shortcut_id not in existing:
                settings.setValue(shortcut_id, keys)
    finally:
        settings.endGroup()


def flush(settings: QSettings) -> None:
    """保留中の変更をファイルへ書き出す。

    QSettings は書き込みを遅延させるため、設定フォルダを開いて見せる前など
    「ファイルが実在していてほしい」場面では明示的に呼ぶ。
    """
    settings.sync()


def confirm_delete(settings: QSettings) -> bool:
    # Windows では bool が文字列で返ることがあるため type= を必ず付ける
    return settings.value(KEY_CONFIRM_DELETE, DEFAULT_CONFIRM_DELETE, type=bool)


def set_confirm_delete(settings: QSettings, value: bool) -> None:
    settings.setValue(KEY_CONFIRM_DELETE, value)


def touchpad_mode(settings: QSettings) -> bool:
    # Windows では bool が文字列で返ることがあるため type= を必ず付ける
    return settings.value(KEY_TOUCHPAD_MODE, DEFAULT_TOUCHPAD_MODE, type=bool)


def set_touchpad_mode(settings: QSettings, value: bool) -> None:
    settings.setValue(KEY_TOUCHPAD_MODE, value)


def last_json(settings: QSettings) -> str:
    """最後に開いた COCO JSON のパス(未設定なら空文字)。

    存在確認はしない。設定を書いた後にファイルが動く/消えることはあるので、
    開けるかどうかは使う側が確かめる。
    """
    return settings.value(KEY_LAST_JSON, "", type=str)


def set_last_json(settings: QSettings, path: str) -> None:
    settings.setValue(KEY_LAST_JSON, path)
