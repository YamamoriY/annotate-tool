"""COCO segmentation ビューアのエントリポイント。

使い方:
    uv run src/main.py [path/to/instances.json]
    uv run annotate-tool [path/to/instances.json]

引数を省略した場合は data/instances.json を読み込む。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from annotate_tool.coco_data import CocoDataset
from annotate_tool.widgets import ViewerWindow

DEFAULT_JSON = Path(__file__).resolve().parents[2] / "data" / "instances.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="annotate-tool",
        description="COCO instance-segmentation アノテーションのビューア",
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        type=Path,
        default=DEFAULT_JSON,
        help=f"COCO JSON のパス(省略時: {DEFAULT_JSON})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.json_path.exists():
        print(f"COCO JSON が見つかりません: {args.json_path}")
        sys.exit(1)

    dataset = CocoDataset(args.json_path)

    app = QApplication(sys.argv)
    window = ViewerWindow(dataset)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
