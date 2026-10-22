import copy
import importlib.util
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from bord_food_api.platform import Platform
from bord_food_api.runtime import heavy_lock
from bord_food_api.transport import TransportError

spec = importlib.util.spec_from_file_location(
    "statewide", Path(__file__).parents[1] / "scripts/run-iowa-statewide.py"
)
statewide = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statewide)


def setup(tmp_path, hosts=("one", "two")):
    p = Platform(tmp_path)
    rows = [
        {
            "kind": "store",
            "source_key": str(i),
            "payload": {
                "name": "Synthetic " + str(i),
                "spider": "fixture",
                "chain_key": host,
                "chain_name": host,
                "source_id": str(i),
                "address": {"region": "IA"},
                "website": f"https://{host}.test/stores/{i}",
            },
        }
        for i, host in enumerate(hosts)
    ]
    p.sync("all_the_places", "fixture", "fixture", rows)
    targets = [
        {
            "store_id": s["id"],
            "name": s["name"],
            "chain_id": s["chain_id"],
            "spider": "fixture",
            "source_website": s["website"],
            "url": s["website"],
            "source_address": s["address"],
            "expected_branch": s["name"],
        }
        for s in p.records("store")
    ]
    scopes = {}
    for target in targets:
        host = urlsplit(target["url"]).hostname
        scopes[host] = {
            "state": "approved",
            "review_evidence": "synthetic owner scope",
            "crawl": {
                "global_enabled": True,
                "adapter_enabled": True,
                "source_authorized": True,
                "owner_public_robots_authorized": True,
                "terms_reviewed": False,
                "robots_reviewed": True,
                "contact": "hello@synthetic.invalid",
                "allowed_host": host,
                "scope_prefix": "/stores/",
                "max_pages_run": 2,
                "max_pages_day": 50,
                "max_bytes": 524288,
                "min_spacing": 45,
            },
        }
    return p, {
        "campaign_id": "synthetic-statewide",
        "activation_enabled": True,
        "state": "IA",
        "collection_profile": statewide.PROFILE,
        "capture_product_inventory": False,
        "capture_product_catalog": False,
        "targets": targets,
        "scopes": scopes,
        "duration_seconds": 7 * 86400,
        "decisions": {"budget_nanousd": 100000000, "max_calls": 10, "key_file": "unused"},
    }


class Judge:
    def __init__(self, *args):
        pass

    def before(self, target):
        pass


def test_blocked_host_is_not_retried_and_other_branches_progress(tmp_path):
    p, c = setup(tmp_path, ("one", "one", "two"))
    calls = []

    def discover(p, job, crawl, **kwargs):
        host = crawl["allowed_host"]
        calls.append(host)
        p.control.check_fence(job)
        if host == "one.test":
            raise TransportError(403)
        crawl["_evidence_sink"]("<main>Synthetic branch</main>", crawl["approved_targets"][0])
        return {"map_records": 0}

    result = statewide.run(c, p.root, judge_factory=Judge, discover=discover, install_signals=False)
    assert result["state"] == "finished_with_holds"
    assert result["counts"] == {"host_blocked": 2, "published": 1}
    assert calls.count("one.test") == 1 and calls.count("two.test") == 1
    assert not p.control.enabled("retailer_maps")
    evidence = json.loads(
        next(
            (p.root / "crawl-campaigns" / c["campaign_id"] / "evidence").glob("*.json")
        ).read_text()
    )
    assert evidence["capture_policy"]["product_inventory"] is False


def frontier(p, host, now, requests=50, expires=None, body="User-agent: *\nAllow: /\n"):
    path = p.root / "control/crawl_frontier.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE crawl_hosts(host PRIMARY KEY,day,requests,last_request)")
        db.execute("CREATE TABLE crawl_robots(host PRIMARY KEY,body,status,expires)")
        db.execute(
            "INSERT INTO crawl_hosts VALUES(?,?,?,?)", (host, int(now // 86400), requests, now)
        )
        if expires:
            db.execute("INSERT INTO crawl_robots VALUES(?,?,200,?)", (host, body, expires))
    return path


def test_daily_capacity_defers_without_paid_decision_and_releases_worker_lock(tmp_path):
    p, c = setup(tmp_path, ("one",))
    now = [time.time()]
    frontier(p, "one.test", now[0])
    paid = []
    slept = []

    class J(Judge):
        def before(self, target):
            paid.append(now[0])

    def sleep(seconds):
        with heavy_lock(p.root):
            pass
        assert paid == []
        slept.append(seconds)
        # Jump across the UTC boundary without an actual long sleep.
        now[0] = (int(now[0] // 86400) + 1) * 86400 + 61

    result = statewide.run(
        c,
        p.root,
        judge_factory=J,
        discover=lambda *a, **k: {"map_records": 0},
        clock=lambda: now[0],
        sleep=sleep,
        install_signals=False,
    )
    assert result["counts"] == {"published": 1} and len(paid) == 1
    assert slept and max(slept) <= 5


def test_expired_robots_needs_two_slots_and_cached_stricter_delay_applies(tmp_path):
    p, c = setup(tmp_path, ("one",))
    now = time.time()
    path = frontier(p, "one.test", now, requests=49)
    policy = c["scopes"]["one.test"]["crawl"]
    assert statewide.host_due(p.root, "one.test", policy, now) > now + 45
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO crawl_robots VALUES(?,?,200,?)",
            ("one.test", "User-agent: *\nCrawl-delay: 120\n", now + 500),
        )
    assert statewide.host_due(p.root, "one.test", policy, now) == now + 120


def test_global_budget_pauses_pending_without_paid_calls_and_resume_is_explicit(tmp_path):
    p, c = setup(tmp_path)
    path = p.root / "control/jev-crawl-budget.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE decisions(campaign,reserved)")
        db.execute("INSERT INTO decisions VALUES(?,?)", ("prior", 4990000000))

    class Never:
        def __init__(self, *args):
            pass

        def before(self, *args):
            raise AssertionError("no budget for paid calls")

    result = statewide.run(c, p.root, judge_factory=Never, install_signals=False)
    assert result["state"] == "paused_budget" and result["counts"] == {"pending": 2}
    with pytest.raises(ValueError, match="explicit_resume"):
        statewide.run(c, p.root, judge_factory=Never, install_signals=False)
    resumed = statewide.run(c, p.root, resume=True, judge_factory=Never, install_signals=False)
    assert resumed["state"] == "paused_budget"
    with p.control.connect() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_resume_keeps_completed_and_interrupted_branches_without_automatic_retry(tmp_path):
    p, c = setup(tmp_path)
    calls = []

    def discover(p, job, crawl, **kwargs):
        calls.append(job["id"])
        if len(calls) == 1:
            raise statewide.Stopped("synthetic stop")
        return {"map_records": 0}

    first = statewide.run(c, p.root, judge_factory=Judge, discover=discover, install_signals=False)
    assert first["state"] == "stopped" and first["counts"]["interrupted_requires_review"] == 1
    second = statewide.run(
        c, p.root, resume=True, judge_factory=Judge, discover=discover, install_signals=False
    )
    assert (
        second["counts"] == {"interrupted_requires_review": 1, "published": 1} and len(calls) == 2
    )


def test_failed_scope_validation_never_constructs_paid_transport(tmp_path):
    p, c = setup(tmp_path)
    c["targets"][0]["source_address"] = {"region": "NY"}

    def unavailable(*args):
        raise AssertionError("no model construction")

    with pytest.raises(ValueError):
        statewide.run(c, p.root, judge_factory=unavailable, install_signals=False)


def test_offline_pacing_amendment_preserves_results_counters_budget_and_resumes_pending(tmp_path):
    p, original = setup(tmp_path, ("one", "two", "three"))
    calls = []

    def discover(p, job, crawl, **kwargs):
        calls.append(crawl["approved_targets"][0]["store_id"])
        if len(calls) == 2:
            raise statewide.Stopped("synthetic stop")
        return {"map_records": 0}

    first = statewide.run(
        original, p.root, judge_factory=Judge, discover=discover, install_signals=False
    )
    assert first["counts"] == {"published": 1, "interrupted_requires_review": 1, "pending": 1}
    frontier_path = frontier(p, "one.test", time.time(), requests=50)
    before = frontier_path.read_bytes()
    amended = copy.deepcopy(original)
    for scope in amended["scopes"].values():
        scope["crawl"].update(max_pages_day=500, spacing_jitter_seconds=45)
    result = statewide.amend_pacing(original, amended, p.root)
    assert result["targets"] == first["targets"]
    assert result["started_at"] == first["started_at"]
    assert result["config_revisions"][0]["previous_sha256"] == first["config_sha256"]
    assert result["config_sha256"] != first["config_sha256"]
    assert frontier_path.read_bytes() == before
    assert amended["decisions"] == original["decisions"]
    final = statewide.run(
        amended,
        p.root,
        resume=True,
        judge_factory=Judge,
        discover=discover,
        install_signals=False,
    )
    assert len(calls) == len(set(calls)) == 3
    assert final["counts"] == {"published": 2, "interrupted_requires_review": 1}


def test_pacing_amendment_rejects_other_changes_active_worker_and_wrong_config(tmp_path):
    p, original = setup(tmp_path, ("one",))
    statewide.run(
        original,
        p.root,
        judge_factory=Judge,
        discover=lambda *a, **k: {"map_records": 0},
        install_signals=False,
    )
    amended = copy.deepcopy(original)
    amended["decisions"]["max_calls"] += 1
    with pytest.raises(ValueError, match="only_pacing"):
        statewide.amend_pacing(original, amended, p.root)
    with (
        statewide.controller_lock(p.root / "crawl-campaigns" / original["campaign_id"]),
        pytest.raises(BlockingIOError),
    ):
        statewide.amend_pacing(original, original, p.root)
    wrong = copy.deepcopy(original)
    wrong["scopes"]["one.test"]["crawl"]["max_pages_day"] = 49
    with pytest.raises(ValueError, match="previous_config_mismatch"):
        statewide.amend_pacing(wrong, original, p.root)
    excessive = copy.deepcopy(original)
    excessive["scopes"]["one.test"]["crawl"]["max_pages_day"] = 501
    with pytest.raises(ValueError, match="host_limit"):
        statewide.amend_pacing(original, excessive, p.root)


def test_one_malformed_page_is_retained_as_review_and_other_hosts_continue(tmp_path):
    p, c = setup(tmp_path)
    c["field_focus"] = True
    calls = []

    def discover(platform, job, config, **kwargs):
        calls.append(config["approved_targets"][0]["store_id"])
        if len(calls) == 1:
            raise TypeError("synthetic-provider-secret-must-not-leak")
        return {"map_records": 0}

    result = statewide.run(c, p.root, judge_factory=Judge, discover=discover, install_signals=False)
    assert result["state"] == "finished_with_holds" and result["counts"] == {
        "review_required": 1,
        "published": 1,
    }
    assert len(calls) == 2
    failed = next(i for i in result["targets"].values() if i["state"] == "review_required")
    assert failed["reason"] == "field_parser_error" and failed["error_frames"]
    assert "synthetic-provider-secret" not in json.dumps(result)


def test_unreachable_source_holds_host_without_stopping_other_hosts(tmp_path):
    p, c = setup(tmp_path)
    calls = []

    def discover(platform, job, config, **kwargs):
        calls.append(config["approved_targets"][0]["store_id"])
        if len(calls) == 1:
            raise OSError("source_connection_failed")
        return {"map_records": 0}

    result = statewide.run(c, p.root, judge_factory=Judge, discover=discover, install_signals=False)
    assert result["counts"] == {"host_blocked": 1, "published": 1}
    blocked = next(i for i in result["targets"].values() if i["state"] == "host_blocked")
    assert blocked["reason"] == "source_connection_failed"
