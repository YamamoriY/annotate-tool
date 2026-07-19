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


def test_delete_annotations_updates_index(coco_json: Path):
    ds = CocoDataset(coco_json)
    ann10 = ds.annotations_for(1)[0]
    ds.delete_annotations([ann10])
    assert [a.id for a in ds.annotations] == [11, 12]
    assert [a.id for a in ds.annotations_for(1)] == [11]


def test_save_persists_deletion_and_preserves_fields(coco_json: Path):
    ds = CocoDataset(coco_json)
    ds.delete_annotations([ds.annotations_for(1)[0]])  # id 10 を削除
    ds.save()

    reloaded = json.loads(coco_json.read_text(encoding="utf-8"))
    assert [a["id"] for a in reloaded["annotations"]] == [11, 12]
    # 削除に関係しないフィールドは保持される
    assert reloaded["info"] == {"description": "test"}
    assert reloaded["images"][0]["file_name"] == "a.jpg"

    # 再読み込みしても整合していること
    ds2 = CocoDataset(coco_json)
    assert [a.id for a in ds2.annotations] == [11, 12]


def test_add_annotation_computes_geometry_and_id(coco_json: Path):
    ds = CocoDataset(coco_json)
    # 10x10 の四角形を追加(既存 id は 10..12 なので新 id は 13)
    ann = ds.add_annotation(1, [[0, 0, 10, 0, 10, 10, 0, 10]])
    assert ann.id == 13
    assert ann.category_id == 1  # 既定カテゴリ(最小 id)
    assert ann.bbox == [0, 0, 10, 10]
    assert ann.area == 100.0
    assert [a.id for a in ds.annotations_for(1)] == [10, 11, 13]


def test_add_annotation_persists_on_save(coco_json: Path):
    ds = CocoDataset(coco_json)
    ds.add_annotation(2, [[0, 0, 4, 0, 4, 4, 0, 4]])
    ds.save()

    reloaded = json.loads(coco_json.read_text(encoding="utf-8"))
    ids = [a["id"] for a in reloaded["annotations"]]
    assert 13 in ids  # 追加分が保存されている

    ds2 = CocoDataset(coco_json)
    new_ann = next(a for a in ds2.annotations if a.id == 13)
    assert new_ann.image_id == 2
    assert new_ann.area == 16.0


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
