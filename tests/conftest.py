"""テスト共通の下ごしらえ。

ウィンドウを組み立てるテストは設定ファイルを読み書きする(ショートカットの
既定値の書き出しや、筆の太さの保存)。既定のままだと実利用の設定ファイルを
触ってしまい、さらにテスト同士が保存値を通じて影響し合うため、テストごとに
使い捨ての INI へ向ける。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from annotate_tool import settings as settings_module


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    ini = tmp_path / "settings" / "annotate-tool.ini"
    monkeypatch.setattr(
        settings_module, "load", lambda: QSettings(str(ini), QSettings.IniFormat)
    )
    return ini
