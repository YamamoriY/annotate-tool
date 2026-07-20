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

    def __init__(self, json_path: str | Path | None = None):
        """json_path=None は「まだ何も開いていない」空のデータセット。

        起動直後(開くファイルが決まっていない)を表すために許している。
        画像もアノテーションも空なので、以降の参照系は素直に空を返し、
        save() は書き出す先が無いので何もしない。
        """
        self.json_path = Path(json_path) if json_path is not None else None
        self.data_dir = self.json_path.parent if self.json_path else None

        # 保存時に元データの全フィールドを保つため、生の dict を保持しておく。
        raw: dict = (
            json.loads(self.json_path.read_text(encoding="utf-8"))
            if self.json_path
            else {}
        )
        self._raw = raw
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

    def default_category_id(self) -> int:
        """新規アノテーションに割り当てる既定カテゴリ(最小の category id)。"""
        if self.categories:
            return min(self.categories)
        return 1

    def _next_annotation_id(self) -> int:
        """未使用のアノテーション id を返す(既存最大 + 1)。"""
        ids = [a.id for a in self.annotations]
        ids += [a.get("id", 0) for a in self._raw.get("annotations", [])]
        return (max(ids) + 1) if ids else 1

    def add_annotation(
        self,
        image_id: int,
        segmentation: list[list[float]],
        category_id: int | None = None,
    ) -> Annotation:
        """ポリゴン列から新しいアノテーションを作って登録する。

        bbox / area は segmentation から算出する。id は自動採番。生の dict にも
        追加するため、この後 save() すればそのまま JSON に書き出される。
        """
        if category_id is None:
            category_id = self.default_category_id()
        bbox = _bbox_of(segmentation)
        area = _area_of(segmentation)
        ann = Annotation(
            id=self._next_annotation_id(),
            image_id=image_id,
            category_id=category_id,
            segmentation=segmentation,
            bbox=bbox,
            area=area,
        )
        self.annotations.append(ann)
        self._by_image.setdefault(image_id, []).append(ann)
        self._raw.setdefault("annotations", []).append(
            {
                "id": ann.id,
                "image_id": image_id,
                "category_id": category_id,
                "segmentation": segmentation,
                "bbox": bbox,
                "area": area,
                "iscrowd": 0,
            }
        )
        return ann

    def update_annotation(
        self, ann: Annotation, segmentation: list[list[float]]
    ) -> None:
        """既存アノテーションの形状を差し替える(bbox / area も引き直す)。

        id・category_id・その他のフィールドは保つ。生の dict 側も同じ id を探して
        書き換えるため、この後 save() すればそのまま JSON へ反映される。
        """
        ann.segmentation = segmentation
        ann.bbox = _bbox_of(segmentation)
        ann.area = _area_of(segmentation)
        for raw in self._raw.get("annotations", []):
            if raw.get("id") == ann.id:
                raw["segmentation"] = segmentation
                raw["bbox"] = ann.bbox
                raw["area"] = ann.area
                break

    def delete_annotations(self, annotations: list[Annotation]) -> None:
        """指定したアノテーション群を削除し、画像索引を張り直す。"""
        targets = {id(ann) for ann in annotations}
        if not targets:
            return
        self.annotations = [a for a in self.annotations if id(a) not in targets]
        self._by_image = {}
        for ann in self.annotations:
            self._by_image.setdefault(ann.image_id, []).append(ann)

    def save(self) -> None:
        """現在のアノテーション集合を元の JSON へ上書き保存する。

        元データの全フィールドを保つため、生の dict から削除済みアノテーションだけを
        取り除いて書き戻す(id は COCO 内で一意である前提)。
        """
        if self.json_path is None:
            return  # 空のデータセット(書き出す先が無い)
        surviving = {ann.id for ann in self.annotations}
        self._raw["annotations"] = [
            a for a in self._raw.get("annotations", []) if a.get("id") in surviving
        ]
        self.json_path.write_text(
            json.dumps(self._raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def image_path(self, image: ImageEntry) -> Path:
        return self.data_dir / image.file_name

    def category_name(self, category_id: int) -> str:
        cat = self.categories.get(category_id)
        return cat.name if cat else str(category_id)


def _bbox_of(segmentation: list[list[float]]) -> list[float]:
    """COCO polygon 列から外接矩形 [x, y, w, h] を求める。"""
    xs: list[float] = []
    ys: list[float] = []
    for poly in segmentation:
        xs += poly[0::2]
        ys += poly[1::2]
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return [x0, y0, x1 - x0, y1 - y0]


def _area_of(segmentation: list[list[float]]) -> float:
    """polygon 列の面積を靴ひも公式で近似する(各ポリゴンの絶対面積の総和)。"""
    total = 0.0
    for poly in segmentation:
        pts = [(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)]
        if len(pts) < 3:
            continue
        s = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            s += x1 * y2 - x2 * y1
        total += abs(s) / 2.0
    return total
