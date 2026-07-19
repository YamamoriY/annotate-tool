"""COCO segmentation ビューアのエントリポイント。

使い方:
    uv run src/main.py [path/to/instances.json]

引数を省略した場合は data/instances.json を読み込む。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from coco_data import CocoDataset
from viewer import ViewerWindow

DEFAULT_JSON = Path(__file__).resolve().parent.parent / "data" / "instances.json"


def main() -> None:
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JSON
    if not json_path.exists():
        print(f"COCO JSON が見つかりません: {json_path}")
        sys.exit(1)

    dataset = CocoDataset(json_path)

    app = QApplication(sys.argv)
    window = ViewerWindow(dataset)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
