"""spec ファイル間で共有するビルド設定。

spec から `sys.path.insert(0, SPECPATH)` した上で import する。
"""

import os
import sys

PACKAGING_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PACKAGING_DIR)
ICON_DIR = os.path.join(PACKAGING_DIR, 'icons')

ENTRY_POINT = os.path.join(ROOT, 'src', 'main.py')

# 未使用の Qt モジュール群。バンドルサイズ削減のため除外する。
EXCLUDES = [
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtQuick',
    'PySide6.QtQml',
    'PySide6.Qt3DCore',
    'PySide6.QtMultimedia',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'tkinter',
]


def icon_datas():
    """アイコンを実行時にも読めるよう同梱する。

    exe に焼き込まれるアイコンは Explorer 用で、Qt のウィンドウ／タスクバー
    アイコンには使われない。実体のファイルを別途バンドルする必要がある。
    """
    if not os.path.isdir(ICON_DIR):
        return []
    return [(os.path.join(ICON_DIR, '*.ico'), 'icons')]


def app_icon():
    """アプリアイコンのパスを返す。未配置なら None（アイコンなしでビルド続行）。"""
    names = ('app.icns', 'app.png') if sys.platform == 'darwin' else ('app.ico', 'app.png')
    for name in names:
        path = os.path.join(ICON_DIR, name)
        if os.path.exists(path):
            return path
    return None
