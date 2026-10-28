"""Exact lookups stay indexed, source-aware and generation-bound at catalog scale."""

import hashlib
import json
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.platform import Platform, ProductIndexUnavailable, _sqlite
from bord_food_api.settings import Settings

GTIN = "00012345678905"


def product(key, **payload):
    return {"kind": "product", "source_key": key, "payload": {"name": key, **payload}}


def request(client, *identifiers):
    return client.post("/v1/products/resolve", json={"identifiers": list(identifiers)})


def test_exact_resolution_uses_index_and_preserves_candidate_semantics(tmp_path, monkeypatch):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "all",
        "1",
        [
            product(
                "a",
                gtin14=GTIN,
                identifiers=[
                    {"namespace": "gtin", "value": "012345678905"},
                    {"namespace": "retailer_sku", "value": "0007", "chain_id": "chain_a"},
                    {"namespace": "plu", "value": "4011", "chain_id": "chain_a"},
                ],
            ),
            product("b", identifiers=[{"namespace": "gtin", "value": "012345678905"}]),
            product(
                "other-chain",
                identifiers=[
                    {"namespace": "retailer_sku", "value": "0007", "chain_id": "chain_b"},
                ],
            ),
            product("prefix-only", gtin14="00012345678906"),  # Invalid check digit.
        ],
    )

    def no_scan(*args, **kwargs):
        raise AssertionError("Barcode resolution must not scan the product pack")

    monkeypatch.setattr(Platform, "iter_records", no_scan)
    monkeypatch.setattr(Platform, "records", no_scan)
    client = TestClient(create_app(Settings(data_dir=tmp_path)))
    before = p.current()
    identifiers = [
        {"namespace": "gtin", "value": "012345678905"},
        {"namespace": "gtin", "value": GTIN},
        {"namespace": "retailer_sku", "value": "0007", "chain_id": "chain_a"},
        {"namespace": "retailer_sku", "value": "0007", "chain_id": "chain_b"},
        {"namespace": "retailer_sku", "value": "0007", "chain_id": "absent"},
        {"namespace": "plu", "value": "4011", "chain_id": "chain_a"},
        {"namespace": "plu", "value": "4011"},
        {"namespace": "gtin", "value": "012345678906"},
        {"namespace": "gtin", "value": "00000000000000"},
    ]
    response = request(client, *identifiers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert [r["status"] for r in data] == [
        "candidates",
        "candidates",
        "exact",
        "exact",
        "not_found",
        "exact",
        "invalid",
        "invalid",
        "not_found",
    ]
    assert len(data[0]["candidates"]) == 2  # Same product's raw/padded GTIN is deduped.
    assert data[0]["candidates"] == data[1]["candidates"]
    assert data[2]["candidates"][0]["name"] == "a"
    assert data[3]["candidates"][0]["name"] == "other-chain"
    assert p.current() == before
    path = p.object_path(before["packs"]["products"])
    with _sqlite(path.as_uri() + "?mode=ro", uri=True) as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT e.payload FROM product_identifiers i "
            "CROSS JOIN entities e ON e.kind='product' AND e.id=i.product_id "
            "WHERE i.namespace=? AND i.value=? AND i.chain_id=? ORDER BY e.id",
            ("gtin", GTIN, ""),
        ).fetchall()
        assert not any("SCAN" in row[3] for row in plan)
        assert "SEARCH i USING PRIMARY KEY" in plan[0][3]
        assert any("kind=? AND id=?" in row[3] for row in plan)


def test_index_updates_are_generation_bound_and_respect_rights_and_aliases(tmp_path):
    p = Platform(tmp_path)
    records = [product("a", gtin=GTIN), product("b", gtin=GTIN)]
    old = p.sync("fixture", "all", "1", records)["manifest"]
    target = p.control.identity("fixture", "product", "b")
    p.control.alias("fixture", "product", "a", target, "reviewed duplicate")
    p.sync("fixture", "all", "1", records)
    assert len(p.product_candidates("gtin", GTIN)) == 1
    assert len(p.product_candidates("gtin", GTIN, generation=old["generation"])) == 2
    p.sync("fixture", "all", "2", [product("a", gtin=GTIN), product("b", gtin="00000000000000")])
    assert p.product_candidates("gtin", GTIN) == []
    assert len(p.product_candidates("gtin", "00000000000000")) == 1
    p.control.restrict_source("fixture")
    assert p.product_candidates("gtin", GTIN, generation=old["generation"]) == []
    p.purge_revoked(quiesced=True)
    path = p.object_path(p.current()["packs"]["products"])
    with _sqlite(path.as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("SELECT count(*) FROM product_identifiers").fetchone()[0] == 0


def legacy_pack(p):
    p.sync("fixture", "all", "1", [product("a", gtin14=GTIN)])
    before = p.current()
    private = p.root / "staging" / "legacy.sqlite"
    original = p.object_path(before["packs"]["products"])
    shutil.copyfile(original, private)
    with _sqlite(private) as db:
        db.execute("DROP TABLE product_identifiers")
    relative = p._seal(private)
    return p._publish(
        {**before["packs"], "products": relative},
        "operator",
        "legacy_fixture",
        "1",
        None,
        "1",
        [],
        source_snapshot=before["sources"],
        identity_snapshot=before,
        acknowledge=False,
    )


@pytest.mark.parametrize("crash", [None, "before_switch", "after_switch"])
def test_reindex_publishes_atomically_preserves_entities_and_source_clocks(tmp_path, crash):
    p = Platform(tmp_path)
    before = legacy_pack(p)
    original = p.object_path(before["packs"]["products"])
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    with _sqlite(original.as_uri() + "?mode=ro", uri=True) as db:
        entities = db.execute("SELECT * FROM entities").fetchall()
    with p.control.connect() as db:
        checkpoints = [tuple(r) for r in db.execute("SELECT * FROM source_state")]

    def hook(point):
        if point == crash:
            raise RuntimeError("simulated crash")

    if crash:
        with pytest.raises(RuntimeError, match="simulated crash"):
            p.reindex_products(hook=hook)
    else:
        p.reindex_products()
    p.recover()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    if crash == "before_switch":
        assert p.current() == before
        with pytest.raises(ProductIndexUnavailable):
            p.product_candidates("gtin", GTIN)
        p.reindex_products()
    after = p.current()
    assert after["sources"] == before["sources"]
    assert after["registry_revision"] == before["registry_revision"]
    assert after["redirects"] == before["redirects"]
    with p.control.connect() as db:
        assert [tuple(r) for r in db.execute("SELECT * FROM source_state")] == checkpoints
    with _sqlite(p.object_path(after["packs"]["products"]).as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("SELECT * FROM entities").fetchall() == entities
    assert len(p.product_candidates("gtin", GTIN)) == 1
    assert p.reindex_products() == after


def test_missing_index_and_database_deadline_return_retryable_json(tmp_path, monkeypatch):
    p = Platform(tmp_path)
    legacy_pack(p)
    client = TestClient(create_app(Settings(data_dir=tmp_path)))
    response = request(client, {"namespace": "gtin", "value": GTIN})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PRODUCT_INDEX_NOT_READY"
    assert response.json()["error"]["retryable"]

    def interrupted(*args, **kwargs):
        raise sqlite3.OperationalError("interrupted private details")

    monkeypatch.setattr(Platform, "product_candidates", interrupted)
    response = request(client, {"namespace": "gtin", "value": GTIN})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
    assert response.json()["error"]["retryable"]
    assert "private details" not in json.dumps(response.json())


def test_legacy_pack_gets_index_on_next_product_import_and_cli_is_offline(
    tmp_path, monkeypatch, capsys
):
    import sys

    from bord_food_api.__main__ import main

    p = Platform(tmp_path)
    legacy_pack(p)
    p.sync("fixture", "all", "2", [product("a", gtin14=GTIN, name="Updated")])
    assert p.product_candidates("gtin", GTIN)[0]["name"] == "Updated"
    before = legacy_pack(p)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["bord_food_api", "catalog", "reindex-products"])

    def no_network(*args, **kwargs):
        raise AssertionError("Reindex must not acquire source data")

    monkeypatch.setattr("bord_food_api.transport.Transport.get", no_network)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["generation"] == p.current()["generation"]
    assert result["generation"] != before["generation"]
    assert len(p.product_candidates("gtin", GTIN)) == 1
