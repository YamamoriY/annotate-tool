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


def confirm_delete(settings: QSettings) -> bool:
    # Windows では bool が文字列で返ることがあるため type= を必ず付ける
    return settings.value(KEY_CONFIRM_DELETE, DEFAULT_CONFIRM_DELETE, type=bool)


def set_confirm_delete(settings: QSettings, value: bool) -> None:
    settings.setValue(KEY_CONFIRM_DELETE, value)
