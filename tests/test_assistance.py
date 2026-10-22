"""Synthetic food assistance records and mocked source/operator transports only."""

import copy
import io
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.assistance import (
    duplicate_candidates,
    freshness,
    parse_feed_resource,
    parse_osm_element,
    records_for_site,
)
from bord_food_api.assistance_crawl import crawl_target, extract_operator_fields, target_plan
from bord_food_api.platform import Platform
from bord_food_api.settings import Settings
from bord_food_api.sources import acquire_source, source_filter_fingerprint


def feed(**extra):
    return {
        "id": 1,
        "name": "Synthetic Pantry",
        "address": "10 Synthetic Street",
        "city": "Example City",
        "state": "IA",
        "zip": "50001",
        "lat": 41.6,
        "lng": -93.6,
        "phone": "515-555-0123",
        "website": "https://pantry.test/find-food",
        "resource_type": "food_pantry",
        "data_source": "fixture",
        "hours_json": '{"monday":"9am-5pm"}',
        "last_verified_date": "2025-01-01",
        **extra,
    }


def feed_records(**extra):
    return list(parse_feed_resource(feed(**extra), state="IA", approved_sources=["fixture"]))


def osm(**tags):
    return {
        "type": "node",
        "id": 1,
        "lat": 41.6,
        "lon": -93.6,
        "tags": {
            "name": "Synthetic Pantry",
            "social_facility": "food_bank",
            "addr:street_address": "10 Synthetic Street",
            "addr:city": "Example City",
            "addr:state": "IA",
            "website": "https://pantry.test/find-food",
            **tags,
        },
    }


def test_directory_separates_facility_service_hours_and_no_inventory_inference():
    rows = feed_records()
    site, service = (r["payload"] for r in rows)
    assert site["phone"] == "+15155550123"
    assert site["schedule"]["raw"] and site["schedule"]["scope"] == "unspecified"
    assert service["schedule"]["raw"] is None and service["schedule"]["scope"] == "service"
    assert site["last_verified_at"] is None and site["source_claimed_verified_at"].startswith(
        "2025"
    )
    assert site["inventory_status"] == service["inventory_status"] == "unknown"
    assert service["appointment_required"] is None and service["public_access"] == "unknown"
    assert site["source_refs"][0]["upstream_source"] == "fixture"
    assert site["source_license"] == "CC-BY-4.0"


def test_feed_rejects_unreviewed_upstream_and_wrong_state():
    with pytest.raises(ValueError, match="rights"):
        list(parse_feed_resource(feed(), state="IA", approved_sources=[]))
    with pytest.raises(ValueError, match="state_mismatch"):
        feed_records(state="IL")
    assert feed_records(resource_type="snap_retailer") == []


def test_osm_is_separate_and_food_bank_tag_does_not_imply_public_pantry():
    rows = list(parse_osm_element(osm(), state="IA"))
    assert rows[0]["kind"] == "osm_assistance_site"
    assert rows[0]["payload"]["service_types"] == ["food_assistance_unspecified"]
    assert rows[0]["payload"]["source_license"] == "ODbL-1.0"
    assert rows[0]["payload"]["public_access"] == "unknown"
    assert (
        list(parse_osm_element(osm(social_facility="soup_kitchen"), state="IA"))[1]["payload"][
            "type"
        ]
        == "meal"
    )
    assert next(iter(parse_osm_element(osm(name=""), state="IA")))["payload"]["name"] is None


@pytest.mark.parametrize("lat,lon", [(True, 1), (91, 1), (1, float("nan")), (None, 1)])
def test_invalid_coordinates_never_become_map_points(lat, lon):
    assert feed_records(lat=lat, lng=lon)[0]["payload"]["coordinates"] is None


def test_pack_publication_stable_ids_relations_rights_and_preserves_groceries(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "grocery",
        "r1",
        [{"kind": "store", "source_key": "1", "payload": {"name": "Synthetic Grocery"}}],
    )
    original = p.current()["packs"]["stores"]
    p.sync("feed_america", "IA", "r1", feed_records(), complete=False)
    site, service = p.records("assistance_site")[0], p.records("assistance_service")[0]
    assert service["site_id"] == site["id"]
    assert p.current()["packs"]["stores"] == original
    p.sync("osm_food_assistance", "IA", "r1", parse_osm_element(osm(), state="IA"), complete=False)
    assert p.current()["packs"]["assistance_osm"] != p.current()["packs"]["assistance"]
    assert p.records("osm_assistance_site")[0]["id"] != site["id"]
    unchanged = p.sync("feed_america", "IA", "r2", feed_records(), complete=False)
    assert unchanged["no_change"] and p.records("assistance_site")[0]["id"] == site["id"]
    p.sync("feed_america", "IA", "empty", [], complete=False, cursor={})
    assert p.records("assistance_site")[0]["operating_status"] == "unknown"
    p.control.restrict_source("feed_america", reason="fixture removal")
    assert not p.records("assistance_site") and p.records("osm_assistance_site")


def test_failed_candidate_keeps_last_good_generation(tmp_path):
    p = Platform(tmp_path)
    p.sync("feed_america", "IA", "r1", feed_records(), complete=False)
    before = p.current()

    def bad():
        yield from feed_records()
        raise ValueError("synthetic partial feed")

    with pytest.raises(ValueError):
        p.sync("feed_america", "IA", "r2", bad(), complete=False)
    assert p.current() == before


class BulkTransport:
    def __init__(self, responder):
        self.responder, self.calls = responder, []

    def fetch(self, url, path, validators=None):
        import hashlib

        self.calls.append(url)
        body = json.dumps(self.responder(url)).encode()
        path.write_bytes(body)
        return {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "url": url}


def source_policy(**extra):
    return {
        "states": ["IA"],
        "max_pages": 2,
        "page_size": 2,
        "rights_reviewed": True,
        "request_delay_seconds": 0,
        "approved_upstream_sources": ["fixture"],
        **extra,
    }


def feed_responder(url):
    query = parse_qs(urlsplit(url).query)
    rows = [feed()] if query["type"] == ["food_pantry"] and query["page"] == ["1"] else []
    return {"success": True, "page": int(query["page"][0]), "resources": rows, "count": len(rows)}


def test_feed_bulk_checks_filters_pagination_and_increments_offline(tmp_path):
    transport = BulkTransport(feed_responder)
    scopes = list(acquire_source("feed_america", source_policy(), transport, tmp_path))
    assert len(transport.calls) == 5
    assert len(list(scopes[0]["records"])) == 2 and scopes[0]["complete"] is False
    assert scopes[0]["cursor"]["state"] == "IA"
    fingerprint = source_filter_fingerprint("feed_america", source_policy())
    assert fingerprint != source_filter_fingerprint("feed_america", source_policy(states=["IL"]))
    assert fingerprint != source_filter_fingerprint(
        "feed_america", source_policy(approved_upstream_sources=["new"])
    )
    with pytest.raises(ValueError, match="rights_review"):
        list(
            acquire_source(
                "feed_america", source_policy(rights_reviewed=False), transport, tmp_path
            )
        )


def test_page_budget_and_ignored_state_filters_cannot_publish(tmp_path):
    def too_many(url):
        q = parse_qs(urlsplit(url).query)
        return {
            "success": True,
            "page": int(q["page"][0]),
            "count": 2,
            "resources": [feed(id=int(q["page"][0]) * 2), feed(id=int(q["page"][0]) * 2 + 1)],
        }

    with pytest.raises(ValueError, match="budget_incomplete"):
        list(
            acquire_source(
                "feed_america", source_policy(max_pages=1), BulkTransport(too_many), tmp_path
            )
        )
    with pytest.raises(ValueError, match="state_mismatch"):
        list(
            acquire_source(
                "feed_america",
                source_policy(),
                BulkTransport(
                    lambda _: {
                        "success": True,
                        "page": 1,
                        "count": 1,
                        "resources": [feed(state="IL")],
                    }
                ),
                tmp_path,
            )
        )


def test_overpass_partial_errors_and_clock_missing_fail_closed(tmp_path):
    for body in [{"elements": [], "remark": "timeout"}, {"elements": []}]:
        with pytest.raises(ValueError):
            list(
                acquire_source(
                    "osm_food_assistance",
                    source_policy(),
                    BulkTransport(lambda _, b=body: b),
                    tmp_path,
                )
            )
    scopes = list(
        acquire_source(
            "osm_food_assistance",
            source_policy(),
            BulkTransport(
                lambda _: {
                    "elements": [osm()],
                    "osm3s": {"timestamp_osm_base": "2026-10-20T12:00:00Z"},
                }
            ),
            tmp_path,
        )
    )
    assert len(list(scopes[0]["records"])) == 2


def test_event_requires_explicit_times_and_stale_schedule_stays_stale():
    site = feed_records()[0]["payload"]
    with pytest.raises(ValueError, match="event_requires"):
        list(
            records_for_site(
                "fixture",
                "1",
                site,
                [],
                [{"source_key": "e1", "starts_at": "Monday", "ends_at": "Tuesday"}],
            )
        )
    result = freshness({"schedule": {"verified_at": "2025-01-01T00:00:00Z"}}, now=time.time())
    assert result["schedule"]["status"] == "stale"
    assert result["needs_confirmation"] is True


def test_api_search_nearby_separate_license_empty_and_pagination(tmp_path):
    settings = Settings(data_dir=tmp_path, auto_download=False)
    p = Platform(tmp_path)
    client = TestClient(create_app(settings))
    assert client.get("/v1/food-assistance/sites").status_code == 503
    p.sync(
        "feed_america",
        "IA",
        "r1",
        [*feed_records(), *feed_records(id=2, name="Second Synthetic Pantry", lat=42.6)],
        complete=False,
    )
    p.sync("osm_food_assistance", "IA", "r1", parse_osm_element(osm(), state="IA"), complete=False)
    answer = client.get("/v1/food-assistance/sites", params={"state": "IA", "limit": 1}).json()
    assert len(answer["data"]) == 1 and answer["meta"]["next_cursor"]
    other = client.get(
        "/v1/food-assistance/sites",
        params={"state": "IA", "limit": 1, "cursor": answer["meta"]["next_cursor"]},
    ).json()
    assert other["data"][0]["id"] != answer["data"][0]["id"]
    nearby = client.get(
        "/v1/food-assistance/sites", params={"lat": 41.6, "lon": -93.6, "radius_km": 5}
    ).json()
    assert len(nearby["data"]) == 1
    assert len(client.get("/v1/food-assistance/sites?dataset=osm").json()["data"]) == 1
    assert client.get("/v1/food-assistance/sites?query=Synthetic").status_code == 200
    assert len(client.get("/v1/food-assistance/sites?postal_code=50001").json()["data"]) == 2
    assert client.get("/v1/food-assistance/sites?lat=41").status_code == 422
    assert client.get("/v1/food-assistance/sites?dataset=merged").status_code == 422
    assert client.get("/v1/capabilities").status_code == 200
    services = client.get("/v1/food-assistance/services?service_type=pantry").json()["data"]
    assert len(services) == 2 and services[0]["site_id"]
    assert client.get("/v1/food-assistance/sites/" + answer["data"][0]["id"]).status_code == 200
    assert client.get("/v1/stores").status_code == 503


def page_html(**extra):
    value = {
        "@type": "NGO",
        "name": "Synthetic Pantry",
        "address": {
            "streetAddress": "10 Synthetic Street",
            "addressLocality": "Example City",
            "addressRegion": "IA",
        },
        "telephone": "515-555-0124",
        "openingHoursSpecification": [{"dayOfWeek": "Monday", "opens": "09:00", "closes": "12:00"}],
        **extra,
    }
    return '<script type="application/ld+json">' + json.dumps(value) + "</script>"


def test_operator_match_must_be_exact_and_cannot_assign_service_hours():
    site = feed_records()[0]["payload"]
    result = extract_operator_fields(page_html(), site, now=time.time(), domain_reviewed=True)
    assert result["status"] == "accepted" and "facility_hours" in result["fields"]
    assert "service_hours" not in result["fields"]
    assert (
        extract_operator_fields(page_html(name="Other Pantry"), site, now=time.time())["status"]
        == "review_required"
    )
    assert (
        extract_operator_fields(
            page_html(address={"streetAddress": "999 Wrong St"}), site, now=time.time()
        )["status"]
        == "review_required"
    )


def test_operator_crawl_shares_robots_frontier_and_retains_conflicts(tmp_path):
    p = Platform(tmp_path)
    p.sync("feed_america", "IA", "r1", feed_records(), complete=False)
    target = target_plan(p, ["IA"])["targets"][0]
    calls = []

    class Transport:
        def __init__(self, policy):
            self.policy = policy

        def get(self, url, headers=None):
            calls.append(url)
            r = io.BytesIO(
                b"User-agent: *\nAllow: /\n"
                if url.endswith("/robots.txt")
                else page_html().encode()
            )
            r.status = 200
            r.headers = {
                "Content-Type": "text/plain" if url.endswith("/robots.txt") else "text/html"
            }
            return r

    now = [time.time()]
    config = {
        "campaign_id": "synthetic-assistance",
        "mode": "bulk_only",
        "global_enabled": True,
        "adapter_enabled": True,
        "source_authorized": True,
        "owner_public_robots_authorized": True,
        "robots_reviewed": True,
        "contact": "ops@bord.org",
        "min_spacing": 45,
        "spacing_jitter_seconds": 45,
        "max_pages_run": 2,
        "reviewed_operator_hosts": ["pantry.test"],
    }
    status = crawl_target(
        p,
        target,
        config,
        transport_factory=Transport,
        clock=lambda: now[0],
        sleep=lambda n: now.__setitem__(0, now[0] + n),
        random_uniform=lambda a, b: 0,
    )
    assert status["state"] == "finished", status
    assert len(calls) == 2 and calls[0].endswith("/robots.txt")
    site = (
        TestClient(create_app(Settings(data_dir=tmp_path, auto_download=False)))
        .get("/v1/food-assistance/sites")
        .json()["data"][0]
    )
    assert site["phone"] == "+15155550124"
    assert site["field_conflicts"] and site["schedule"]["scope"] == "facility"
    assert p.records("assistance_service")[0]["schedule"]["raw"] is None
    assert (
        p.records("assistance_site")[0]["phone"] == "+15155550123"
    )  # serving source assertion unchanged
    assert (tmp_path / "control/crawl-history/history.sqlite").exists()


def test_duplicate_candidates_require_name_and_premises_and_never_merge():
    row = feed_records()[0]["payload"]
    rows = [{**copy.deepcopy(row), "id": str(i)} for i in range(2)]
    assert duplicate_candidates(rows)[0]["action"] == "review_required"
    rows[1]["name"] = "Different Service"
    assert not duplicate_candidates(rows)


def test_reviewed_local_arcgis_export_and_service_events(tmp_path):
    from bord_food_api.assistance_exports import parse_local_row

    profile = {
        "id": "fixture-pantries",
        "state": "IA",
        "license": "CC0-1.0",
        "attribution": "Synthetic municipal source",
        "reuse_reviewed": True,
        "service_type": "mobile_pantry",
        "format": "arcgis",
        "url": "https://municipal.test/Food/0",
        "fields": {
            "id": "OBJECTID",
            "name": "NAME",
            "street": "STREET",
            "city": "CITY",
            "phone": "PHONE",
            "service_hours": "DISTRIBUTION",
            "event_id": "EVENT",
            "starts_at": "START",
            "ends_at": "END",
        },
    }
    raw = {
        "OBJECTID": 1,
        "NAME": "Synthetic Mobile Pantry",
        "STREET": "10 Synthetic Street",
        "CITY": "Example City",
        "PHONE": "515-555-0123",
        "DISTRIBUTION": "First Monday only",
        "EVENT": "e1",
        "START": "2026-10-25T09:00:00-05:00",
        "END": "2026-10-25T11:00:00-05:00",
    }
    records = list(parse_local_row(raw, profile))
    assert [r["kind"] for r in records] == [
        "assistance_site",
        "assistance_service",
        "assistance_event",
    ]
    p = Platform(tmp_path)
    p.sync("community_food_assistance", "fixture-pantries", "r1", records, complete=False)
    assert p.records("assistance_service")[0]["schedule"]["raw"] == "First Monday only"
    assert p.records("assistance_site")[0]["schedule"]["raw"] is None
    assert (
        p.records("assistance_event")[0]["service_id"] == p.records("assistance_service")[0]["id"]
    )
    policy = {"profiles": [profile]}

    def responder(_):
        return {
            "features": [{"attributes": raw, "geometry": {"x": -93.6, "y": 41.6}}],
            "spatialReference": {"wkid": 4326},
        }

    scopes = list(
        acquire_source(
            "community_food_assistance", policy, BulkTransport(responder), tmp_path / "download"
        )
    )
    assert len(list(scopes[0]["records"])) == 3
    with pytest.raises(ValueError, match="wgs84"):
        list(
            acquire_source(
                "community_food_assistance",
                policy,
                BulkTransport(lambda _: {**responder(_), "spatialReference": {"wkid": 3857}}),
                tmp_path / "bad",
            )
        )
    with pytest.raises(ValueError, match="offset_times"):
        list(parse_local_row({**raw, "START": "2026-10-25", "END": "2026-10-26"}, profile))


def test_hsds_services_join_only_their_locations(tmp_path):
    from bord_food_api.assistance_exports import parse_hsds_bundle

    profile = {
        "id": "synthetic-hsds",
        "state": "IA",
        "license": "CC0-1.0",
        "attribution": "Synthetic authorized export",
        "url": "https://municipal.test/export",
        "reuse_reviewed": True,
        "service_type": "pantry",
    }
    bundle = {
        "locations": [
            {"id": "l1", "name": "Synthetic Pantry"},
            {"id": "l2", "name": "Other place"},
        ],
        "services": [
            {"id": "s1", "type": "pantry", "eligibility": "Resident of example county"},
            {"id": "s2", "type": "meal"},
        ],
        "service_at_location": [{"id": "link1", "service_id": "s1", "location_id": "l1"}],
        "addresses": [
            {
                "id": "a1",
                "location_id": "l1",
                "address_1": "10 Synthetic Street",
                "city": "Example City",
                "state_province": "IA",
            }
        ],
    }
    rows = list(parse_hsds_bundle(bundle, profile))
    assert len(rows) == 2 and rows[1]["payload"]["type"] == "pantry"
    assert rows[1]["payload"]["eligibility"] == "Resident of example county"
    with pytest.raises(ValueError, match="dangling"):
        list(
            parse_hsds_bundle(
                {**bundle, "service_at_location": [{"service_id": "unknown", "location_id": "l1"}]},
                profile,
            )
        )
    with pytest.raises(ValueError, match="rights"):
        list(parse_hsds_bundle(bundle, {**profile, "reuse_reviewed": False}))


def test_post_supermarket_dependency_never_fetches_early(tmp_path):
    from bord_food_api.assistance_campaign import run_pass, supermarket_gate
    from bord_food_api.platform import atomic_json

    settings = Settings(data_dir=tmp_path, auto_download=False)
    config = {
        "states": ["IA"],
        "after_campaigns": ["synthetic-supermarkets"],
        "campaign_id": "synthetic-assistance",
    }
    called = []
    result = run_pass(settings, config, acquisition=lambda *_: called.append(True))
    assert result["state"] == "waiting_for_supermarkets" and not called
    path = tmp_path / "crawl-campaigns/synthetic-supermarkets/status.json"
    atomic_json(path, {"state": "running", "active": "IA"})
    assert not supermarket_gate(tmp_path, ["synthetic-supermarkets"])["ready"]
    atomic_json(
        path,
        {
            "state": "finished_with_holds",
            "active": None,
            "active_run": None,
            "states": {"IA": {"targets": 30, "phases": [{"state": "finished"}]}},
        },
    )
    assert not supermarket_gate(tmp_path, ["synthetic-supermarkets"])["ready"]
    atomic_json(
        path,
        {
            "state": "finished_with_holds",
            "active": None,
            "active_run": None,
            "states": {
                "IA": {
                    "targets": 30,
                    "phases": [{"state": "finished"}, {"state": "finished_with_holds"}],
                }
            },
        },
    )
    assert supermarket_gate(tmp_path, ["synthetic-supermarkets"])["ready"]
    assert not supermarket_gate(tmp_path, [])["ready"]


def test_post_pass_runs_only_due_assistance_source_and_retains_provenance(tmp_path, monkeypatch):
    from bord_food_api.assistance_campaign import run_pass
    from bord_food_api.platform import atomic_json
    from bord_food_api.settings import SOURCE_DEFAULTS

    config_path = tmp_path / "policy.json"
    config_path.write_text(
        json.dumps(
            {
                "network": {"mode": "bulk_only"},
                "budgets": {"free_space_reserve_bytes": 0},
                "sources": {
                    name: {"enabled": name == "osm_food_assistance"} for name in SOURCE_DEFAULTS
                },
            }
        )
    )
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(config_path))
    settings = Settings(data_dir=tmp_path / "data", auto_download=False)
    atomic_json(
        settings.data_dir / "crawl-campaigns/synthetic-supermarkets/status.json",
        {"state": "finished", "active": None, "active_run": None},
    )
    calls = []

    def acquired(source, *_):
        calls.append(source)
        yield {
            "partition": "IA",
            "release": "synthetic-r1",
            "complete": False,
            "cursor": {"state": "IA"},
            "records": parse_osm_element(osm(), state="IA"),
        }

    config = {
        "states": ["IA"],
        "after_campaigns": ["synthetic-supermarkets"],
        "campaign_id": "synthetic-assistance",
        "operator_crawl_enabled": False,
    }
    result = run_pass(settings, config, acquisition=acquired)
    assert result["source_jobs"][0]["state"] == "succeeded"
    assert calls == ["osm_food_assistance"]
    run_pass(settings, config, acquisition=acquired)
    assert calls == ["osm_food_assistance"]  # weekly interval coalesces repeated checks
    assert (
        Platform(settings.data_dir).records("osm_assistance_site")[0]["source_license"]
        == "ODbL-1.0"
    )


def test_source_relocation_and_contact_conflicts_are_retained_for_review(tmp_path):
    p = Platform(tmp_path)
    p.sync("feed_america", "IA", "r1", feed_records(), complete=False)
    identity = p.records("assistance_site")[0]["id"]
    p.sync("feed_america", "IA", "r2", feed_records(phone="515-555-0124"), complete=False)
    assert p.records("assistance_site")[0]["field_conflicts"]
    p.sync(
        "feed_america",
        "IA",
        "r3",
        feed_records(address="999 Other Street", phone="515-555-0125"),
        complete=False,
    )
    row = p.records("assistance_site")[0]
    assert row["id"] == identity and row["address"]["street"] == "10 Synthetic Street"
    assert row["identity_review"]["candidate"]["address"]["street"] == "999 Other Street"
    assert row["phone"] == "+15155550124"


def test_jev_triage_is_mocked_and_cannot_override_identity():
    from bord_food_api.assistance_review import review_page

    class Judge:
        def ask(self, target, stage, state, questions):
            assert stage == "food_assistance_page_review"
            assert "untrusted" in questions["identity"]["instructions"]
            assert state["deterministic_match"] is False
            return {
                "identity": {"choice": "consistent", "confidence": 0.99},
                "service": {"choice": "pantry", "confidence": 0.9},
            }

    target = {"site_id": "synthetic", "url": "https://pantry.test/find-food"}
    result = review_page(Judge(), "Synthetic source text", target, {"status": "review_required"})
    assert result["can_override_evidence"] is False
    assert result["role"] == "review_only"


def test_paused_post_worker_stays_idle_without_requests(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"network": {"mode": "offline"}}))
    config = tmp_path / "campaign.json"
    config.write_text(
        json.dumps(
            {
                "campaign_id": "paused-food-assistance",
                "states": ["IA"],
                "after_campaigns": ["synthetic-supermarkets"],
                "policy_path": str(policy),
            }
        )
    )
    root = tmp_path / "data"
    directory = root / "crawl-campaigns/paused-food-assistance"
    directory.mkdir(parents=True)
    (directory / "STOP").touch()
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(policy))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run-food-assistance.py",
            str(config),
            "--data-dir",
            str(root),
            "--run",
            "--resume",
            "--once",
        ],
    )
    spec = importlib.util.spec_from_file_location(
        "paused_assistance", Path(__file__).parents[1] / "scripts/run-food-assistance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    assert json.loads((directory / "status.json").read_text())["state"] == "paused_operator"
    assert not (root / "downloads").exists()
