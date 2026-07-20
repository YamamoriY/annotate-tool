"""COCO segmentation ビューアのエントリポイント。

使い方:
    uv run src/main.py [path/to/instances.json]
    uv run annotate-tool [path/to/instances.json]

引数を省略した場合は前回開いた JSON を開き直す。それも無ければ何も開かずに
起動し、右パネルの「開く」で選んでもらう。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from annotate_tool import settings
from annotate_tool.widgets import ViewerWindow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="annotate-tool",
        description="COCO instance-segmentation アノテーションのビューア",
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        type=Path,
        default=None,
        help="COCO JSON のパス(省略時: 前回開いたファイル)",
    )
    return parser.parse_args(argv)


def startup_path(json_path: Path | None) -> Path | None:
    """起動時に開くファイルを決める。開くものが無ければ None。

    引数 > 前回開いたファイル の順。前回のファイルは消えていることがあるので
    実在を確かめる(無ければ黙って未読込で起動する。前回の設定が理由で
    起動が止まるのは筋が悪い)。
    """
    if json_path is not None:
        return json_path
    remembered = settings.last_json(settings.load())
    if remembered and Path(remembered).exists():
        return Path(remembered)
    return None


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.json_path is not None and not args.json_path.exists():
        print(f"COCO JSON が見つかりません: {args.json_path}")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = ViewerWindow()
    path = startup_path(args.json_path)
    if path is not None:
        window.open_dataset(path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
