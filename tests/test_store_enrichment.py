import json

import pytest

from bord_food_api.crawl_evidence import collect_evidence
from bord_food_api.platform import Platform
from bord_food_api.store_enrichment import (
    assertion,
    publish_enrichment,
    reconcile_fields,
    snapshot_assertions,
)
from bord_food_api.store_hours import derive_timezone, holiday_exceptions, osm_hours, valid_timezone
from bord_food_api.store_sources import source_assertions

NOW = 1792500000


def store(**kwargs):
    return {
        "id": "sto_test",
        "name": "Test Store",
        "country": "US",
        "address": {
            "street": "100 Main St",
            "city": "Ames",
            "region": "IA",
            "postal_code": "50010",
        },
        **kwargs,
    }


def evidence(field="phone", value="(515) 555-1234", source="openstreetmap", **kwargs):
    return assertion(
        "sto_test",
        field,
        value,
        source_id=source,
        record_id="1",
        source_url="https://example.org/store/1",
        checked_at=NOW,
        lineage=source,
        branch_match="exact_address",
        **kwargs,
    )


def test_single_source_and_copies_can_report_but_never_verify():
    for rows in [
        [evidence()],
        [evidence(), evidence(source="jev")],
        [evidence(), {**evidence(source="copy"), "lineage": "openstreetmap"}],
    ]:
        result = reconcile_fields(store(), rows, now=NOW)
        assert result["phone"] == "+15155551234"
        assert result["field_provenance"]["phone"]["status"] == "source_reported"
        assert result["field_provenance"]["phone"]["verified_at"] is None
    assert "phone" not in reconcile_fields(store(), [evidence(source="jev")], now=NOW)


def test_agreement_promotes_normalized_values_and_retains_sources_idempotently():
    rows = [
        evidence(),
        evidence(value="+15155551234", source="retailer_page", authority="official"),
    ]
    result = reconcile_fields(store(), rows, now=NOW)
    assert result["phone"] == "+15155551234"
    assert result["field_provenance"]["phone"]["status"] == "corroborated"
    assert len(result["field_evidence"]) == 2
    again = reconcile_fields(result, rows, now=NOW + 3600)
    assert again == result
    assert snapshot_assertions(result) == []


def test_conflicts_retain_existing_field_and_raw_evidence():
    rows = [evidence(), evidence(value="5155559876", source="retailer_page")]
    result = reconcile_fields(store(phone="5155550000"), rows, now=NOW)
    assert result["phone"] == "5155550000"
    assert result["field_provenance"]["phone"]["status"] == "conflicted"
    assert result["field_conflicts"][0]["field"] == "phone"
    assert {r["raw_value"] for r in result["field_evidence"]} == {"(515) 555-1234", "5155559876"}


def test_old_future_or_wrong_branch_evidence_does_not_verify():
    for bad in [
        {"checked_at": NOW - 100 * 86400},
        {"checked_at": NOW + 1},
        {"branch_match": "unresolved"},
    ]:
        row = {**evidence(source="retailer_page"), **bad}
        result = reconcile_fields(store(), [evidence(), row], now=NOW)
        assert result["field_provenance"]["phone"]["status"] == "source_reported"
        assert result["field_provenance"]["phone"]["verified_at"] is None
        assert row["id"] not in result["field_provenance"]["phone"]["supporting_ids"]


def test_explicit_permanent_closure_requires_official_plus_corroboration():
    rows = [
        evidence("operating_status", "permanently_closed"),
        evidence("operating_status", "permanently_closed", source="foursquare_os"),
    ]
    assert reconcile_fields(store(), rows, now=NOW)["permanently_closed"] is None
    rows.append(
        evidence(
            "operating_status", "permanently_closed", source="retailer_page", authority="official"
        )
    )
    result = reconcile_fields(store(), rows, now=NOW)
    assert result["permanently_closed"] is True and result["lifecycle"] == "closed"
    assert "closed_at" not in result
    assert reconcile_fields(store(), [], now=NOW)["operating_status"] == "unknown"


def test_reviewed_aisle_mapping_requires_bound_audited_review():
    mapping = [
        {
            "category": "en:dairy",
            "aisle": "7",
            "map_version": "v1",
            "route_geometry_validated": False,
        }
    ]
    rows = [
        evidence("aisle_category_mappings", mapping),
        evidence("aisle_category_mappings", mapping, source="retailer_page"),
    ]
    assert "aisle_category_mappings" not in reconcile_fields(store(), rows, now=NOW)
    review = {
        "assertion_id": rows[0]["id"],
        "reviewer": "operator",
        "reason": "Compared branch map and category labels",
        "reviewed_at": NOW,
        "decision": "accept",
    }
    result = reconcile_fields(store(), rows, now=NOW, reviews=[review])
    assert result["aisle_category_mappings"] == mapping
    assert result["field_provenance"]["aisle_category_mappings"]["status"] == "reviewed"
    assert (
        reconcile_fields(result, [], now=NOW + 1)["field_provenance"]["aisle_category_mappings"][
            "status"
        ]
        == "reviewed"
    )
    with pytest.raises(ValueError):
        reconcile_fields(store(), rows, now=NOW, reviews=[{**review, "assertion_id": "unknown"}])


def test_iana_timezone_inference_avoids_split_states_and_preserves_derivation():
    assert derive_timezone(store())["value"] == "America/Chicago"
    for state in ("FL", "AZ", "IN", "TX", "AK", "OR", "NV"):
        assert derive_timezone(store(address={"region": state})) is None
    assert valid_timezone("CST") is None
    result = reconcile_fields(store(), [], now=NOW)
    assert result["field_provenance"]["timezone"]["status"] == "derived"
    assert result["field_provenance"]["timezone"]["verified_at"] is None
    assert reconcile_fields(result, [], now=NOW + 1) == result


def test_weekly_hours_and_dated_holiday_exceptions_never_imply_closure():
    hours = osm_hours("Mo-Fr 08:00-21:00; Sa 09:00-17:00; Su off")
    assert len(hours) == 7 and hours[-1]["closed"]
    assert len(osm_hours("24/7")) == 7
    with pytest.raises(ValueError):
        osm_hours("Mo-Fr 08:00-21:00; PH off")
    special = holiday_exceptions({"validFrom": "2026-12-25", "opens": "00:00", "closes": "00:00"})
    assert special[0]["closed"] and special[0]["valid_through"] == "2026-12-25"
    assert evidence("opening_hours", "Closed permanently")["validation"] == "invalid_or_unsupported"


def test_overture_foursquare_known_shared_lineage_is_not_two_votes():
    s = store()
    overture = source_assertions(
        "overture_places",
        {
            "phones": ["+15155551234"],
            "sources": [{"dataset": "foursquare", "update_time": "2026-10-20T00:00:00Z"}],
        },
        s,
        record_id="gers1",
        source_url="https://docs.overturemaps.org",
        checked_at=NOW,
        branch_match="reviewed_crosswalk",
    )
    fsq = source_assertions(
        "foursquare_os",
        {"tel": "+15155551234"},
        s,
        record_id="fsq1",
        source_url="https://foursquare.com",
        checked_at=NOW,
        branch_match="reviewed_crosswalk",
    )
    result = reconcile_fields(s, overture + fsq, now=NOW)
    assert result["field_provenance"]["phone"]["status"] == "source_reported"
    assert result["field_provenance"]["phone"]["verified_at"] is None


def test_contact_validation_preserves_invalid_assertion_without_promotion():
    for field, value in [
        ("website", "javascript:alert(1)"),
        ("website", "https://example.org/?api_key=secret"),
        ("email", "bad"),
        ("phone", "3"),
    ]:
        row = evidence(field, value)
        assert row["validation"] == "invalid_or_unsupported"
        assert field not in reconcile_fields(store(), [row], now=NOW)


def test_parent_grocery_node_and_abbreviated_address_produce_branch_fields():
    target = {
        "store_id": "sto_test",
        "url": "https://shop.example/store/1",
        "expected_branch": "Ames",
        "source_address": store()["address"],
    }
    branch = {
        "@type": "GroceryStore",
        "name": "Test Store",
        "address": {
            "streetAddress": "100 Main Street",
            "addressLocality": "Ames",
            "addressRegion": "IA",
            "postalCode": "50010-1234",
        },
        "telephone": "5155551234",
        "timeZone": "America/Chicago",
        "specialOpeningHoursSpecification": {
            "validFrom": "2026-12-25",
            "opens": "00:00",
            "closes": "00:00",
        },
        "department": {
            "@type": "Store",
            "name": "Photo center",
            "address": {"streetAddress": "100 Main St", "postalCode": "50010"},
            "telephone": "5155559999",
        },
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps(branch)
        + '</script><a href="/pickup/1">Curbside pickup</a>'
    )
    result = collect_evidence(html, target, retrieved_at=NOW)
    assert result["branch_match"] == "exact_address"
    fields = {r["field"]: r["value"] for r in result["field_assertions"]}
    assert fields["phone"] == "+15155551234"
    assert "pickup_links" not in fields  # Unscoped page link stays a candidate.
    assert fields["hours_exceptions"][0]["closed"]


def test_immutable_field_publication_and_source_refresh_preserve_ids_and_conflicts(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {k: v for k, v in store().items() if k != "id"},
            }
        ],
    )
    original = p.records("store")[0]
    rows = [
        {**evidence(), "store_id": original["id"]},
        {**evidence(source="retailer_page", authority="official"), "store_id": original["id"]},
    ]
    enriched = reconcile_fields(original, rows, now=NOW)
    before = p.current()
    old = p.object_path(before["packs"]["stores"]).read_bytes()
    result = publish_enrichment(
        p, [enriched], base_generation=before["generation"], release="v1", now=NOW
    )
    assert result["changed"] == 1
    assert p.object_path(before["packs"]["stores"]).read_bytes() == old
    published = p.get("store", original["id"])
    assert published["phone"] == "+15155551234"
    assert len(p.records("store")) == 1
    with pytest.raises(ValueError):
        publish_enrichment(
            p, [enriched], base_generation=before["generation"], release="stale", now=NOW
        )
    p.sync(
        "fixture",
        "IA",
        "r2",
        [{"kind": "store", "source_key": "one", "payload": {**store(), "phone": "5155559876"}}],
        complete=False,
    )
    current = p.get("store", original["id"])
    assert current["phone"] == "+15155551234"
    assert current["field_provenance"]["phone"]["status"] == "conflicted"


def test_hidden_support_is_removed_from_promoted_value_and_provenance(tmp_path):
    p = Platform(tmp_path)
    s = store()
    rows = [evidence(), evidence(source="retailer_page", authority="official")]
    enriched = reconcile_fields(s, rows, now=NOW)
    enriched["field_baselines"] = {
        "phone": {"source_id": "fixture", "present": False, "value": None}
    }
    visible = p._visible_payload(enriched, {"retailer_page"})
    assert "phone" not in visible
    assert all(r["source_id"] != "retailer_page" for r in visible["field_evidence"])
    assert visible["field_provenance"]["phone"]["status"] == "rights_restricted"


def test_source_credentials_are_redacted_from_invalid_raw_evidence():
    row = evidence("website", "https://example.org/?api_key=private-value")
    assert "private-value" not in json.dumps(row)
    assert row["validation"] == "invalid_or_unsupported"
    row = evidence("departments", [{"name": "public", "api_key": "private-value"}])
    assert "private-value" not in json.dumps(row)


def test_revocation_blocks_backup_and_purges_derived_field_evidence(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {k: v for k, v in store().items() if k != "id"},
            }
        ],
    )
    original = p.records("store")[0]
    rows = [
        {**evidence(), "store_id": original["id"]},
        {**evidence(source="retailer_page", authority="official"), "store_id": original["id"]},
    ]
    result = reconcile_fields(original, rows, now=NOW)
    publish_enrichment(
        p, [result], base_generation=p.current()["generation"], release="v1", now=NOW
    )
    p.control.restrict_source("retailer_maps", reason="synthetic revocation")
    assert "phone" not in p.get("store", original["id"])
    with pytest.raises(ValueError):
        p.backup(tmp_path / "backup")
    p.purge_revoked(quiesced=True)
    p.assert_permitted(p.current())
    record = p.get("store", original["id"])
    assert all(row["source_id"] != "retailer_page" for row in record["field_evidence"])


def test_microdata_without_jsonld_extracts_identity_bound_contacts_and_hours():
    target = {
        "store_id": "sto_test",
        "url": "https://shop.example/store/1",
        "expected_branch": "Ames",
        "source_address": store()["address"],
    }
    html = """<div itemscope itemtype="https://schema.org/GroceryStore"><span itemprop="name">Test Store</span><div itemprop="address" itemscope itemtype="https://schema.org/PostalAddress"><span itemprop="streetAddress">100 Main Street</span><meta itemprop="postalCode" content="50010"></div><a itemprop="telephone" href="tel:+15155551234">Call store</a><meta itemprop="openingHours" content="Mo-Fr 08:00-21:00"></div><footer><a href="mailto:corporate@example.org">Corporate contact</a></footer>"""
    record = collect_evidence(html, target, retrieved_at=NOW)
    assert record["branch_match"] == "exact_address"
    assert any(
        a["field"] == "phone" and a["branch_match"] == "exact_address"
        for a in record["field_assertions"]
    )
    corporate = next(a for a in record["field_assertions"] if a["field"] == "email")
    assert corporate["scope"] == "page_contact" and corporate["branch_match"] == "unresolved"
    assert "email" not in reconcile_fields(store(), [corporate], now=NOW)
    result = reconcile_fields(
        store(), [corporate, evidence("email", "corporate@example.org")], now=NOW
    )
    meta = result["field_provenance"]["email"]
    assert meta["status"] == "source_reported" and meta["verified_at"] is None
    assert corporate["id"] not in meta["supporting_ids"]


def test_osm_lifecycle_refresh_by_native_id_is_bounded_and_disused_is_not_permanent():
    from bord_food_api.store_sources import osm_fields, osm_verification_query

    assert "out meta center tags" in osm_verification_query(["node/1", "way/2"])
    with pytest.raises(ValueError):
        osm_verification_query(["way/2);out body;"])
    assert (
        osm_fields({"disused:shop": "supermarket"})["operating_status"]
        == "not_operating_unspecified"
    )


def test_operator_publication_receipt_keeps_state_filter_separate_from_outcome(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "enrich_operator", Path(__file__).parents[1] / "scripts/enrich-retained-stores.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "data"
    p = Platform(root)
    p.sync(
        "fixture",
        "stores",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {"name": "Fixture", "country": "US", "address": {"region": "IA"}},
            }
        ],
    )
    directory = tmp_path / "run"
    module.run(root, directory, publish=True, state="IA")
    receipt = json.loads((directory / "publication.json").read_text())
    assert receipt["state"] == "published" and receipt["state_filter"] == "IA"
    assert receipt["generation"] == p.current()["generation"]


def test_direct_official_branch_fills_gap_without_claiming_verification_or_closure():
    row = evidence(source="retailer_page", authority="official")
    result = reconcile_fields(store(), [row], now=NOW)
    assert result["phone"] == "+15155551234"
    p = result["field_provenance"]["phone"]
    assert p["status"] == "source_reported" and p["verified_at"] is None
    assert p["last_checked_at"] == NOW and p["observed_until"] > NOW
    assert reconcile_fields(result, [row], now=NOW + 60) == result
    existing = reconcile_fields(store(phone="+15155559999"), [row], now=NOW)
    assert existing["phone"] == "+15155559999"
    closure = evidence(
        "operating_status", "permanently_closed", source="retailer_page", authority="official"
    )
    assert reconcile_fields(store(), [closure], now=NOW)["operating_status"] == "unknown"
    wrong = {**row, "branch_match": "unresolved"}
    assert "phone" not in reconcile_fields(store(), [wrong], now=NOW)


def test_withdrawn_page_assertion_removes_only_its_reported_gap_and_preserves_evidence(tmp_path):
    from bord_food_api.store_enrichment import publish_crawl_evidence

    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {
                    "name": "Fixture",
                    "country": "US",
                    "address": {
                        "street": "1 Main St",
                        "city": "Ames",
                        "region": "IA",
                        "postal_code": "50010",
                    },
                },
            }
        ],
    )
    s = p.records("store")[0]
    r = assertion(
        s["id"],
        "pickup_links",
        ["https://fixture.test/one/pickup"],
        source_id="retailer_page",
        record_id="https://fixture.test/one",
        source_url="https://fixture.test/one",
        checked_at=NOW,
        lineage="retailer:fixture.test",
        branch_match="exact_address",
        authority="official",
    )
    e = {
        "store_id": s["id"],
        "source_url": "https://fixture.test/one",
        "html_sha256": "first",
        "branch_match": "exact_address",
        "field_assertions": [r],
    }
    publish_crawl_evidence(p, e, now=NOW)
    assert p.get("store", s["id"])["pickup_links"]
    publish_crawl_evidence(p, {**e, "html_sha256": "second", "field_assertions": []}, now=NOW + 60)
    updated = p.get("store", s["id"])
    assert "pickup_links" not in updated
    assert updated["field_provenance"]["pickup_links"]["status"] == "withdrawn"
    assert any(r.get("withdrawn") for r in updated["field_evidence"])


def test_overture_computed_confidence_is_not_an_independent_contact_provider():
    from bord_food_api.store_sources import overture_lineage

    row = {
        "websites": ["https://retailer.test/store/1"],
        "sources": [
            {"property": "", "dataset": "AllThePlaces"},
            {"property": "/properties/confidence", "dataset": "Overture"},
            {"property": "/properties/operating_status", "dataset": "Overture-signals"},
        ],
    }
    assert overture_lineage(row, "phone") == "retailer:retailer.test"
    row["sources"][0]["dataset"] = "Foursquare"
    assert overture_lineage(row, "phone") == "foursquare_os"
    row["sources"].append({"property": "", "dataset": "meta"})
    assert overture_lineage(row, "phone") is None


def test_vendor_host_and_retailer_page_are_one_family_and_latest_direct_hours_win():
    old = evidence("opening_hours", "Mo-Su 08:00-21:00", source="all_the_places")
    old["lineage"] = "retailer:vendor.example"
    old["checked_at"] = NOW - 86400
    fresh = evidence(
        "opening_hours", "Mo-Su 08:00-22:00", source="retailer_page", authority="official"
    )
    fresh["lineage"] = "retailer:retailer.example"
    base = store(chain_id="chn_fixture")
    initial = reconcile_fields(base, [old], now=NOW - 86400)
    updated = reconcile_fields(initial, [fresh], now=NOW)
    assert updated["opening_hours"][0]["closes"] == "22:00"
    assert updated["field_provenance"]["opening_hours"]["status"] == "source_reported"
    assert any(
        r.get("superseded_reason") == "newer_direct_report_from_same_retailer_family"
        for r in updated["field_evidence"]
    )
    assert not updated["field_conflicts"]
    copy = {
        **fresh,
        "source_id": "all_the_places",
        "lineage": "retailer:other-vendor.example",
        "id": "fixture-copy",
    }
    same = reconcile_fields(base, [fresh, copy], now=NOW)
    assert same["field_provenance"]["opening_hours"]["status"] == "source_reported"
    independent = evidence("opening_hours", "Mo-Su 08:00-21:00")
    conflict = reconcile_fields(initial, [fresh, independent], now=NOW)
    assert conflict["field_provenance"]["opening_hours"]["status"] == "conflicted"
