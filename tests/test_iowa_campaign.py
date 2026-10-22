import importlib.util
import json
from pathlib import Path

import pytest

from bord_food_api.platform import Platform
from bord_food_api.transport import TransportError

spec = importlib.util.spec_from_file_location(
    "iowa_campaign", Path(__file__).parents[1] / "scripts/run-iowa-crawl.py"
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


@pytest.fixture
def configured(tmp_path):
    p = Platform(tmp_path)
    rows = [
        {
            "kind": "store",
            "source_key": str(i),
            "payload": {
                "name": f"Synthetic {i}",
                "spider": "synthetic_grocer",
                "chain_key": f"chain:{i}",
                "chain_name": f"Synthetic {i}",
                "country": "US",
                "address": {
                    "street_address": "1 Fixture Street",
                    "locality": "Ames",
                    "region": "IA",
                    "postal_code": "50010",
                },
                "website": f"https://retailer{i}.test/stores/one/",
            },
        }
        for i in range(2)
    ]
    p.sync("all_the_places", "synthetic_grocer", "fixture", rows)
    stores = p.records("store")
    targets = []
    scopes = {}
    for store in stores:
        host = store["website"].split("/")[2]
        targets.append(
            {
                "store_id": store["id"],
                "name": store["name"],
                "chain_id": store["chain_id"],
                "spider": store["spider"],
                "source_website": store["website"],
                "url": store["website"],
                "expected_branch": store["name"],
            }
        )
        scopes[host] = {
            "state": "approved",
            "review_evidence": "Synthetic operator policy review",
            "crawl": {
                "global_enabled": True,
                "adapter_enabled": True,
                "source_authorized": True,
                "terms_reviewed": True,
                "robots_reviewed": True,
                "contact": "operator@fixture.invalid",
                "allowed_host": host,
                "scope_prefix": "/stores/",
                "min_spacing": 60,
                "max_pages_run": 2,
                "max_pages_day": 50,
                "max_bytes": 524288,
            },
        }
    return p, {
        "campaign_id": "synthetic-iowa",
        "targets": targets,
        "scopes": scopes,
        "decisions": {"max_calls": 4, "budget_nanousd": 40000000, "key_file": "unused"},
    }


class Judge:
    def __init__(self, *args):
        pass

    def before(self, target):
        pass


@pytest.mark.parametrize("change", ["region", "url", "review"])
def test_scope_validation_prevents_paid_calls_or_source_unpause(configured, change):
    p, c = configured
    target = c["targets"][0]
    if change == "region":
        target["store_id"] = "non-iowa-or-unknown"
    elif change == "url":
        target["url"] = "https://invented.test/stores/one/"
    else:
        c["scopes"][target["url"].split("/")[2]]["state"] = "blocked_terms"
    p.control.set_source(campaign.SOURCE, False)

    def unavailable(*args):
        raise AssertionError("paid transport must not be constructed")

    with pytest.raises(ValueError):
        campaign.run(c, p.root, judge_factory=unavailable)
    assert not p.control.enabled(campaign.SOURCE)


def test_blocked_host_does_not_retry_or_block_other_reviewed_host(configured):
    p, c = configured
    calls = []

    def discover(platform, job, config, **kwargs):
        calls.append(config["allowed_host"])
        platform.control.check_fence(job)
        assert config["min_spacing"] >= 60
        if len(calls) == 1:
            raise TransportError(403)
        return {"map_records": 0}

    result = campaign.run(c, p.root, judge_factory=Judge, discover=discover)
    assert result["state"] == "finished" and len(calls) == 2
    assert [x["state"] for x in result["completed"]] == ["host_blocked", "published"]
    assert len(result["blocked_hosts"]) == 1
    assert not p.control.enabled(campaign.SOURCE)
    with p.control.connect() as db:
        assert {
            x[0] for x in db.execute("SELECT state FROM jobs WHERE source=?", (campaign.SOURCE,))
        } == {"failed", "succeeded"}


def test_publication_keeps_pending_media_rights_and_source_provenance(configured):
    p, c = configured

    def discover(platform, job, config, **kwargs):
        target = config["approved_targets"][0]
        platform.sync(
            campaign.SOURCE,
            config["allowed_host"],
            "synthetic",
            [
                {
                    "kind": "map",
                    "source_key": target["url"],
                    "payload": {
                        "store_id": target["store_id"],
                        "branch_page": target["url"],
                        "rights_status": "pending",
                        "display_permitted": False,
                        "storage_permitted": False,
                        "assets": {},
                    },
                }
            ],
            complete=False,
            fence=job,
        )
        return {"map_records": 1}

    result = campaign.run(c, p.root, judge_factory=Judge, discover=discover)
    assert all(x["state"] == "published" for x in result["completed"])
    assert len(p.records("map")) == 2
    assert all(
        x["rights_status"] == "pending" and not x["display_permitted"] and not x["assets"]
        for x in p.records("map")
    )
    assert all(x["source_refs"][0]["source_id"] == campaign.SOURCE for x in p.records("map"))


def test_operator_stop_during_job_releases_fence_and_pauses(configured):
    p, c = configured

    def discover(*args, **kwargs):
        raise campaign.CampaignStopped("synthetic stop")

    result = campaign.run(c, p.root, judge_factory=Judge, discover=discover)
    assert result["state"] == "stopped" and not p.control.enabled(campaign.SOURCE)
    with p.control.connect() as db:
        assert (
            db.execute("SELECT state FROM jobs WHERE source=?", (campaign.SOURCE,)).fetchone()[0]
            == "failed"
        )


def test_observed_official_url_requires_evidence_bound_to_exact_branch(configured):
    p, c = configured
    t = c["targets"][0]
    t["url"] = t["url"].replace("/one/", "/observed-current/")
    with pytest.raises(ValueError, match="source_backed"):
        campaign.validate(c, p)
    branch = p.get("store", t["store_id"])
    t["observed_url_evidence"] = {
        "store_id": t["store_id"],
        "url": t["url"],
        "evidence_url": t["url"],
        "kind": "observed_official_branch_page",
        "source_address": branch["address"],
        "reviewed_at": 100,
    }
    campaign.validate(c, p)
    t["observed_url_evidence"]["store_id"] = "other_branch"
    with pytest.raises(ValueError, match="source_backed"):
        campaign.validate(c, p)


def test_state_batch_supports_other_states_and_requires_current_address(configured):
    p, c = configured
    c["state"] = "NY"
    # Iowa catalog records cannot be reused for an arbitrary state's activation.
    with pytest.raises(ValueError):
        campaign.validate(c, p)
    c["state"] = "IA"
    c["collection_profile"] = "public-store-layout-evidence-v1"
    with pytest.raises(ValueError, match="current_branch_address"):
        campaign.validate(c, p)
    for target in c["targets"]:
        target["source_address"] = p.get("store", target["store_id"])["address"]
    assert len(campaign.validate(c, p)) == 2


def test_saved_page_fields_publish_without_another_request_or_model_call(configured):
    import json

    p, c = configured
    c["collection_profile"] = campaign.PROFILE
    for target in c["targets"]:
        target["source_address"] = p.get("store", target["store_id"])["address"]
    calls = []

    def discover(platform, job, config, **kwargs):
        target = config["approved_targets"][0]
        calls.append(target["store_id"])
        node = {
            "@type": "GroceryStore",
            "name": target["name"],
            "address": {"streetAddress": "1 Fixture Street", "postalCode": "50010"},
            "telephone": "+15155551234",
        }
        config["_evidence_sink"](
            '<script type="application/ld+json">' + json.dumps(node) + "</script>", target
        )
        return {"map_records": 0}

    result = campaign.run(c, p.root, judge_factory=Judge, discover=discover)
    assert len(calls) == 2
    assert all(r["field_enrichment"]["state"] == "published" for r in result["completed"])
    for target in c["targets"]:
        row = p.get("store", target["store_id"])
        assert row["field_evidence"] and row["field_evidence"][0]["store_id"] == target["store_id"]
        assert row["timezone"] == "America/Chicago"
        assert row["phone"] == "+15155551234"
        assert row["field_provenance"]["phone"]["status"] == "source_reported"
        assert row["field_provenance"]["phone"]["verified_at"] is None


def test_provider_website_candidate_needs_pinned_extract_and_cannot_claim_official_authority(
    configured,
):
    from bord_food_api.crawl_evidence import collect_evidence
    from bord_food_api.store_enrichment import reconcile_fields

    p, c = configured
    c["field_focus"] = True
    t = c["targets"][0]
    s = p.get("store", t["store_id"])
    t["source_address"] = s["address"]
    t["url"] = t["url"] + "/details"
    t["source_authority"] = "community"
    t["observed_url_evidence"] = {
        "store_id": s["id"],
        "url": t["url"],
        "evidence_url": t["url"],
        "kind": "provider_branch_website_candidate",
        "source_id": "overture_places",
        "record_id": "fixture-gers",
        "extract_sha256": "a" * 64,
        "source_address": s["address"],
        "reviewed_at": 1792519000,
    }
    campaign.validate(c, p)
    node = {
        "@type": "GroceryStore",
        "address": {"streetAddress": "1 Fixture Street", "postalCode": "50010"},
        "telephone": "5155551234",
    }
    e = collect_evidence(
        '<script type="application/ld+json">' + json.dumps(node) + "</script>",
        t,
        retrieved_at=1792519000,
    )
    rows = [r for r in e["field_assertions"] if r["field"] == "phone"]
    assert rows and all(r["authority"] == "community" for r in rows)
    result = reconcile_fields(s, rows, now=1792519000)
    assert result["field_provenance"]["phone"]["status"] == "source_reported"
    assert result["field_provenance"]["phone"]["verified_at"] is None
    assert result["field_provenance"]["phone"]["method"] == "provider_branch_report"
    t["observed_url_evidence"]["extract_sha256"] = "missing"
    with pytest.raises(ValueError, match="source_backed"):
        campaign.validate(c, p)
