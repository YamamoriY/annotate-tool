"""coco_data モジュール(GUI 非依存層)のテスト。"""

import json
from pathlib import Path

import pytest

from annotate_tool.coco_data import Annotation, CocoDataset


@pytest.fixture
def coco_json(tmp_path: Path) -> Path:
    data = {
        "info": {"description": "test"},
        "licenses": [],
        "images": [
            {"id": 1, "file_name": "a.jpg", "width": 100, "height": 80},
            {"id": 2, "file_name": "b.jpg", "width": 200, "height": 160},
        ],
        "categories": [
            {"id": 1, "name": "circle", "supercategory": "particle"},
        ],
        "annotations": [
            {
                "id": 10,
                "image_id": 1,
                "category_id": 1,
                "segmentation": [[0, 0, 10, 0, 10, 10]],
                "bbox": [0, 0, 10, 10],
                "area": 50.0,
                "iscrowd": 0,
            },
            {
                "id": 11,
                "image_id": 1,
                "category_id": 1,
                "segmentation": [[5, 5, 15, 5, 15, 15]],
            },
            {
                "id": 12,
                "image_id": 2,
                "category_id": 1,
                "segmentation": [],
            },
        ],
    }
    path = tmp_path / "instances.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_basic(coco_json: Path):
    ds = CocoDataset(coco_json)
    assert [im.id for im in ds.images] == [1, 2]
    assert ds.images[0].width == 100
    assert len(ds.annotations) == 3
    assert ds.categories[1].name == "circle"


def test_annotations_for(coco_json: Path):
    ds = CocoDataset(coco_json)
    assert [a.id for a in ds.annotations_for(1)] == [10, 11]
    assert [a.id for a in ds.annotations_for(2)] == [12]
    assert ds.annotations_for(999) == []


def test_image_path_is_relative_to_json_dir(coco_json: Path):
    ds = CocoDataset(coco_json)
    assert ds.image_path(ds.images[0]) == coco_json.parent / "a.jpg"


def test_category_name_fallback(coco_json: Path):
    ds = CocoDataset(coco_json)
    assert ds.category_name(1) == "circle"
    assert ds.category_name(42) == "42"  # 未知 id は文字列化して返す


def test_annotation_polygons():
    ann = Annotation(
        id=1,
        image_id=1,
        category_id=1,
        segmentation=[[0, 0, 10, 0, 10, 10], []],
    )
    assert ann.polygons() == [[(0, 0), (10, 0), (10, 10)]]


def test_optional_fields_default():
    ann = Annotation(id=1, image_id=1, category_id=1, segmentation=[])
    assert ann.bbox == []
    assert ann.area == 0.0
    assert ann.iscrowd == 0
