# -*- mode: python ; coding: utf-8 -*-
"""onefile ビルド（単一 exe）。

起動のたびに一時ディレクトリへ全体を展開するため onedir より起動が遅い。
配布の手軽さを優先する場合のみ使う。

リポジトリルートから実行すること:
    uv run pyinstaller packaging/annotate-tool-onefile.spec --noconfirm
"""

import os
import sys

sys.path.insert(0, SPECPATH)
from spec_common import ENTRY_POINT, EXCLUDES, app_icon, icon_datas  # noqa: E402


a = Analysis(
    [ENTRY_POINT],
    pathex=[],
    binaries=[],
    datas=icon_datas(),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='annotate-tool-onefile',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon(),
)
