"""Campaign fixtures; real source/model transports remain blocked by conftest."""

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bord_food_api.platform import Platform

spec = importlib.util.spec_from_file_location(
    "reviewed_campaign", Path(__file__).parents[1] / "scripts/run-reviewed-crawl.py"
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def answer(payload, key):
    return {
        "model": "jev-1.14.0",
        "usage": {"input_tokens": 100},
        "answers": {
            name: {"type": "choice", "choice": next(iter(q["criteria"])), "confidence": 0.99}
            for name, q in payload["questions"].items()
        },
    }


@pytest.fixture
def fixture(tmp_path):
    key = tmp_path / "test-key"
    key.write_text("SYNTHETIC-KEY-DO-NOT-LOG")
    platform = Platform(tmp_path / "data")
    platform.sync(
        "all_the_places",
        "woodmans_markets_us",
        "synthetic",
        [
            {
                "kind": "store",
                "source_key": "woodmans_markets_us:synthetic",
                "payload": {
                    "name": "Synthetic branch",
                    "spider": "woodmans_markets_us",
                    "website": "http://www.woodmans-food.com/synthetic/",
                },
            }
        ],
    )
    store = platform.records("store")[0]
    target = {
        "store_id": store["id"],
        "url": "https://www.woodmans-food.com/store-locations/synthetic/",
        "name": "Synthetic branch",
        "source_website": "http://www.woodmans-food.com/synthetic/",
        "expected_branch": "10 Synthetic Street",
    }
    config = {
        "campaign_id": "synthetic-campaign",
        "targets": [target],
        "decisions": {"key_file": str(key), "max_calls": 40, "budget_nanousd": 500000000},
        "crawl": {
            "global_enabled": True,
            "adapter_enabled": True,
            "source_authorized": True,
            "terms_reviewed": True,
            "robots_reviewed": True,
            "contact": "operator@synthetic.invalid",
            "allowed_host": "www.woodmans-food.com",
            "scope_prefix": "/store-locations/",
            "min_spacing": 30,
            "max_pages_run": 2,
            "max_pages_day": 50,
            "max_bytes": 524288,
        },
    }
    return platform, target, config


def judge(root, config, post=answer):
    return campaign.Judge(
        root, {**config["decisions"], "campaign_id": config["campaign_id"]}, post=post
    )


def test_budget_is_reserved_atomically_across_judges(fixture):
    platform, target, config = fixture
    config["decisions"]["max_calls"] = 1

    def call(_):
        try:
            judge(platform.root, config).before(target)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert sum(executor.map(call, range(6))) == 1
    with judge(platform.root, config).connect() as db:
        assert db.execute("SELECT count(*) FROM decisions").fetchone()[0] == 1


def test_failed_provider_retains_budget_and_redacts_errors(fixture):
    platform, target, config = fixture

    def fail(payload, key):
        raise RuntimeError("secret=" + key)

    client = judge(platform.root, config, fail)
    with pytest.raises(ValueError, match="decision_unavailable_or_invalid") as error:
        client.before(target)
    assert "SYNTHETIC-KEY" not in str(error.value)
    with client.connect() as db:
        row = db.execute("SELECT reserved,state,result FROM decisions").fetchone()
    assert row == (campaign.RESERVATION_NANOUSD, "failed", None)
    assert b"SYNTHETIC-KEY" not in client.database.read_bytes()


def test_global_cap_includes_previous_pilot(fixture):
    platform, target, config = fixture
    client = judge(platform.root, config)
    with client.connect() as db:
        db.execute("INSERT INTO decisions(campaign,reserved) VALUES (?,?)", ("prior", 4990000000))
    with pytest.raises(ValueError, match="budget_exhausted"):
        client.before(target)


def test_low_confidence_decision_withholds_fetch(fixture):
    platform, target, config = fixture

    def uncertain(payload, key):
        result = answer(payload, key)
        result["answers"]["fetch"]["confidence"] = 0.5
        return result

    with pytest.raises(campaign.ReviewRequired):
        judge(platform.root, config, uncertain).before(target)


def test_page_review_only_sends_bounded_observed_safe_links(fixture):
    platform, target, config = fixture
    captured = []

    def post(payload, key):
        captured.append(payload)
        return answer(payload, key)

    html = b'<p>10 Synthetic Street</p><a href="/map.pdf">Store map</a><a href="https://evil.invalid/map.pdf">map</a><a href="/login/">map</a>'
    judge(platform.root, config, post).after(target, html)
    assert captured[0]["state"]["observed_links"] == [
        {"text": "Store map", "url": "https://www.woodmans-food.com/map.pdf"}
    ]
    assert "assets" not in captured[0]
    assert len(captured[0]["questions"]) == 2


def test_invalid_config_cannot_unpause_source(fixture):
    platform, _target, config = fixture
    platform.control.set_source("woodmans_maps", False)
    config["crawl"]["allowed_host"] = "evil.invalid"
    with pytest.raises(ValueError, match="not_reviewed"):
        campaign.run(config, platform.root)
    assert not platform.control.enabled("woodmans_maps")


def test_campaign_publishes_under_fence_and_pauses_afterwards(fixture, monkeypatch):
    platform, target, config = fixture
    original_judge = campaign.Judge
    monkeypatch.setattr(campaign, "Judge", lambda root, c: original_judge(root, c, post=answer))

    def discover(p, job, c, **kwargs):
        p.control.check_fence(job)
        assert c["min_spacing"] >= 30
        p.sync(
            "woodmans_maps",
            "maps",
            "synthetic",
            [
                {
                    "kind": "map",
                    "source_key": "synthetic-map",
                    "payload": {
                        "store_id": target["store_id"],
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

    monkeypatch.setattr(campaign, "run_map_discovery", discover)
    result = campaign.run(config, platform.root)
    assert result["state"] == "finished" and result["completed"][0]["state"] == "published"
    assert not platform.control.enabled("woodmans_maps")
    assert "maps" in platform.current()["packs"]


def test_robots_or_source_block_stops_campaign(fixture, monkeypatch):
    platform, _target, config = fixture
    original_judge = campaign.Judge
    monkeypatch.setattr(campaign, "Judge", lambda root, c: original_judge(root, c, post=answer))

    def blocked(*args, **kwargs):
        raise campaign.CrawlBlocked("Robots denied")

    monkeypatch.setattr(campaign, "run_map_discovery", blocked)
    result = campaign.run(config, platform.root)
    assert result["state"] == "stopped" and not result["completed"]
    assert not platform.control.enabled("woodmans_maps")
    assert "maps" not in platform.current()["packs"]
    persisted = json.loads(
        (platform.root / "crawl-campaigns/synthetic-campaign/status.json").read_text()
    )
    assert persisted["error_type"] == "CrawlBlocked"


def test_advertisement_decision_withholds_candidate_publication(fixture):
    platform, target, config = fixture

    def post(payload, key):
        result = answer(payload, key)
        result["answers"]["link_0"]["choice"] = "advertisement"
        return result

    with pytest.raises(campaign.ReviewRequired, match="candidate_review_required"):
        judge(platform.root, config, post).after(
            target, b'<p>10 Synthetic Street</p><a href="/synthetic.pdf">Store Map</a>'
        )


def test_review_excerpt_prioritizes_visible_branch_content(fixture):
    platform, target, config = fixture
    captured = []

    def post(payload, key):
        captured.append(payload)
        return answer(payload, key)

    html = (
        "<title>Synthetic branch</title><script>"
        + "javascript_noise " * 1000
        + "</script><style>css_noise</style><nav><h1>navigation_noise</h1></nav>"
        + "<div>"
        + "boilerplate " * 1000
        + "</div>"
        + "<main><h1>Synthetic branch</h1><address>10 Synthetic Street</address>"
        + '<div hidden>hidden_noise</div><span aria-hidden="true">aria_noise</span>'
        + '<div style="display: none">style_noise</div>'
        + "<template>template_noise</template><noscript>noscript_noise</noscript>"
        + '<svg>svg_noise</svg><a href="/synthetic.pdf">Store Map</a></main>'
    )
    judge(platform.root, config, post).after(target, html.encode())
    state = captured[0]["state"]
    assert state["page_text"].startswith("Synthetic branch 10 Synthetic Street Store Map")
    assert len(state["page_text"]) <= 4500
    assert "_noise" not in state["page_text"]
    with judge(platform.root, config).connect() as db:
        evidence = json.loads(db.execute("SELECT result FROM decisions").fetchone()[0])
    assert evidence["request_evidence"] == state
    assert len(state["html_sha256"]) == 64
    assert state["observed_links"][0]["url"].endswith("/synthetic.pdf")
    assert "SYNTHETIC-KEY" not in json.dumps(evidence)


def test_off_branch_evidence_remains_subject_to_review(fixture):
    platform, target, config = fixture

    def post(payload, key):
        assert "90 Other Street" in payload["state"]["page_text"]
        result = answer(payload, key)
        result["answers"]["branch"]["choice"] = "review"
        return result

    with pytest.raises(campaign.ReviewRequired, match="branch_review_required"):
        judge(platform.root, config, post).after(
            target, b"<main><h1>Other branch</h1><p>90 Other Street</p></main>"
        )
