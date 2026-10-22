"""Synthetic state-scoped public directories; external DNS/sockets are denied."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from bord_food_api.sources import atp_run_quality
from bord_food_api.store_discovery import (
    SNAP_ITEM,
    SNAP_LAYER,
    SOURCE,
    acquire_snap,
    address_key,
    osm_candidates,
    reconcile,
    snap_candidates,
)


def provider_row(key=1, name="Synthetic Grocery", **extra):
    return {
        "Record_ID": key,
        "ObjectId": key,
        "Store_Name": name,
        "Store_Type": "Grocery Store",
        "Store_Street_Address": f"{key} North Synthetic Street",
        "City": "Synthetic",
        "State": "IA",
        "Zip_Code": "50000",
        "County": "Synthetic",
        "Latitude": 42.0 + (key % 100) * 0.01,
        "Longitude": -93.0,
        **extra,
    }


def fake_snap(*, truncated=False, changed=False, bad_ids=False):
    calls = []
    metadata_calls = []

    def fetch(url):
        calls.append(url)
        if url.startswith(SNAP_ITEM):
            return {"owner": "FNS_SNAP_RPMD", "url": SNAP_LAYER.rsplit("/", 1)[0]}
        if "/query?" not in url:
            metadata_calls.append(url)
            return {
                "fields": [
                    {"name": n}
                    for n in (
                        "Record_ID",
                        "Store_Name",
                        "Store_Street_Address",
                        "City",
                        "State",
                        "Store_Type",
                        "ObjectId",
                    )
                ],
                "editingInfo": {
                    "dataLastEditDate": 200 if changed and len(metadata_calls) > 1 else 100
                },
            }
        query = parse_qs(urlsplit(url).query)
        assert query["where"] == ["State='IA'"]
        if "returnCountOnly" in query:
            return {"count": 2}
        if "returnIdsOnly" in query:
            return {"objectIds": [1, 1] if bad_ids else [1, 2]}
        return {
            "exceededTransferLimit": truncated,
            "features": [{"attributes": provider_row(i)} for i in (1, 2)],
        }

    return fetch, calls


def test_snap_metadata_and_frozen_identity_pagination_are_complete():
    fetch, calls = fake_snap()
    rows, metadata = acquire_snap(fetch)
    assert len(rows) == 2 and metadata["complete_reference"]
    assert not metadata["all_grocery_census_complete"]
    candidates = snap_candidates(rows, metadata)
    assert [c["source_key"] for c in candidates] == ["snap:1", "snap:2"]
    assert all(c["category"] == "include" for c in candidates)
    assert len(calls) == 6


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"truncated": True}, "truncated_page"),
        ({"changed": True}, "snapshot_changed"),
        ({"bad_ids": True}, "reference_count_mismatch"),
    ],
)
def test_snap_rejects_truncated_unstable_or_duplicate_snapshot(options, reason):
    fetch, _ = fake_snap(**options)
    with pytest.raises(ValueError, match=reason):
        acquire_snap(fetch)


def test_scope_excludes_dollar_convenience_and_specialists_without_excluding_dollar_fresh():
    _, meta = acquire_snap(fake_snap()[0])
    rows = [
        provider_row(1, "Dollar General 100", Store_Type="Super Store"),
        provider_row(2, "Synthetic Fuel", Store_Type="Convenience Store"),
        provider_row(3, "Synthetic Meats", Store_Type="Specialty Store"),
        provider_row(4, "Dollar Fresh", Store_Type="Supermarket"),
        provider_row(5, "Unknown retailer", Store_Type="Other"),
    ]
    assert [r["category"] for r in snap_candidates(rows, meta)] == [
        "exclude",
        "exclude",
        "exclude",
        "include",
        "review",
    ]


def candidate(
    key="snap:1",
    name="Synthetic Grocery",
    street="1 North Synthetic Street",
    city="Synthetic",
    **extra,
):
    p = {
        "name": name,
        "address": {"street": street, "city": city, "region": "IA"},
        "latitude": 42.0,
        "longitude": -93.0,
        "source_url": "https://source.test/directory",
        "license": "fixture",
        **extra,
    }
    return {
        "source": "usda_snap_arcgis",
        "source_key": key,
        "category": "include",
        "reason": "fixture",
        "payload": p,
    }


def test_exact_address_and_name_reconcile_but_name_or_proximity_alone_never_merge():
    existing = {
        "id": "sto_existing",
        "name": "Synthetic Grocery",
        "address": {"full": "1 N Synthetic St, Synthetic, IA 50000"},
        "latitude": 42.0,
        "longitude": -93.0,
    }
    assert address_key(existing) == address_key(candidate()["payload"])
    exact = reconcile([existing], [candidate()])
    assert exact["records"] == [] and exact["crosswalk"][0]["canonical_id"] == "sto_existing"
    near = reconcile([existing], [candidate(street="2 North Synthetic Street")])
    assert (
        near["records"] == [] and near["reviews"][0]["reason"] == "nearby_identity_requires_review"
    )
    unrelated = reconcile([existing], [candidate(name="Unrelated Retailer")])
    assert (
        unrelated["records"] == []
        and unrelated["reviews"][0]["reason"] == "address_identity_conflict"
    )
    far = reconcile([existing], [candidate(street="3 Synthetic Street", latitude=43.0)])
    assert len(far["records"]) == 1


def test_new_cross_source_duplicates_keep_all_native_ids_and_replay_retains_id():
    a = candidate()
    b = {**candidate("osm:node/2"), "source": "openstreetmap"}
    result = reconcile([], [a, b])
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["payload"]["discovery_keys"] == ["snap:1", "osm:node/2"]
    existing = {
        **record["payload"],
        "id": "sto_stable",
        "catalog_source": SOURCE,
        "catalog_source_key": "snap:1",
    }
    second = reconcile([existing], [a, b])
    assert second["summary"]["new_records"] == 0
    assert len(second["records"]) == 1 and second["records"][0]["source_key"] == "snap:1"
    assert all(c["canonical_id"] == "sto_stable" for c in second["crosswalk"])
    moved = candidate(street="900 Other Street")
    assert (
        reconcile([existing], [moved])["reviews"][0]["reason"] == "native_identity_location_changed"
    )


def test_osm_native_ids_attribution_and_query_failure_are_preserved():
    doc = {
        "osm3s": {"timestamp_osm_base": "2026-10-01T00:00:00Z"},
        "elements": [
            {
                "type": "way",
                "id": 1,
                "center": {"lat": 42, "lon": -93},
                "tags": {
                    "name": "Synthetic Grocery",
                    "shop": "supermarket",
                    "addr:housenumber": "1",
                    "addr:street": "Synthetic St",
                    "addr:city": "Synthetic",
                },
            }
        ],
    }
    row = osm_candidates(doc)[0]
    assert row["source_key"] == "osm:way/1" and row["payload"]["license"] == "ODbL-1.0"
    assert row["category"] == "include"
    with pytest.raises(ValueError, match="incomplete_query"):
        osm_candidates({**doc, "remark": "runtime timeout"})
    with pytest.raises(ValueError, match="duplicate_identity"):
        osm_candidates({**doc, "elements": doc["elements"] * 2})


def test_upstream_run_quality_rejects_timeout_missing_stats_queue_and_count_drop():
    good = {
        "finish_reason": "finished",
        "scheduler/enqueued": 100,
        "scheduler/dequeued": 100,
        "item_scraped_count": 90,
    }
    assert atp_run_quality(good)["complete"]
    assert not atp_run_quality({**good, "finish_reason": "closespider_timeout"})["complete"]
    assert not atp_run_quality({**good, "scheduler/enqueued": 101})["complete"]
    assert not atp_run_quality(None)["complete"]
    assert not atp_run_quality(good, previous_count=200)["complete"]


def load_operator():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "iowa_expansion", Path(__file__).parents[1] / "scripts/expand-iowa-directory.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_acquire_publish_and_replay_preserve_existing_store_ids(tmp_path):
    from bord_food_api.platform import Platform

    operator = load_operator()
    root = tmp_path / "catalog"
    p = Platform(root)
    p.sync(
        "fixture",
        "stores",
        "1",
        [
            {
                "kind": "store",
                "source_key": "existing",
                "payload": {
                    "name": "Existing Grocery",
                    "address": {"street": "900 Other Street", "city": "Other", "region": "IA"},
                },
            }
        ],
    )
    original = p.records("store")[0]
    directory = tmp_path / "discovery"
    bundle = operator.acquire(directory, "ops@fixture.invalid", fetch=fake_snap()[0])
    assert bundle["metadata"]["complete_reference"]
    first = operator.publish(directory, root)
    assert first["iowa_records_after"] == 3
    assert p.get("store", original["id"]) == original
    keys = {r["source_id"]: r["id"] for r in p.records("store") if r.get("source_id")}
    second = operator.publish(directory, root)
    assert second["iowa_records_after"] == 3
    assert keys == {r["source_id"]: r["id"] for r in p.records("store") if r.get("source_id")}
    assert second["changed"] == 0


def test_operator_failed_acquisition_leaves_serving_catalog_and_records_untouched(tmp_path):
    from bord_food_api.platform import Platform

    operator = load_operator()
    p = Platform(tmp_path / "catalog")
    p.sync(
        "fixture",
        "stores",
        "1",
        [
            {
                "kind": "store",
                "source_key": "existing",
                "payload": {"name": "Existing Grocery", "address": {"region": "IA"}},
            }
        ],
    )
    before = (p.root / "current.json").read_bytes()
    directory = tmp_path / "failed"
    with pytest.raises(ValueError, match="truncated_page"):
        operator.acquire(directory, "ops@fixture.invalid", fetch=fake_snap(truncated=True)[0])
    assert (p.root / "current.json").read_bytes() == before
    assert not (directory / "bundle.json").exists()
    status = json.loads((directory / "status.json").read_text())
    assert status["state"] == "failed" and status["paid_calls"] == 0


def test_atp_timeout_scope_cannot_supply_absence_evidence(tmp_path):
    import io

    from bord_food_api.sources import acquire_source

    class Mock:
        def get(self, url):
            return io.BytesIO(b'{"run_id":"2026-10-01"}')

        def fetch(self, url, path, validators=None):
            import hashlib

            if "/stats/" in url:
                body = json.dumps(
                    {
                        "finish_reason": "closespider_timeout",
                        "item_scraped_count": 1,
                        "scheduler/enqueued": 10,
                        "scheduler/dequeued": 2,
                    }
                ).encode()
            else:
                body = json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {"type": "Point", "coordinates": [-93, 42]},
                                "properties": {
                                    "name": "Walmart",
                                    "brand": "Walmart",
                                    "ref": "1",
                                    "addr:country": "US",
                                    "addr:state": "IA",
                                },
                            }
                        ],
                    }
                ).encode()
            path.write_bytes(body)
            return {
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "url": url.replace("/latest/", "/2026-10-01/"),
            }

    scope = next(
        acquire_source(
            "all_the_places",
            {"spiders": ["walmart_us"]},
            Mock(),
            tmp_path,
            {"upstream_item_count": 100},
        )
    )
    assert not scope["complete"]
    assert scope["cursor"]["upstream_item_count"] == 100
    assert scope["cursor"]["observed_upstream_item_count"] == 1
    assert len(list(scope["records"])) == 1


@pytest.mark.parametrize("coordinates", [(float("nan"), -93), (42, 0), (None, -93), (90, -93)])
def test_discovery_holds_bad_coordinates_even_for_known_native_identity(coordinates):
    _, meta = acquire_snap(fake_snap()[0])
    row = provider_row(Latitude=coordinates[0], Longitude=coordinates[1])
    proposed = snap_candidates([row], meta)
    known = {**proposed[0]["payload"], "id": "existing", "discovery_keys": ["snap:1"]}
    result = reconcile([known], proposed)
    assert not result["records"] and not result["crosswalk"]
    assert result["reviews"][0]["reason"] == "invalid_or_outside_iowa_coordinates"


def test_native_identity_rename_requires_review():
    old = candidate()["payload"]
    old.update(id="existing", discovery_keys=["snap:1"])
    result = reconcile([old], [candidate(name="Unrelated Grocery")])
    assert not result["records"] and not result["crosswalk"]
    assert result["reviews"][0]["reason"] == "native_identity_name_changed"


def test_snap_bulk_pages_keep_request_urls_bounded():
    template, _ = fake_snap()
    urls = []

    def fetch(url):
        query = parse_qs(urlsplit(url).query)
        if "returnCountOnly" in query:
            return {"count": 205}
        if "returnIdsOnly" in query:
            return {"objectIds": list(range(100000, 100205))}
        if "objectIds" in query:
            urls.append(url)
            ids = [int(i) for i in query["objectIds"][0].split(",")]
            return {"features": [{"attributes": provider_row(i)} for i in ids]}
        return template(url)

    rows, _ = acquire_snap(fetch)
    assert len(rows) == 205 and len(urls) == 3
    assert all(len(url) < 2000 for url in urls)


def test_pharmacy_and_fast_fresh_formats_excluded_but_full_food_drugstore_retained():
    _, meta = acquire_snap(fake_snap()[0])
    rows = [
        provider_row(i, name, Store_Type="Super Store")
        for i, name in enumerate(
            [
                "Hy-Vee Drugstore",
                "Hy-Vee Drug Store 7056",
                "Hy-Vee Fast and Fresh #3",
                "Hartig Drug Company 3",
                "Hy-Vee Food & Drugstore",
                "Hy-Vee Food and Drugstore",
            ],
            1,
        )
    ]
    assert [r["category"] for r in snap_candidates(rows, meta)] == ["exclude"] * 4 + ["include"] * 2


def test_nearby_new_native_keys_are_held_instead_of_duplicated():
    first = candidate("snap:1")
    other = candidate("osm:node/2", street="2 Other Street")
    result = reconcile([], [first, other])
    assert len(result["records"]) == 1
    assert result["reviews"][0]["reason"] == "nearby_new_identity_requires_review"


def test_existing_chain_name_supports_identity_when_store_name_is_just_city():
    known = {
        **candidate()["payload"],
        "name": "Synthetic",
        "chain_name": "Synthetic Grocery",
        "id": "known",
    }
    result = reconcile([known], [candidate()])
    assert not result["records"]
    assert result["crosswalk"][0]["canonical_id"] == "known"


def test_format_review_requires_bound_native_payload_and_evidence():
    import hashlib

    from bord_food_api.store_discovery import apply_reviews

    row = candidate()
    row.update(category="review", reason="store_type_requires_review")
    decision = {
        "source_key": "snap:1",
        "action": "include",
        "payload_sha256": hashlib.sha256(
            json.dumps(row["payload"], sort_keys=True).encode()
        ).hexdigest(),
        "evidence_urls": ["https://official.test/stores"],
        "reviewed_at": "2026-10-20",
        "reason": "Official full grocery directory",
    }
    reviews = {"candidate_sha256": "fixture", "decisions": [decision]}
    applied = apply_reviews([row], reviews, "fixture")
    assert applied[0]["category"] == "include"
    assert applied[0]["payload"]["format_review"]["evidence_urls"]
    with pytest.raises(ValueError, match="bundle_binding"):
        apply_reviews([row], reviews, "other")
    row["payload"]["name"] = "Changed"
    with pytest.raises(ValueError, match="identity_binding"):
        apply_reviews([row], reviews, "fixture")


def test_missing_house_number_is_held_and_coarse_address_never_auto_merges():
    assert address_key({"address": {"street": "10th Avenue North", "city": "Synthetic"}}) is None
    known = {**candidate()["payload"], "id": "existing", "latitude": None, "longitude": None}
    proposed = candidate(street="1 Synthetic St", latitude=None, longitude=None)
    result = reconcile([known], [proposed])
    assert not result["records"] and not result["crosswalk"]
    assert result["reviews"][0]["reason"] == "nearby_identity_requires_review"


def test_matched_secondary_source_geometry_blocks_alternate_address_duplicate():
    known = {**candidate()["payload"], "id": "known", "latitude": None, "longitude": None}
    first = candidate("snap:1")
    other = candidate("osm:node/2", street="200 Alternate Road")
    other["source"] = "openstreetmap"
    result = reconcile([known], [first, other])
    assert not result["records"]
    assert result["crosswalk"][0]["canonical_id"] == "known"
    assert result["reviews"][0]["candidate_ids"] == ["known"]


def test_catalog_reader_defaults_iowa_but_enrichment_can_read_all_states(tmp_path):
    from bord_food_api.platform import Platform
    from bord_food_api.store_discovery import catalog_stores

    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "stores",
        "r1",
        [
            {
                "kind": "store",
                "source_key": region,
                "payload": {"name": region, "address": {"region": region}},
            }
            for region in ["IA", "IL"]
        ],
    )
    assert [r["name"] for r in catalog_stores(tmp_path)] == ["IA"]
    assert len(catalog_stores(tmp_path, state=None)) == 2
    assert [r["name"] for r in catalog_stores(tmp_path, state="IL")] == ["IL"]
