"""アプリアイコンのマスター画像から app.ico / app.icns を生成する。

    uv run python packaging/make_icons.py

マスターは packaging/icons/ 内の icon.* または app.*（png/jpg/jpeg）。
1024x1024 の正方形を推奨。ビルドスクリプトから自動で呼ばれる。
"""

import sys
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"

# 探索順。先に見つかったものをマスターとして使う。
MASTER_CANDIDATES = ("icon.png", "app.png", "icon.jpg", "app.jpg", "icon.jpeg", "app.jpeg")

# Windows の .ico に含めるサイズ。エクスプローラの各表示倍率で使われる。
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def find_master() -> Path | None:
    for name in MASTER_CANDIDATES:
        path = ICON_DIR / name
        if path.exists():
            return path
    return None


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow が必要です: uv add --dev pillow")
        return 1

    master = find_master()
    if master is None:
        print(f"マスター画像がありません。{ICON_DIR} に icon.png などを置いてください。")
        return 1

    print(f"マスター: {master.name}")
    img = Image.open(master).convert("RGBA")
    if img.width != img.height:
        print(f"警告: 正方形ではありません ({img.width}x{img.height})。歪む可能性があります。")

    # 縮小品質を揃えるため、一度 1024 の正方形に正規化してから各サイズを作る。
    square = img.resize((1024, 1024), Image.LANCZOS)

    ico_path = ICON_DIR / "app.ico"
    square.save(ico_path, format="ICO", sizes=ICO_SIZES)
    print(f"生成: {ico_path.name}")

    icns_path = ICON_DIR / "app.icns"
    try:
        square.save(icns_path, format="ICNS", sizes=[(s, s) for s in ICNS_SIZES])
        print(f"生成: {icns_path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f".icns の生成に失敗（macOS 側で生成してください）: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
