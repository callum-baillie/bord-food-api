import copy

import pytest

from bord_food_api.refresh import DAY, NORMALIZER_VERSION, field_groups, plan_store_refresh

NOW = 1_800_000_000


def store(**changes):
    return {
        "name": "Synthetic Grocery",
        "chain_key": "synthetic",
        "address": "1 Example Rd",
        "latitude": 41.1,
        "longitude": -91.1,
        "phone": "+1 (555) 010-0001",
        "website": "https://example.test/store",
        "hours": "Mo-Su 08:00-20:00",
        "services": ["pickup", "delivery"],
        **changes,
    }


def observed(record, at=NOW, **kwargs):
    report = plan_store_refresh(None, record, at, **kwargs)
    return {
        **record,
        "field_refresh": {
            "normalizer_version": report["normalizer_version"],
            "groups": report["groups"],
        },
    }


def test_normalized_hashes_whitespace_unicode_phone_sets_and_tracking():
    original = store(name="Café Grocery", website="https://EXAMPLE.test/store?utm_source=x&a=1")
    equivalent = store(
        name="  Cafe\u0301  Grocery ",
        phone="tel:+1-555-010-0001",
        services=["DELIVERY", "pickup", "pickup"],
        website="https://example.test/store?a=1&utm_source=y#irrelevant",
        fetched_at="2099-01-01",
        source_record={"anything": "ignored"},
    )
    assert field_groups(original) == field_groups(equivalent)
    assert field_groups(store(latitude=0))["location"]["status"] == "known"
    assert field_groups({})["hours"]["status"] == "unknown"
    assert field_groups({"hours": None})["hours"] == field_groups({})["hours"]


def test_new_bulk_record_requires_no_detail_and_never_queues_requests():
    report = plan_store_refresh(None, store(), NOW, crawl_authorized=True)
    assert report["detail_groups"] == []
    assert report["detail_candidates"] == []
    assert report["requests"] == []
    assert report["normalizer_version"] == NORMALIZER_VERSION
    assert report["groups"]["hours"]["last_detail_checked_at"] is None
    assert report["due_at"]["location"] == NOW + 180 * DAY
    assert report["due_at"]["maps"] is None


def test_changed_hours_only_avoids_location_detail_and_disabled_crawling():
    previous = observed(store())
    incoming = store(hours="Mo-Su 07:00-21:00")
    frozen = copy.deepcopy(previous)
    allowed = plan_store_refresh(previous, incoming, NOW + DAY, crawl_authorized=True)
    blocked = plan_store_refresh(previous, incoming, NOW + DAY, crawl_authorized=False)
    assert allowed["changed_groups"] == ["hours"]
    assert allowed["detail_groups"] == ["hours"]
    assert allowed["detail_reasons"] == {"hours": "changed"}
    assert blocked["detail_groups"] == []
    assert blocked["requests"] == []
    assert previous == frozen


def test_unknown_optional_fields_require_explicit_enrichment_policy():
    missing = store(phone=None, website=None, hours=None)
    assert plan_store_refresh(None, missing, NOW, crawl_authorized=True)["detail_groups"] == []
    report = plan_store_refresh(
        None,
        missing,
        NOW,
        required_groups=("contact", "hours"),
        maps_requested=True,
        crawl_authorized=True,
    )
    assert report["detail_groups"] == ["contact", "hours", "maps"]
    # A known website does not satisfy an explicit missing phone requirement.
    report = plan_store_refresh(
        None, store(phone=None), NOW, required_fields=("phone",), crawl_authorized=True
    )
    assert report["detail_groups"] == ["contact"]


def test_existing_fields_are_audited_independently_without_resetting_on_bulk_check():
    record = store()
    previous = observed(record)
    later = plan_store_refresh(
        previous, record, NOW + 15 * DAY, watched=True, crawl_authorized=True
    )
    assert later["detail_groups"] == ["hours"]
    assert later["groups"]["hours"]["first_seen_at"] == NOW
    assert later["groups"]["hours"]["last_detail_checked_at"] is None
    unwatched = plan_store_refresh(previous, record, NOW + 15 * DAY, crawl_authorized=True)
    assert unwatched["detail_groups"] == []
    old = plan_store_refresh(previous, record, NOW + 181 * DAY, crawl_authorized=True)
    assert set(old["detail_groups"]) == {
        "identity",
        "name",
        "location",
        "contact",
        "hours",
        "services",
    }
    assert old["detail_reasons"]["location"] == "audit_due"
    assert old["due_at"]["contact"] == NOW + 30 * DAY


@pytest.mark.parametrize("attempts,days", [(1, 30), (2, 90), (3, 180), (12, 180)])
def test_map_not_found_backoff_has_no_closure_inference(attempts, days):
    record = store(map_status="not_found")
    record["field_refresh"] = {
        "groups": {
            "maps": {
                "last_detail_checked_at": NOW,
                "negative_attempts": attempts,
                "status": "not_found",
            }
        }
    }
    report = plan_store_refresh(None, record, NOW + DAY, maps_requested=True, crawl_authorized=True)
    assert report["detail_groups"] == []
    assert report["due_at"]["maps"] == NOW + days * DAY
    saved = {**record, "field_refresh": {"groups": report["groups"]}}
    report = plan_store_refresh(
        saved, saved, NOW + (days + 1) * DAY, maps_requested=True, crawl_authorized=True
    )
    assert "maps" in report["detail_groups"]
    assert "closure" not in report


def test_real_detail_check_advances_its_group_only_and_rejects_unbounded_evidence():
    previous = observed(store())
    incoming = store(
        field_refresh={"groups": {"hours": {"last_detail_checked_at": NOW + 15 * DAY}}}
    )
    result = plan_store_refresh(
        previous, incoming, NOW + 16 * DAY, watched=True, crawl_authorized=True
    )
    assert result["due_at"]["hours"] == NOW + 29 * DAY
    assert result["due_at"]["location"] == NOW + 180 * DAY
    with pytest.raises(ValueError, match="Nonfinite"):
        field_groups(store(latitude=float("nan")))
    with pytest.raises(ValueError, match="Unknown required"):
        plan_store_refresh(None, store(), NOW, required_groups=("stock",))
    with pytest.raises(ValueError, match="string limit"):
        field_groups(store(name="x" * 65537))


def test_negative_map_evidence_persists_without_affecting_missing_contact():
    original = store(map_status="not_found", phone=None, website=None)
    first = plan_store_refresh(
        None,
        original,
        NOW,
        maps_requested=True,
        required_groups=("contact",),
        crawl_authorized=True,
    )
    assert first["detail_groups"] == ["contact"]
    previous = {**original, "field_refresh": {"groups": first["groups"]}}
    next_record = store(phone=None, website=None)
    later = plan_store_refresh(
        previous, next_record, NOW + 10 * DAY, maps_requested=True, crawl_authorized=True
    )
    assert "maps" not in later["detail_groups"]
    assert later["due_at"]["maps"] == NOW + 30 * DAY
    future = store(field_refresh={"groups": {"hours": {"last_detail_checked_at": NOW + 100}}})
    with pytest.raises(ValueError, match="future"):
        plan_store_refresh(None, future, NOW)
