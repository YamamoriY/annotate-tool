"""バンドルされたリソースファイルの探索。

PyInstaller で固めた場合と、リポジトリから直接動かす場合の両方で同じパスを
返せるようにする。
"""

from __future__ import annotations

import sys
from pathlib import Path

# spec 側の datas で `packaging/icons` をこの名前で同梱している。
_BUNDLE_ICON_DIR = "icons"


def _bundle_root() -> Path | None:
    """PyInstaller の展開先。凍結されていなければ None。"""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass is not None else None


def app_icon_path() -> Path | None:
    """アプリアイコン (.ico) のパス。見つからなければ None。"""
    root = _bundle_root()
    if root is not None:
        candidate = root / _BUNDLE_ICON_DIR / "app.ico"
        return candidate if candidate.exists() else None

    # 開発時はリポジトリの packaging/icons/ を直接参照する。
    candidate = Path(__file__).resolve().parents[2] / "packaging" / "icons" / "app.ico"
    return candidate if candidate.exists() else None
