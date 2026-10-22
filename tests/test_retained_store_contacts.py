import importlib.util
from pathlib import Path

from bord_food_api.store_enrichment import assertion, reconcile_fields

spec = importlib.util.spec_from_file_location(
    "retained_contacts", Path(__file__).parents[1] / "scripts/enrich-retained-stores.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_shared_provider_contact_is_retained_and_withdrawn_without_clock_changes():
    now = 1792500000
    stores, evidence = [], {}
    for identity in ["one", "two"]:
        row = assertion(
            identity,
            "email",
            "office@fixture.test",
            source_id="overture_places",
            record_id=identity,
            source_url="https://fixture.test/",
            checked_at=now,
            lineage="provider:fixture",
            branch_match="exact_address",
        )
        stores.append(reconcile_fields({"id": identity, "country": "US"}, [row], now=now))
        evidence[identity] = [row]
    adjusted, count = module.hold_shared_provider_emails(stores, evidence)
    assert count == 4
    for original, adjusted_store in zip(stores, adjusted, strict=True):
        result = reconcile_fields(adjusted_store, evidence[original["id"]], now=now)
        assert original["email"] == "office@fixture.test"
        assert "email" not in result
        assert result["field_provenance"]["email"]["status"] == "withdrawn"
        assert result["field_evidence"][0]["checked_at"] == now
        assert result["field_evidence"][0]["raw_value"] == "office@fixture.test"
        assert result["field_evidence"][0]["shared_location_count"] == 2


def test_retained_osm_exact_join_after_address_cleanup_is_not_a_new_identity(tmp_path):
    import json

    from bord_food_api.platform import Platform

    now = 1792500000
    p = Platform(tmp_path)
    payload = {
        "name": "Fixture Cooperative",
        "country": "US",
        "address": {
            "street": "10 West Main St",
            "city": "Omaha",
            "region": "NE",
            "postal_code": "68102",
        },
    }
    p.sync("fixture", "NE", "one", [{"kind": "store", "source_key": "one", "payload": payload}])
    identity = p.records("store")[0]["id"]
    d = tmp_path / "discovery/fixture"
    d.mkdir(parents=True)
    (d / "bundle.json").write_text(json.dumps({"acquired_at": now, "candidate_sha256": "fixture"}))
    (d / "crosswalk.jsonl").write_text("")
    candidate = {
        "source": "openstreetmap",
        "source_key": "osm:node/1",
        "category": "include",
        "payload": {
            **payload,
            "source_url": "https://www.openstreetmap.org/node/1",
            "source_record": {"phone": "4025551234", "opening_hours": "Mo-Su 08:00-20:00"},
        },
    }
    (d / "candidates.jsonl").write_text(json.dumps(candidate) + "\n")
    # A later-staged different state must not hide the selected state's retained
    # source bundle. No other-state activation or identity mutation is involved.
    other = tmp_path / "discovery/z-other-state"
    other.mkdir()
    (other / "bundle.json").write_text(json.dumps({"state": "IA", "acquired_at": now}))
    (other / "crosswalk.jsonl").write_text("")
    (other / "candidates.jsonl").write_text("")
    plan = module.prepare(tmp_path, state="NE", now=now)
    assert len(plan["records"]) == 1 and plan["records"][0]["id"] == identity
    assert plan["records"][0]["phone"] == "+14025551234"
    assert plan["records"][0]["field_evidence"][0]["branch_match"] == "exact_address"
    assert p.get("store", identity).get("phone") is None
