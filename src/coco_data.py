"""COCO instance-segmentation データの読み込み・保持を担う軽量な層。

ビューアと編集ツールの両方から使えるように、GUI に依存しない純粋な
データモデルとして分離している。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageEntry:
    id: int
    file_name: str
    width: int
    height: int


@dataclass
class Annotation:
    id: int
    image_id: int
    category_id: int
    segmentation: list[list[float]]  # COCO polygon 形式: [[x1,y1,x2,y2,...], ...]
    bbox: list[float] = field(default_factory=list)  # [x, y, w, h]
    area: float = 0.0
    iscrowd: int = 0

    def polygons(self) -> list[list[tuple[float, float]]]:
        """segmentation を (x, y) タプルのリストに変換して返す。"""
        result: list[list[tuple[float, float]]] = []
        for poly in self.segmentation:
            pts = [(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)]
            if pts:
                result.append(pts)
        return result


@dataclass
class Category:
    id: int
    name: str
    supercategory: str = ""


class CocoDataset:
    """COCO JSON を読み込み、画像単位でアノテーションを引けるようにする。"""

    def __init__(self, json_path: str | Path):
        self.json_path = Path(json_path)
        self.data_dir = self.json_path.parent

        raw = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.info: dict = raw.get("info", {})
        self.licenses: list = raw.get("licenses", [])

        self.images: list[ImageEntry] = [
            ImageEntry(
                id=im["id"],
                file_name=im["file_name"],
                width=im.get("width", 0),
                height=im.get("height", 0),
            )
            for im in raw.get("images", [])
        ]

        self.categories: dict[int, Category] = {
            c["id"]: Category(
                id=c["id"],
                name=c.get("name", str(c["id"])),
                supercategory=c.get("supercategory", ""),
            )
            for c in raw.get("categories", [])
        }

        self.annotations: list[Annotation] = [
            Annotation(
                id=a["id"],
                image_id=a["image_id"],
                category_id=a["category_id"],
                segmentation=a.get("segmentation", []),
                bbox=a.get("bbox", []),
                area=a.get("area", 0.0),
                iscrowd=a.get("iscrowd", 0),
            )
            for a in raw.get("annotations", [])
        ]

        # image_id -> annotations の索引
        self._by_image: dict[int, list[Annotation]] = {}
        for ann in self.annotations:
            self._by_image.setdefault(ann.image_id, []).append(ann)

    def annotations_for(self, image_id: int) -> list[Annotation]:
        return self._by_image.get(image_id, [])

    def image_path(self, image: ImageEntry) -> Path:
        return self.data_dir / image.file_name

    def category_name(self, category_id: int) -> str:
        cat = self.categories.get(category_id)
        return cat.name if cat else str(category_id)
