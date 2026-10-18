import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.native_api import CatalogHTTPError, Cursors
from bord_food_api.platform import Platform
from bord_food_api.settings import Settings


@pytest.fixture
def native(tmp_path):
    settings = Settings(data_dir=tmp_path, api_key="test-read-key", auto_download=False)
    platform = Platform(tmp_path)
    client = TestClient(create_app(settings))
    client.headers["X-Api-Key"] = "test-read-key"
    return platform, client


def record(kind, key, **payload):
    return {"kind": kind, "source_key": key, "payload": payload}


def seed(platform):
    platform.sync(
        "synthetic",
        "stores",
        "1",
        [
            record(
                "store",
                "a",
                name="Fixture A",
                address={"region": "IA"},
                latitude=41.0,
                longitude=-91.0,
                chain_key="fixture",
                chain_name="Fixture",
            ),
            record(
                "store",
                "b",
                name="Fixture B",
                address={"region": "IA"},
                latitude=41.01,
                longitude=-91.0,
                chain_key="fixture",
                chain_name="Fixture",
            ),
            record(
                "store",
                "c",
                name="Fixture C",
                address={"region": "IL"},
                latitude=42,
                longitude=-91,
                chain_key="fixture",
                chain_name="Fixture",
            ),
        ],
    )
    platform.sync(
        "open_food_facts",
        "products",
        "1",
        [
            record(
                "product",
                "012345678905",
                name="Fixture Food",
                gtin14="00012345678905",
                nutrition={"energy": 0},
                measures=[{"amount": 10, "unit": "g", "basis": "mass"}],
                chain_evidence=[{"scope": "chain", "name": "Fixture"}],
            )
        ],
    )


def test_empty_status_auth_readiness_and_validation(native):
    _, client = native
    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/v1/system/status").json()["data"]["state"] == "empty"
    error = client.get("/v1/stores").json()["error"]
    assert error["code"] == "CATALOG_NOT_READY" and error["retryable"]
    assert client.get("/v1/stores?lat=40").status_code == 422
    assert client.get("/v1/stores?limit=101").json()["error"]["code"] == "INVALID_INPUT"
    assert client.get("/v1/system/status", headers={"X-Api-Key": "wrong"}).status_code == 401
    assert not client.get("/v1/system/status").json()["meta"]["catalog_generation"]


def test_stable_generation_cursor_filters_exact_distance_and_etag(native):
    platform, client = native
    seed(platform)
    response = client.get("/v1/stores?limit=1&state=IA")
    assert response.status_code == 200
    first = response.json()
    cursor = first["meta"]["next_cursor"]
    old_generation = first["meta"]["catalog_generation"]
    assert cursor
    assert response.headers["etag"].startswith('"')
    assert (
        client.get("/v1/stores", params={"limit": 1, "state": "IL", "cursor": cursor}).status_code
        == 409
    )
    platform.sync(
        "synthetic",
        "stores",
        "2",
        [
            record(
                "store", "d", name="Fixture D", address={"region": "IA"}, latitude=41, longitude=-91
            )
        ],
    )
    second = client.get("/v1/stores", params={"limit": 1, "state": "IA", "cursor": cursor}).json()
    assert second["meta"]["catalog_generation"] == old_generation
    assert first["data"][0]["id"] != second["data"][0]["id"]
    nearby = client.get("/v1/stores?lat=41&lon=-91&radius_km=0.5").json()["data"]
    assert nearby and all(row["latitude"] == 41 for row in nearby)
    assert len(client.get("/v1/chains").json()["data"]) == 1
    assert client.get("/v1/stores?query=absent").json()["data"] == []


def test_strict_resolution_revision_measures_and_no_household_side_effects(native):
    platform, client = native
    seed(platform)
    result = client.post(
        "/v1/products/resolve",
        json={
            "identifiers": [
                {"namespace": "gtin", "value": "012345678905"},
                {"namespace": "gtin", "value": "012345678906"},
                {"namespace": "retailer_sku", "value": "012345678905"},
            ]
        },
    ).json()["data"]
    assert [item["status"] for item in result] == ["exact", "invalid", "invalid"]
    product_id = result[0]["candidates"][0]["id"]
    food = client.get("/v1/foods/open_food_facts/012345678905").json()["data"]
    assert food["nutrition"]["energy"] == 0
    assert client.get("/v1/foods/open_food_facts/012345678905?revision=old").status_code == 409
    measures = client.get("/v1/foods/open_food_facts/012345678905/measures?basis=mass").json()
    assert measures["data"] == [{"amount": 10, "unit": "g", "basis": "mass"}]
    assert (
        client.get("/v1/foods/open_food_facts/012345678905/measures?basis=volume").json()["data"]
        == []
    )
    before = platform.current()
    enriched = client.post(
        "/v1/shopping/enrich",
        json={"lines": [{"line_id": "household-private-line", "product_id": product_id}]},
    ).json()["data"][0]
    evidence = enriched["retail_evidence"]
    assert evidence["availability"] == "unknown" and evidence["offers"] == []
    assert evidence["placements"] == [] and evidence["assortment_status"] == "unknown"
    assert evidence["chain_evidence"]
    assert platform.current() == before
    assert (
        client.post("/v1/shopping/enrich", json={"lines": [{"line_id": "x"}] * 101}).status_code
        == 422
    )


def test_changes_cursor_secret_persistence_expiry_and_fixed_asset_rights(native, tmp_path):
    platform, client = native
    seed(platform)
    first = client.get("/v1/catalog/changes?limit=1").json()
    assert len(first["data"]) == 1
    second = client.get(
        "/v1/catalog/changes", params={"after": first["meta"]["next_cursor"], "limit": 100}
    ).json()
    assert second["data"][0]["seq"] > first["data"][0]["seq"]
    assert client.get("/v1/catalog/changes?after=forged").status_code == 409
    cursors = Cursors(tmp_path, clock=lambda: time.time() - 7200)
    token = cursors.encode({"generation": "g_foo", "last": "a", "filters": "a"})
    with pytest.raises(CatalogHTTPError):
        Cursors(tmp_path).decode(token)
    assert (tmp_path / ".cursor_secret").stat().st_mode & 0o777 == 0o600
    store_id = platform.records("store")[0]["id"]
    platform.sync(
        "synthetic",
        "maps",
        "1",
        [
            record(
                "map",
                "m",
                store_id=store_id,
                rights_status="pending",
                display_permitted=False,
                assets={"original": {"sha256": "a" * 64, "media_type": "application/pdf"}},
            )
        ],
    )
    map_id = platform.records("map")[0]["id"]
    maps = client.get(f"/v1/stores/{store_id}/maps").json()["data"]
    assert "assets" not in maps[0]
    assert client.get(f"/v1/maps/{map_id}/assets/original").status_code == 403
    assert client.get(f"/v1/maps/{map_id}/assets/arbitrary").status_code == 422
    current = client.get("/v1/catalog/generations/current").json()
    assert "objects/" not in str(current)


def test_shared_contract_fixtures_validate():
    import json
    from pathlib import Path

    from bord_food_api.domain import normalize_gtin
    from bord_food_api.native_api import Envelope, ErrorEnvelope

    fixtures = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"
    identifiers = json.loads((fixtures / "identifiers.json").read_text())
    for case in identifiers["cases"]:
        assert normalize_gtin(case["input"]) == case["expected"]
    responses = json.loads((fixtures / "native-responses.json").read_text())["responses"]
    for case in responses.values():
        body = case["body"]
        if "error" in body:
            ErrorEnvelope.model_validate(body)
        elif "schema_version" in body:
            Envelope[dict | list].model_validate(body)


def test_concurrent_cursor_initialization_and_corrupt_catalog(native, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: Cursors(tmp_path / "concurrent").secret, range(24)))
    assert len(set(keys)) == 1 and len(keys[0]) == 32
    platform, client = native
    seed(platform)
    path = platform.object_path(platform.current()["packs"]["stores"])
    path.chmod(0o644)
    path.write_bytes(b"corrupt object")
    response = client.get("/v1/stores")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
    assert str(tmp_path) not in response.text


def test_permitted_asset_requires_separate_rights_integrity_and_safe_path(native, tmp_path):
    import hashlib

    platform, client = native
    seed(platform)
    content = b"%PDF-1.4\nSynthetic map fixture; never downloaded"
    digest = hashlib.sha256(content).hexdigest()
    media = tmp_path / "objects" / "media"
    media.mkdir()
    (media / digest).write_bytes(content)
    payload = {
        "rights_status": "permitted",
        "display_permitted": True,
        "assets": {"original": {"sha256": digest, "media_type": "application/pdf"}},
    }
    platform.sync("synthetic", "maps", "1", [record("map", "fixture", **payload)])
    map_id = platform.records("map")[0]["id"]
    path = f"/v1/maps/{map_id}/assets/original"
    assert client.get(path).status_code == 403  # storage permission is independent
    payload["storage_permitted"] = True
    platform.sync("synthetic", "maps", "2", [record("map", "fixture", **payload)])
    response = client.get(path)
    assert response.status_code == 200 and response.content == content
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment")
    (media / digest).write_bytes(b"corrupt map")
    assert client.get(path).status_code == 503
    (media / digest).unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(content)
    (media / digest).symlink_to(outside)
    assert client.get(path).status_code == 404
    payload["assets"]["original"]["media_type"] = "image/svg+xml"
    platform.sync("synthetic", "maps", "3", [record("map", "fixture", **payload)])
    assert client.get(path).status_code == 403


def test_retail_history_does_not_infer_stock_and_stale_map_anchor_is_withheld(native):
    from datetime import UTC, datetime, timedelta

    platform, client = native
    seed(platform)
    product_id = platform.records("product")[0]["id"]
    store_id = platform.records("store")[0]["id"]
    platform.sync(
        "synthetic",
        "evidence",
        "1",
        [
            record(
                "price",
                "p",
                product_id=product_id,
                store_id=store_id,
                amount_decimal="0.00",
                currency="USD",
                channel="in_store",
                observed_at="2000-01-01",
                valid_until="2000-01-02",
            ),
            record(
                "placement",
                "old",
                product_id=product_id,
                store_id=store_id,
                aisle="10",
                map_id="nonexistent",
                map_version="old",
            ),
        ],
    )
    endpoint = f"/v1/products/{product_id}/retail-evidence?store_id={store_id}"
    evidence = client.get(endpoint).json()["data"]
    assert evidence["assortment_status"] == "historical_only"
    assert evidence["availability"] == "unknown"
    assert evidence["offers"][0]["amount_decimal"] == "0.00"
    assert not evidence["capabilities"]["current_stock"]
    assert evidence["placements"] == []
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    platform.sync(
        "synthetic",
        "stock",
        "1",
        [
            record(
                "stock",
                "s",
                product_id=product_id,
                store_id=store_id,
                availability="available",
                valid_until=future,
            )
        ],
    )
    evidence = client.get(endpoint).json()["data"]
    assert evidence["availability"] == "available"
    assert evidence["capabilities"]["current_stock"]
    assert evidence["reason"] is None


def test_source_rights_revocation_applies_to_retained_generations_and_assets(native, tmp_path):
    from bord_food_api.importer import build_catalog

    platform, client = native
    seed(platform)
    platform.sync(
        "open_food_facts",
        "products",
        "2",
        [record("product", "4006381333931", name="Second Synthetic Food", gtin14="04006381333931")],
        complete=False,
    )
    old = client.get("/v1/products?limit=1").json()
    assert old["meta"]["next_cursor"]
    product_id = old["data"][0]["id"]
    platform.control.restrict_source("open_food_facts", reason="synthetic rights test")
    assert client.get(f"/v1/products/{product_id}").status_code == 404
    assert client.get("/v1/products").json()["data"] == []
    retained = client.get("/v1/products", params={"limit": 1, "cursor": old["meta"]["next_cursor"]})
    assert retained.status_code == 200 and retained.json()["data"] == []
    assert client.get("/v1/foods/open_food_facts/012345678905").status_code == 404
    capabilities = client.get("/v1/capabilities").json()["data"]["sources"]["open_food_facts"]
    assert capabilities["rights_blocked"] and not capabilities["available"]
    fixture = Path(__file__).parent / "fixtures" / "foods.json"
    build_catalog([fixture], tmp_path / "foods.sqlite")
    platform.adopt_legacy()
    assert client.get("/v1/foods/usda_fdc/1001").status_code != 403
    platform.control.restrict_source("local_usda", reason="synthetic USDA rights test")
    assert client.get("/v1/foods/usda_fdc/1001").status_code == 403


def test_readiness_closes_each_database_connection(native, monkeypatch):
    import sqlite3
    from types import SimpleNamespace

    from bord_food_api import native_api

    platform, client = native
    seed(platform)
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = sqlite3.connect(*args, check_same_thread=False, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(
        native_api, "sqlite3", SimpleNamespace(connect=tracked_connect, Error=sqlite3.Error)
    )
    for _ in range(25):
        assert client.get("/ready").status_code == 503  # USDA pack is not published.
    assert len(connections) == 25
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_source_food_lookup_and_precomputed_chain_counts_avoid_full_catalog_scans(
    native, monkeypatch
):
    platform, client = native
    seed(platform)
    original_iter = Platform.iter_records

    def no_materialized_catalog(*args, **kwargs):
        raise AssertionError("Exact source lookup must not materialize a catalog")

    def no_store_scan(self, kind, *args, **kwargs):
        assert kind != "store", "Published chain counts must not trigger a full store scan"
        yield from original_iter(self, kind, *args, **kwargs)

    monkeypatch.setattr(Platform, "records", no_materialized_catalog)
    monkeypatch.setattr(Platform, "iter_records", no_store_scan)
    food = client.get("/v1/foods/open_food_facts/012345678905")
    assert food.status_code == 200
    assert food.json()["data"]["nutrition"]["energy"] == 0
    chains = client.get("/v1/chains")
    assert chains.status_code == 200
    assert chains.json()["data"][0]["observed_store_count"] == 3


def test_capabilities_separate_actual_run_freshness_from_checks_and_policy(
    native, tmp_path, monkeypatch
):
    import json

    platform, client = native
    platform.sync(
        "all_the_places",
        "fixture_spider",
        "old-run",
        [record("store", "fixture", name="Synthetic old branch")],
        cursor={"source_run": "2000-01-01"},
    )
    source = client.get("/v1/capabilities").json()["data"]["sources"]["all_the_places"]
    assert source["last_feed_check_at"] is not None
    assert source["source_observed_at"].startswith("2000-01-01")
    assert source["source_age_seconds"] > 20 * 365 * 86400
    assert source["evidence_stale"] and source["stale"]
    assert not source["partitions"]["fixture_spider"]["feed_check_stale"]
    platform.control.set_source("all_the_places", False)
    source = client.get("/v1/capabilities").json()["data"]["sources"]["all_the_places"]
    assert not source["enabled"] and source["available"]
    platform.control.set_action("all_the_places", "can_display", False)
    source = client.get("/v1/capabilities").json()["data"]["sources"]["all_the_places"]
    assert source["rights_blocked"] and not source["available"]
    config = tmp_path / "readiness-policy.json"
    config.write_text(json.dumps({"runtime": {"required_packs": ["stores"]}}))
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(config))
    ready = client.get("/ready")
    assert ready.status_code == 503
    assert ready.json()["packs"]["stores"] == {"available": False, "reason": "rights_blocked"}


def test_capabilities_do_not_infer_opaque_run_dates_and_warn_unaligned_off(native):
    platform, client = native
    platform.sync(
        "all_the_places",
        "fixture_spider",
        "opaque",
        [record("store", "fixture", name="Synthetic opaque run")],
        cursor={"source_run": "opaque-run-2000-01-01"},
    )
    platform.sync(
        "open_food_facts",
        "products",
        "snapshot",
        [record("product", "012345678905", name="Synthetic snapshot")],
        cursor={
            "snapshot_only": True,
            "watermark": None,
            "alignment_status": "baseline_extraction_boundary_unresolved",
        },
    )
    sources = client.get("/v1/capabilities").json()["data"]["sources"]
    assert sources["all_the_places"]["source_observed_at"] is None
    assert sources["all_the_places"]["source_age_seconds"] is None
    off = sources["open_food_facts"]
    assert off["source_observed_at"] is None
    assert off["warnings"][0]["code"] == "DELTA_ALIGNMENT_UNRESOLVED"
    platform.sync(
        "open_food_facts",
        "products",
        "aligned",
        [],
        complete=False,
        cursor={"snapshot_only": False, "watermark": 946684800},
    )
    off = client.get("/v1/capabilities").json()["data"]["sources"]["open_food_facts"]
    assert off["source_observed_at"].startswith("2000-01-01") and off["evidence_stale"]


def test_each_native_request_binds_exactly_one_manifest_snapshot(native, monkeypatch):
    platform, client = native
    platform.sync("synthetic", "stores", "old", [record("store", "old", name="Old snapshot")])
    old = platform.current()
    platform.sync("synthetic", "stores", "new", [record("store", "new", name="New snapshot")])
    new = platform.current()
    reads = []

    def alternating_current(self):
        snapshot = old if len(reads) % 2 == 0 else new
        reads.append(snapshot["generation"])
        return snapshot

    monkeypatch.setattr(Platform, "current", alternating_current)
    for path in (
        "/v1/stores",
        "/v1/system/status",
        "/v1/capabilities",
        "/v1/catalog/generations/current",
        "/ready",
        "/live",
    ):
        before = len(reads)
        response = client.get(path)
        assert len(reads) == before + 1, path
        payload = response.json()
        if "meta" in payload:
            assert payload["meta"]["catalog_generation"] == reads[-1]
        if path == "/v1/stores":
            assert payload["data"][0]["name"] == "Old snapshot"
        if path == "/v1/system/status":
            assert payload["data"]["catalog_generation"] == payload["meta"]["catalog_generation"]
    assert client.get("/live").status_code == 200


def test_liveness_survives_invalid_manifest_while_native_routes_report_unavailable(
    native, monkeypatch
):
    _, client = native

    def invalid_current(self):
        raise ValueError("synthetic damaged manifest")

    monkeypatch.setattr(Platform, "current", invalid_current)
    assert client.get("/live").status_code == 200
    for path in ("/ready", "/v1/system/status", "/v1/stores"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"


def test_reviewed_product_alias_keeps_exact_source_nutrition(native):
    platform, client = native
    seed(platform)
    original = platform.records("product")[0]
    second = record(
        "product",
        "second",
        name="Second source revision",
        gtin14="00012345678905",
        nutrition={"energy": 99},
    )
    platform.sync("open_food_facts", "products", "2", [second], complete=False)
    target = platform.control.identity("open_food_facts", "product", "second")
    platform.control.alias(
        "open_food_facts", "product", "012345678905", target, "reviewed same trade item"
    )
    platform.sync("open_food_facts", "products", "3", [second], complete=False)
    canonical = client.get(f"/v1/products/{original['id']}").json()["data"]
    assert canonical["id"] == target and canonical["nutrition"]["energy"] == 99
    source = client.get("/v1/foods/open_food_facts/012345678905").json()["data"]
    assert source["data"]["nutrition"]["energy"] == 0
    assert source["canonical_product_id"] == target


def test_branch_stock_requires_branch_scope_and_evidence_is_bounded(native):
    from datetime import UTC, datetime, timedelta

    platform, client = native
    seed(platform)
    product = platform.records("product")[0]["id"]
    store_id = platform.records("store")[0]["id"]
    expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    platform.sync(
        "synthetic",
        "evidence",
        "1",
        [
            record(
                "stock",
                "stock",
                product_id=product,
                store_id=store_id,
                availability="available",
                valid_until=expiry,
            ),
            *[
                record(
                    "price",
                    str(n),
                    product_id=product,
                    store_id=store_id,
                    amount="0.00",
                    currency="USD",
                )
                for n in range(105)
            ],
        ],
    )
    endpoint = f"/v1/products/{product}/retail-evidence"
    unscoped = client.get(endpoint).json()["data"]
    assert unscoped["availability"] == "unknown"
    assert not unscoped["capabilities"]["current_stock"]
    assert len(unscoped["offers"]) == 100 and unscoped["history_truncated"]
    scoped = client.get(endpoint, params={"store_id": store_id}).json()["data"]
    assert scoped["availability"] == "available"
