# -*- mode: python ; coding: utf-8 -*-
"""onedir ビルド（配布推奨）。

リポジトリルートから実行すること:
    uv run pyinstaller packaging/annotate-tool.spec --noconfirm
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
    [],
    exclude_binaries=True,
    name='annotate-tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon(),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='annotate-tool',
)

# macOS では .app バンドルを生成する
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='annotate-tool.app',
        icon=app_icon(),
        bundle_identifier='dev.tkino117.annotate-tool',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '0.1.0',
        },
    )
