import importlib.util
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
                "address": {"region": "IA"},
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
