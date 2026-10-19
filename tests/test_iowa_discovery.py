import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from bord_food_api.platform import Platform
from bord_food_api.transport import PolicyError

spec = importlib.util.spec_from_file_location(
    "iowa_discovery", Path(__file__).parents[1] / "scripts/discover-iowa-grocers.py"
)
iowa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iowa)


def feature(key, state="IA", shop="supermarket", brand="Synthetic Grocers"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-93.6, 41.6]},
        "properties": {
            "ref": key,
            "name": "Synthetic Branch " + key,
            "brand": brand,
            "addr:country": "US",
            "addr:state": state,
            "shop": shop,
            "website": "https://synthetic.invalid/stores/" + key,
        },
    }


def archive(tmp_path, **members):
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as package:
        for name, features in members.items():
            package.writestr(name, json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def test_statewide_discovery_is_not_limited_to_known_spiders(tmp_path):
    path = archive(
        tmp_path,
        **{
            "unknown_grocer.geojson": [
                feature("one"),
                feature("two", state="Iowa"),
                feature("other", state="WI"),
                feature("fuel", shop="fuel"),
                feature("no-brand", brand=None),
            ]
        },
    )
    report = iowa.discover(path, tmp_path / "result")
    assert report["stores"] == 2 and len(report["banners"]) == 1
    assert report["banners"][0]["stores"] == 2
    assert report["banners"][0]["map_crawl_state"] == "access_review_required"
    assert not report["census_complete"] and len(report["unresolved"]) == 1
    rows = [json.loads(x) for x in (tmp_path / "result/roster.jsonl").read_text().splitlines()]
    assert all(x["payload"]["chain_candidate"] for x in rows)
    assert all(x["payload"]["license"] == "CC0-1.0" for x in rows)


def test_malformed_scope_is_reported_without_partial_publication(tmp_path):
    path = archive(
        tmp_path,
        **{
            "broken.geojson": [
                feature("valid"),
                {"type": "Feature", "properties": {"addr:state": "IA", "addr:country": "US"}},
            ],
            "good.geojson": [feature("good")],
        },
    )
    report = iowa.discover(path, tmp_path / "result")
    assert report["stores"] == 1
    assert report["errors"] == [{"spider": "broken", "error": "ValueError"}]


def test_unsafe_archive_rejected_before_parsing(tmp_path):
    path = archive(tmp_path, **{"../escape.geojson": [feature("one")]})
    with pytest.raises(PolicyError):
        list(iowa.scan(path))


def test_partial_iowa_publication_preserves_ids_and_other_states(tmp_path):
    path = archive(tmp_path, **{"walmart_us.geojson": [feature("iowa", brand="Walmart")]})
    directory = tmp_path / "result"
    iowa.discover(path, directory)
    (directory / "atp-manifest.json").write_text(
        json.dumps({"run_id": "2026-10-10", "start_time": "2026-10-10T00:00:00Z"})
    )
    platform = Platform(tmp_path / "data")
    rows = [
        iowa._atp_feature(
            feature(key, state=state, brand="Walmart"),
            "walmart_us",
            iowa.ATP_DESCRIPTORS["walmart_us"],
        )
        for key, state in [("iowa", "IA"), ("wisconsin", "WI")]
    ]
    platform.sync("all_the_places", "walmart_us", "old", rows)
    original = {x["source_id"]: x["id"] for x in platform.records("store")}
    iowa.publish(directory, platform)
    assert {x["source_id"]: x["id"] for x in platform.records("store")} == original
    assert all(
        x.get("source_membership", {}).get("status") != "retired" for x in platform.records("store")
    )
    report = json.loads((directory / "coverage.json").read_text())
    (directory / "roster.jsonl").write_text("modified")
    with pytest.raises(ValueError, match="roster_hash_mismatch"):
        iowa.publish(directory, platform)
    assert report["stores"] == 1


def test_older_archive_does_not_replace_newer_source_scope(tmp_path):
    path = archive(tmp_path, **{"walmart_us.geojson": [feature("old", brand="Walmart")]})
    directory = tmp_path / "result"
    iowa.discover(path, directory)
    (directory / "atp-manifest.json").write_text(
        json.dumps({"run_id": "2026-10-10", "start_time": "2026-10-10T00:00:00Z"})
    )
    platform = Platform(tmp_path / "data")
    row = iowa._atp_feature(
        feature("new", brand="Walmart"), "walmart_us", iowa.ATP_DESCRIPTORS["walmart_us"]
    )
    platform.sync("all_the_places", "walmart_us", "new", [row], cursor={"source_run": "2026-10-17"})
    result = iowa.publish(directory, platform)
    assert result[0]["reason"] == "newer_scope_already_published"
    assert [x["source_id"] for x in platform.records("store")] == ["new"]


def test_explicit_iowa_postal_suffix_is_not_silently_lost(tmp_path):
    full = feature("full")
    full["properties"].pop("addr:state")
    full["properties"]["addr:full"] = "10 Synthetic Street, Example City, IA 50313"
    conflict = feature("conflict", state="WI")
    conflict["properties"]["addr:full"] = "20 Example St, Test, IA 50313"
    path = archive(tmp_path, **{"unknown_grocer.geojson": [full, conflict]})
    scope = next(iter(iowa.scan(path)))
    assert len(scope["records"]) == 1
    payload = scope["records"][0]["payload"]
    assert payload["address"]["region"] == "IA"
    assert payload["address"]["full"] == full["properties"]["addr:full"]
    assert payload["address_region_evidence"]["field"] == "addr:full"
    assert payload["source_properties"] == full["properties"]


def test_oversized_scope_is_explicitly_reported_and_other_scopes_continue(tmp_path):
    path = archive(
        tmp_path,
        **{"large.geojson": [feature("one"), feature("two")], "small.geojson": [feature("only")]},
    )
    with ZipFile(path) as package:
        limit = package.getinfo("small.geojson").file_size + 1
    result = list(iowa.scan(path, max_member_bytes=limit))
    assert result[0]["error"] == "scope_member_byte_limit" and result[0]["records"] == []
    assert len(result[1]["records"]) == 1 and result[1]["error"] is None
