import pytest

from bord_food_api.crawl_evidence import collect_evidence
from bord_food_api.site_discovery import contact_followups, directory_candidates
from bord_food_api.store_enrichment import assertion, reconcile_fields, reparse_assertions
from bord_food_api.store_hours import structured_hours

NOW = 1792530000
ROW = {
    "id": "sto_fixture",
    "name": "Imaginary Cooperative",
    "country": "US",
    "address": {
        "street": "10 West Main St",
        "city": "Omaha",
        "region": "NE",
        "postal_code": "68102",
    },
}


def e(raw, source="openstreetmap", field="opening_hours"):
    return assertion(
        ROW["id"],
        field,
        raw,
        source_id=source,
        record_id="one",
        source_url="https://fixture.test/one",
        checked_at=NOW,
        lineage=source,
        branch_match="exact_address",
    )


def test_fuller_source_does_not_claim_partial_week_independent_verification():
    partial = e("Mo-Sa 08:00-21:00")
    full = e("Mo-Sa 08:00-21:00; Su off", "all_the_places")
    r = reconcile_fields(ROW, [partial, full], now=NOW)
    assert len(r["opening_hours"]) == 7
    p = r["field_provenance"]["opening_hours"]
    assert p["status"] == "source_reported" and p["verified_at"] is None
    assert p["supporting_ids"] == [full["id"]] and p["partial_supporting_ids"] == [partial["id"]]
    assert r["field_conflicts"][0]["resolution"] == "compatible_partial_schedule"
    assert reconcile_fields(r, [], now=NOW) == r
    conflicting = e("Mo-Sa 09:00-21:00")
    assert "opening_hours" not in reconcile_fields(ROW, [conflicting, full], now=NOW)


def test_schema_meridiem_and_osm_daily_selector_keep_source_clocks():
    assert (
        structured_hours({"dayOfWeek": "Monday", "opens": "12am", "closes": "12:30PM"})[0]["closes"]
        == "12:30"
    )
    with pytest.raises(ValueError):
        structured_hours({"dayOfWeek": "Monday", "opens": "9", "closes": "20:00"})
    daily = e("08:00-20:00")
    assert len(daily["value"]) == 7
    assert e("08:00-20:00", "retailer_page")["validation"] == "invalid_or_unsupported"
    old = e([{"dayOfWeek": "Monday", "opens": "9am", "closes": "8pm"}], "all_the_places")
    old.update(id="retained-old", validation="invalid_or_unsupported", value=None)
    replay = reparse_assertions({**ROW, "field_evidence": [old]})[0]
    assert replay["checked_at"] == NOW and replay["reparsed_from"] == "retained-old"
    stale = reconcile_fields(ROW, [{**replay, "checked_at": NOW - 100 * 86400}], now=NOW)
    assert "opening_hours" not in stale


def test_chain_service_phone_is_retained_without_becoming_branch_verification():
    row = {**ROW, "name": "ALDI"}
    result = reconcile_fields(
        row,
        [e("855-955-2534", field="phone"), e("8559552534", "retailer_page", field="phone")],
        now=NOW,
    )
    assert "phone" not in result
    assert {r["scope"] for r in result["contact_channels"]["phones"]} == {"chain"}


def test_nested_reviewed_branch_panel_keeps_phone_but_does_not_invent_weekdays():
    target = {
        **ROW,
        "store_id": ROW["id"],
        "source_address": ROW["address"],
        "expected_branch": ROW["name"],
        "url": "https://fixture.test/contact",
        "site_identity_review": {
            "store_id": ROW["id"],
            "source_address": ROW["address"],
            "evidence_sha256": "a" * 64,
            "scope": "multi_branch_contact_panel",
        },
    }
    html = "<footer><div><div>Other Branch 30 Main St Omaha NE 68102</div>4025559999</div><div><div>10 West Main St Omaha NE 68102</div><div>8am-9pm</div><div>(402) 555-1234</div></div></footer>"
    evidence = collect_evidence(html, target, retrieved_at=NOW)
    valid = [a for a in evidence["field_assertions"] if a["validation"] == "valid"]
    assert {a["value"] for a in valid if a["field"] == "phone"} == {"+14025551234"}
    assert not any(a["field"] == "opening_hours" for a in valid)


def test_discovery_is_address_bound_cross_state_and_does_not_fetch_or_promote():
    html = '<li><h3>Imaginary Cooperative</h3>10 W Main Street Omaha NE 68102 <a href="https://fixture.test/">www.fixture.test</a><a href="https://facebook.com/fixture">Facebook</a></li><footer>10 W Main Street Omaha NE 68102 <a href="https://bad.test">Corporate</a></footer>'
    rows = directory_candidates(
        html,
        "https://www.ncg.coop/find-co-op",
        [ROW],
        state="NE",
        source_id="ncg",
        retrieved_at=NOW,
    )
    assert len(rows) == 1 and rows[0]["url"] == "https://fixture.test"
    assert (
        rows[0]["single_store_site"] is False and rows[0]["status"] == "candidate_requires_review"
    )
    assert (
        directory_candidates(
            html,
            "https://www.ncg.coop/find-co-op",
            [ROW],
            state="IA",
            source_id="ncg",
            retrieved_at=NOW,
        )
        == []
    )
    assert (
        directory_candidates(
            html.replace("10 W Main", "11 W Main"),
            "https://www.ncg.coop/find-co-op",
            [ROW],
            state="NE",
            source_id="ncg",
            retrieved_at=NOW,
        )
        == []
    )
    target = {
        "store_id": ROW["id"],
        "source_address": ROW["address"],
        "url": "https://fixture.test/",
    }
    links = contact_followups(
        '<a href="/locations/">Locations</a><a href="https://other.test/contact">Contact</a><a href="/product">Product</a>',
        target,
    )
    assert [r["url"] for r in links] == ["https://fixture.test/locations"]


def test_reviewed_single_premise_footer_and_daily_suffix_do_not_enable_corporate_footer():
    target = {
        "store_id": ROW["id"],
        "name": ROW["name"],
        "source_address": ROW["address"],
        "url": "https://fixture.test/",
        "single_store_site": True,
        "expected_branch": ROW["name"],
    }
    html = "<footer><h3>Imaginary Cooperative</h3><p>10 West Main St Omaha NE 68102</p><p>(402)-555-1234</p><p>Open 9 am – 8 pm daily</p></footer>"
    assert (
        collect_evidence(html, target, retrieved_at=NOW)["branch_match"] == "ambiguous_or_missing"
    )
    target["site_identity_review"] = {
        "store_id": ROW["id"],
        "source_address": ROW["address"],
        "evidence_sha256": "a" * 64,
    }
    result = collect_evidence(html, target, retrieved_at=NOW)
    valid = {
        r["field"]: r["value"]
        for r in result["field_assertions"]
        if r["validation"] == "valid" and r["branch_match"] == "exact_address"
    }
    assert valid["phone"] == "+14025551234" and len(valid["opening_hours"]) == 7
    assert (
        collect_evidence(html.replace("10 West", "11 West"), target, retrieved_at=NOW)[
            "branch_match"
        ]
        == "ambiguous_or_missing"
    )


def test_unconfirmed_aldi_routing_numbers_cannot_fill_a_missing_branch_phone():
    result = reconcile_fields({**ROW, "name": "ALDI"}, [e("833-472-7047", field="phone")], now=NOW)
    assert "phone" not in result
    assert result["contact_channels"]["phones"][0]["scope"] == "unresolved_contact_scope"


def test_http_directory_leads_are_retained_without_silently_upgrading_them():
    html = '<li>Imaginary Cooperative 10 West Main St Omaha NE 68102 <a href="http://fixture.test">Website</a></li>'
    candidate = directory_candidates(
        html,
        "https://www.ncg.coop/find-co-op",
        [ROW],
        state="NE",
        source_id="ncg",
        retrieved_at=NOW,
    )[0]
    assert (
        candidate["url"] == "http://fixture.test"
        and candidate["status"] == "candidate_requires_review"
    )


def test_multi_branch_footer_panels_require_exact_address_and_do_not_copy_office_contact():
    target = {
        "store_id": ROW["id"],
        "name": ROW["name"],
        "expected_branch": ROW["name"],
        "source_address": ROW["address"],
        "url": "https://fixture.test/contact/",
        "site_identity_review": {
            "store_id": ROW["id"],
            "source_address": ROW["address"],
            "scope": "multi_branch_contact_panel",
            "evidence_sha256": "a" * 64,
        },
    }
    html = "<main>Administrative office 30 Main St Omaha NE 68102 Phone 402-555-9999</main><footer><div><p>10 West Main St Omaha NE 68102</p><p>402-555-1234</p><p>8am-9pm</p></div><div>20 Other St Omaha NE 68102 Phone 402-555-8888</div></footer>"
    r = collect_evidence(html, target, retrieved_at=NOW)
    valid = {
        e["field"]: e["value"]
        for e in r["field_assertions"]
        if e["validation"] == "valid" and e["branch_match"] == "exact_address"
    }
    assert valid["phone"] == "+14025551234" and "opening_hours" not in valid


def test_visible_state_names_are_supported_outside_iowa_without_postcode_guessing():
    target = {
        "store_id": ROW["id"],
        "name": ROW["name"],
        "expected_branch": ROW["name"],
        "source_address": {**ROW["address"], "postal_code": None},
        "url": "https://fixture.test/one",
    }
    html = '<main>Imaginary Cooperative 10 West Main Street Omaha Nebraska <a href="tel:4025551234">Store phone</a> Monday-Sunday 9am-8pm</main>'
    assert collect_evidence(html, target, retrieved_at=NOW)["branch_match"] == "exact_address"
    assert (
        collect_evidence(html.replace("Nebraska", "Kansas"), target, retrieved_at=NOW)[
            "branch_match"
        ]
        == "ambiguous_or_missing"
    )
