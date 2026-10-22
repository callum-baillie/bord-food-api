import copy
import importlib.util
from pathlib import Path

from bord_food_api.platform import Platform, atomic_json

spec = importlib.util.spec_from_file_location(
    "field_campaign", Path(__file__).parents[1] / "scripts/run-iowa-fields-campaign.py"
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def setup(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": str(i),
                "payload": {
                    "name": "Imaginary Grocery " + str(i),
                    "country": "US",
                    "address": {
                        "street": str(i + 1) + " Main St",
                        "city": "Ames",
                        "region": "IA",
                        "postal_code": "50010",
                    },
                    "website": "https://fixture.test/store/" + str(i),
                },
            }
            for i in range(2)
        ],
    )
    rows = p.records("store")
    targets = [
        {
            "store_id": s["id"],
            "name": s["name"],
            "spider": s.get("spider"),
            "chain_id": s.get("chain_id"),
            "source_address": s["address"],
            "source_website": s["website"],
            "url": s["website"],
            "expected_branch": s["name"],
        }
        for s in rows
    ]
    crawl = {
        "global_enabled": True,
        "adapter_enabled": True,
        "source_authorized": True,
        "owner_public_robots_authorized": True,
        "robots_reviewed": True,
        "contact": "ops@fixture.org",
        "allowed_host": "fixture.test",
        "scope_prefix": "/store/",
        "max_pages_run": 3,
        "max_pages_day": 500,
        "max_bytes": 2097152,
        "min_spacing": 45,
        "can_store_raw": True,
    }
    c = {
        "campaign_id": "fixture-campaign",
        "state": "IA",
        "activation_enabled": True,
        "field_focus": True,
        "capture_prices": False,
        "capture_product_inventory": False,
        "capture_product_catalog": False,
        "collection_profile": "public-store-layout-evidence-v1",
        "duration_seconds": 3600,
        "directory_stores": 2,
        "coverage_gaps": [],
        "targets": targets,
        "scopes": {
            "fixture.test": {
                "state": "approved",
                "review_evidence": "synthetic exact source",
                "crawl": crawl,
            }
        },
        "decisions": {
            "max_calls": 10,
            "budget_nanousd": 100000000,
            "global_budget_nanousd": 15000000000,
            "key_file": "unused",
        },
    }
    return p, c


def test_followup_uses_observed_www_aliases_and_preserves_identity_holds(tmp_path):
    p, c = setup(tmp_path)
    one, two = c["targets"]
    status = {
        "targets": {
            one["store_id"]: {
                "state": "host_blocked",
                "stage": "robots",
                "http_status": 301,
                "redirect_candidate": "https://www.fixture.test/robots.txt",
                "finished_at": 1,
            },
            two["store_id"]: {"state": "host_blocked"},
        }
    }
    result = campaign.canonical_followup(c, status, p)
    assert len(result["targets"]) == 2
    assert all(
        t["url"].startswith("https://www.fixture.test/store/") and t["canonical_review_required"]
        for t in result["targets"]
    )
    assert {t["store_id"] for t in result["targets"]} == {t["store_id"] for t in c["targets"]}
    for bad in [
        "https://unrelated.test/robots.txt",
        "https://127.0.0.1/robots.txt",
        "https://www.fixture.test/store?token=secret",
    ]:
        changed = copy.deepcopy(status)
        changed["targets"][one["store_id"]]["redirect_candidate"] = bad
        assert campaign.canonical_followup(c, changed, p)["targets"] == []
    status["targets"][one["store_id"]]["http_status"] = 403
    assert campaign.canonical_followup(c, status, p)["targets"] == []


def test_parent_has_no_extra_pass_when_primary_finishes_and_resumes_without_recrawl(
    tmp_path, monkeypatch
):
    p, c = setup(tmp_path)
    calls = []
    monkeypatch.setattr(campaign.signal, "signal", lambda *_: None)

    def run(config, root, **kwargs):
        calls.append(config["campaign_id"])
        r = {
            "campaign_id": config["campaign_id"],
            "state": "finished",
            "counts": {"published": 2},
            "targets": {t["store_id"]: {"state": "published"} for t in config["targets"]},
        }
        atomic_json(Path(root) / "crawl-campaigns" / config["campaign_id"] / "status.json", r)
        return r

    monkeypatch.setattr(campaign.fields.statewide, "run", run)
    first = campaign.run(c, p.root)
    assert first["state"] == "finished" and first["passes"]["canonical"]["state"] == "not_needed"
    assert not list((p.root / "crawl-campaigns").glob("*/STOP"))
    second = campaign.run(c, p.root, resume=True)
    assert second["state"] == "finished" and len(calls) == 1


def test_successful_canonical_route_is_reused_only_for_unchanged_store(tmp_path):
    p, c = setup(tmp_path)
    saved = copy.deepcopy(c)
    saved["campaign_id"] = "iowa-fields-fixture-canonical"
    saved["targets"][0]["url"] = "https://www.fixture.test/store/0"
    directory = p.root / "crawl-campaigns/iowa-fields-fixture"
    atomic_json(directory / "canonical-config.json", saved)
    atomic_json(
        p.root / "crawl-campaigns" / saved["campaign_id"] / "status.json",
        {"targets": {saved["targets"][0]["store_id"]: {"state": "published", "finished_at": 2}}},
    )
    reused = campaign.retained_canonical_targets(c, p.root)
    assert reused["targets"][0]["url"] == saved["targets"][0]["url"]
    assert reused["scopes"]["www.fixture.test"]["crawl"]["allowed_host"] == "www.fixture.test"
    changed = copy.deepcopy(c)
    changed["targets"][0]["source_address"]["street"] = "99 Changed St"
    assert (
        campaign.retained_canonical_targets(changed, p.root)["targets"][0]["url"]
        == c["targets"][0]["url"]
    )
