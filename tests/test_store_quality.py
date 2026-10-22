import copy

import pytest

from bord_food_api.chain_profiles import profile_for
from bord_food_api.platform import Platform
from bord_food_api.store_enrichment import publish_enrichment
from bord_food_api.store_quality import (
    clean_store,
    coordinate_evidence,
    duplicate_candidates,
    location_key,
)


def store(**values):
    return {
        "id": "one",
        "name": "Imaginary Grocery",
        "country": "US",
        "address": {
            "street": "123 Main St",
            "city": "Ames",
            "region": "IA",
            "postal_code": "50010",
        },
        **values,
    }


def test_profiles_and_full_addresses_apply_outside_iowa_without_inventing_components():
    r = store(
        name="Dollar Fresh Hy-Vee",
        address={"full": "123 Main Street, Omaha, NE 68102", "region": "NE", "city": None},
    )
    result = clean_store(r)
    assert result["address"]["city"] == "Omaha" and result["address"]["postal_code"] == "68102"
    assert result["quality"]["profile_id"] == "hy_vee"
    assert r["address"]["city"] is None
    assert clean_store(result) == result
    assert clean_store(store(address={"full": "unparseable"}))["address"] == {"full": "unparseable"}
    assert profile_for(store(name="ALDI", website="https://www.aldi.us/"))["id"] == "aldi"


def test_scope_is_not_closure_and_chain_phones_are_not_branch_contacts():
    r = clean_store(store(name="Hy-Vee Fast & Fresh"))
    assert (
        r["directory_scope"]["status"] == "excluded"
        and r["directory_scope"]["physical_closure"] is False
    )
    assert "permanently_closed" not in r
    r = clean_store(store(name="Aldi", phone="855-955-2534"))
    assert r["contact_channels"]["phone"]["scope"] == "chain"
    r = clean_store(store(name="Hy-Vee", phone="Main (641) 784-6981 - Pharmacy (641) 784-6322"))
    assert r["phone"] == "+16417846981"


def test_identity_city_spacing_postal_box_and_shared_building_do_not_guess_merges():
    a = store(
        name="Fareway",
        address={"street": "615 Westwood Drive, PO 96", "city": "LeClaire", "region": "IA"},
        phone="515-555-1234",
    )
    b = store(
        id="two",
        name="Fareway Stores Inc. 993",
        address={"street": "615 Westwood Dr", "city": "Le Claire", "region": "IA"},
        phone="515-555-1234",
    )
    assert location_key(a) == location_key(b)
    assert len(duplicate_candidates([a, b])) == 1
    assert duplicate_candidates([a, {**b, "name": "Target"}]) == []
    # A chain phone without matching address cannot link branches.
    assert (
        duplicate_candidates(
            [
                store(name="Aldi", phone="8559552534"),
                store(
                    id="two",
                    name="Aldi",
                    phone="8559552534",
                    address={"street": "999 Other Rd", "city": "Ames", "region": "IA"},
                ),
            ]
        )
        == []
    )


def test_coordinates_require_exact_address_brand_clock_and_consistent_points():
    a = store()
    c = {
        "source": "fixture",
        "source_key": "point",
        "payload": {**a, "latitude": 42.0, "longitude": -93.6, "source_observed_at": 100},
    }
    point, reason = coordinate_evidence(a, [c])
    assert point["verified_at"] is None and reason is None
    bad = copy.deepcopy(c)
    bad["payload"]["address"]["street"] = "999 Main St"
    assert coordinate_evidence(a, [bad])[0] is None
    bad = copy.deepcopy(c)
    bad["payload"]["latitude"] = 43
    assert coordinate_evidence(a, [c, bad])[1] == "coordinate_source_conflict"
    bad = copy.deepcopy(c)
    bad["payload"]["source_observed_at"] = None
    assert coordinate_evidence(a, [bad])[0] is None


def test_quality_publish_rebuilds_spatial_and_hides_scope_but_retains_direct_lookup(tmp_path):
    p = Platform(tmp_path)
    p.sync("fixture", "IA", "r1", [{"kind": "store", "source_key": "one", "payload": store()}])
    row = p.records("store")[0]
    before = p.current()
    updated = clean_store(row)
    updated.update(latitude=42.0, longitude=-93.6)
    publish_enrichment(
        p, [updated], base_generation=before["generation"], release="quality", now=100
    )
    assert next(iter(p.iter_records("store", lat=42, lon=-93.6, radius_km=1)))["id"] == row["id"]
    updated = clean_store({**updated, "name": "Hy-Vee Fast & Fresh"})
    publish_enrichment(
        p, [updated], base_generation=p.current()["generation"], release="scope", now=101
    )
    assert p.records("store") == list(p.iter_records("store")) == []
    assert p.get("store", row["id"])["directory_scope"]["status"] == "excluded"
    assert p.records("store", before["generation"])[0]["id"] == row["id"]
    with pytest.raises(ValueError, match="base_generation"):
        publish_enrichment(
            p, [updated], base_generation=before["generation"], release="stale", now=102
        )


def test_reviewed_aliases_keep_old_ids_and_source_assertions_then_replay_is_safe(tmp_path):
    from bord_food_api.store_quality import prepare, publish

    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": str(i),
                "payload": store(id=None, name="Fareway", phone="5155551234"),
            }
            for i in range(2)
        ],
    )
    before = p.current()
    plan = prepare(p.records("store"), state="IA")
    plan["base_generation"] = before["generation"]
    pair = plan["duplicates"][0]
    review = {
        "from": pair["a"],
        "to": pair["b"],
        "binding": pair["binding"],
        "reviewer": "operator",
        "reason": "synthetic exact-address and phone confirmation",
    }
    result = publish(p, plan, [review], now=100)
    assert result["changed"] >= 1
    assert len(p.records("store")) == 1
    assert p.get("store", pair["a"])["id"] == pair["b"]
    assert p.get("store", pair["a"])["redirected_from"] == pair["a"]
    assert p.get("store", pair["b"])["source_alternatives"]
    assert len(p.records("store", before["generation"])) == 2
    # Raw source rows still exist, so a subsequent refresh cannot recreate a duplicate.
    p.sync(
        "fixture",
        "IA",
        "r2",
        [
            {
                "kind": "store",
                "source_key": str(i),
                "payload": store(id=None, name="Fareway", phone="5155551234"),
            }
            for i in range(2)
        ],
    )
    assert len(p.records("store")) == 1
