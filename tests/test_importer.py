import json
import sqlite3
from zipfile import ZipFile

import pytest
from ijson import JSONError

from bord_food_api.catalog import connect, metadata
from bord_food_api.importer import build_catalog, import_lock


def test_four_usda_wrappers_and_zip_streaming(tmp_path, foods):
    paths = []
    for root, index in [
        ("BrandedFoods", 0),
        ("FoundationFoods", 2),
        ("SurveyFoods", 3),
        ("SRLegacyFoods", 4),
    ]:
        path = tmp_path / (root + ".zip")
        with ZipFile(path, "w") as archive:
            archive.writestr("nested/" + root + ".json", json.dumps({root: [foods[index]]}))
            archive.writestr("README.txt", "Ignored")
        paths.append(path)
    database = tmp_path / "test.sqlite"
    report = build_catalog(paths, database)
    assert report["totalFoods"] == 4
    assert len(report["dataTypes"]) == 4
    assert not list(tmp_path.glob("*.json"))


def test_failed_import_does_not_replace_existing_catalog(settings, tmp_path, foods):
    before = settings.database.read_bytes()
    invalid = tmp_path / "broken.json"
    invalid.write_text(json.dumps([foods[0]])[:-1] + ", {")
    with pytest.raises(JSONError):
        build_catalog([invalid], settings.database)
    assert settings.database.read_bytes() == before
    assert not list(tmp_path.glob("*.building"))
    invalid.write_text(json.dumps([foods[0], foods[0]]))
    with pytest.raises(sqlite3.IntegrityError):
        build_catalog([invalid], settings.database)
    assert settings.database.read_bytes() == before


def test_successful_replacement_keeps_existing_reader_valid(settings, tmp_path, foods):
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps([foods[-1]]))
    with connect(settings.database) as old_reader:
        assert metadata(old_reader)["totalFoods"] == 6
        build_catalog([replacement], settings.database)
        assert metadata(old_reader)["totalFoods"] == 6
        with connect(settings.database) as new_reader:
            assert metadata(new_reader)["totalFoods"] == 1


@pytest.mark.parametrize("value", [{}, [], {"NotUSDA": []}, {"BrandedFoods": {}}, [{"fdcId": 1}]])
def test_empty_or_invalid_sources_do_not_publish(tmp_path, value):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        build_catalog([path], tmp_path / "foods.sqlite")
    assert not (tmp_path / "foods.sqlite").exists()


def test_writer_lock(tmp_path):
    with (
        import_lock(tmp_path),
        pytest.raises(ValueError, match="already running"),
        import_lock(tmp_path),
    ):
        pytest.fail("A second writer acquired the lock")


def test_official_null_placeholders_are_counted(tmp_path, foods):
    path = tmp_path / "foundation.json"
    path.write_text(json.dumps({"FoundationFoods": [foods[2], None, None]}))
    report = build_catalog([path], tmp_path / "foods.sqlite")
    assert report["totalFoods"] == 1
    assert report["sources"][0]["skippedNulls"] == 2


def test_unsafe_archive_path_rejected_before_publication(tmp_path, foods):
    path = tmp_path / "unsafe.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("../../escape.json", json.dumps(foods))
    with pytest.raises(ValueError, match="unsafe_archive_member"):
        build_catalog([path], tmp_path / "test.sqlite")
    assert not (tmp_path / "test.sqlite").exists()
