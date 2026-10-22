import copy
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "iowa_places", Path(__file__).parents[1] / "scripts/plan-iowa-places.py"
)
places = importlib.util.module_from_spec(spec)
spec.loader.exec_module(places)


def fixtures():
    payload = {
        "name": "Imaginary Grocery",
        "country": "US",
        "address": {"street": "10 Main St", "city": "Ames", "region": "IA", "postal_code": "50010"},
        "latitude": 42.03,
        "longitude": -93.63,
        "source_url": "https://fixture.test/snap",
        "license": "Public domain",
    }
    snap = {
        "source": "usda_snap_arcgis",
        "source_key": "snap:1",
        "category": "review",
        "reason": "store_type_requires_review",
        "payload": payload,
    }
    place = {
        "id": "gers-fixture",
        "names": {"primary": "Imaginary Grocery"},
        "addresses": [
            {
                "freeform": "10 Main Street",
                "locality": "Ames",
                "region": "IA",
                "country": "US",
                "postcode": "50010",
            }
        ],
        "geometry": {"type": "Point", "coordinates": [-93.63, 42.03]},
        "taxonomy": {"primary": "grocery_store"},
        "_retrieved_at": 1792519000,
        "_source_url": "https://fixture.test/overture",
        "sources": [{"dataset": "meta"}],
    }
    return snap, place


def test_only_new_exact_snap_and_grocery_place_pair_can_add_directory_record():
    snap, place = fixtures()
    result = places.prepare([], [snap], [place])
    assert result["corroborated_new_records"] == 1
    record = result["records"][0]
    assert {s["source_id"] for s in record["payload"]["discovery_sources"]} == {
        "usda_snap_arcgis",
        "overture_places",
    }
    assert record["payload"]["open_status"] == "unknown"
    assert places.prepare([], [], [place])["records"] == []
    assert places.prepare([], [snap, snap], [place])["records"] == []
    for mutate in [
        lambda r: r.update(operating_status="permanently_closed"),
        lambda r: r["taxonomy"].update(primary="pharmacy"),
        lambda r: r["addresses"][0].update(region="NE"),
        lambda r: r["names"].update(primary="Unrelated Business"),
    ]:
        changed = copy.deepcopy(place)
        mutate(changed)
        assert places.prepare([], [snap], [changed])["records"] == []
