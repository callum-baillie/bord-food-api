import importlib.util
import json
from pathlib import Path

from bord_food_api.crawl_history import CrawlHistory, exception_details, safe_url
from bord_food_api.platform import Platform
from bord_food_api.transport import TransportError

spec = importlib.util.spec_from_file_location(
    "history_cli", Path(__file__).parents[1] / "scripts/crawl-history.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def snapshot(run="run-one", outcome="host_blocked", updated=10):
    return {
        "campaign_id": run,
        "state": "running",
        "started_at": 1,
        "updated_at": updated,
        "targets": {
            "store-one": {
                "state": outcome,
                "host": "grocer.test",
                "reason": "robots_denied",
                "network_attempted": False,
            }
        },
    }


def config(run="run-one", state="IA"):
    return {
        "campaign_id": run,
        "state": state,
        "targets": [
            {
                "store_id": "store-one",
                "name": "Synthetic branch",
                "url": "https://grocer.test/branch?s=7&api_key=secret-value",
                "source_address": {"region": state},
            }
        ],
    }


def events(history):
    with history.connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY id")]


def test_append_history_survives_repeat_resume_later_success_and_another_state(tmp_path):
    history = CrawlHistory(tmp_path)
    assert history.ingest(snapshot(), config(), observed_at=20) == 1
    assert history.ingest(snapshot(), config(), observed_at=30) == 0
    assert (
        history.ingest(snapshot("run-two", "published", 15), config("run-two"), observed_at=40) == 1
    )
    assert (
        history.ingest(
            snapshot("ny-run", "review_required", 20), config("ny-run", "NY"), observed_at=50
        )
        == 1
    )
    summary = history.export()
    assert set(summary["states"]) == {"IA", "NY"}
    attention = json.loads((history.directory / "reports/states/IA/attention.json").read_text())
    assert len(attention) == 1 and attention[0]["run_id"] == "run-one"
    assert len(events(history)) == 3
    assert history.blocking(config()["targets"][0])
    assert "secret-value" not in json.dumps(events(history))


def test_repeated_metadata_enrichment_does_not_duplicate_failures_or_clear_review(tmp_path):
    history = CrawlHistory(tmp_path)
    history.ingest(snapshot(), config())
    stores = {"store-one": {"chain_name": "Synthetic Grocers", "name": "Renamed display label"}}
    assert history.ingest(snapshot(), config(), stores) == 0
    hold = history.blocking(config()["targets"][0])[0]
    history.resolve(hold["hold_key"], "review:operator-test", reviewed_at=50)
    assert history.blocking(config()["targets"][0]) == []
    assert history.ingest(snapshot(), config(), stores) == 0
    assert history.blocking(config()["targets"][0]) == []
    history.ingest(snapshot("new-failure", updated=60), config("new-failure"), observed_at=60)
    assert history.blocking(config()["targets"][0])
    with history.connect() as db:
        assert db.execute("SELECT count(*) FROM reviews").fetchone()[0] == 1


def test_budget_rate_and_missing_url_are_not_failed_requests(tmp_path):
    history = CrawlHistory(tmp_path)
    for run, run_state in [("budget", "paused_budget"), ("daily", "waiting_host_limits")]:
        s = snapshot(run, "pending")
        s.update(state=run_state, next_due=1000)
        history.ingest(s, config(run))
    history.ingest(snapshot("gaps", "missing_branch_url"), config("gaps"))
    rows = events(history)
    assert [r["category"] for r in rows] == ["deferred", "deferred", "unresolved"]
    assert all(r["network_attempted"] is False for r in rows)
    assert history.blocking(config()["targets"][0]) == []
    assert rows[1]["next_check_at"] == 1000


def test_stale_snapshot_cannot_rewrite_later_outcomes_and_unknown_state_is_explicit(tmp_path):
    history = CrawlHistory(tmp_path)
    history.ingest(snapshot(outcome="published", updated=20), config())
    assert history.ingest(snapshot(updated=10), config()) == 0
    history.ingest(snapshot("unknown"), {"campaign_id": "unknown"})
    assert events(history)[-1]["state"] == "UNKNOWN"
    assert events(history)[-1]["http_status"] is None
    assert events(history)[-1]["timestamp_precision"] == "snapshot_observation"


def test_legacy_stopped_active_target_is_retained_as_interrupted(tmp_path):
    history = CrawlHistory(tmp_path)
    s = {
        "campaign_id": "legacy",
        "state": "stopped",
        "active": "store-one",
        "started_at": 10,
        "stopped_at": 20,
        "targets": 14,
        "completed": [],
    }
    history.ingest(s, config("legacy"))
    row = events(history)[0]
    assert (
        row["outcome"] == "interrupted_requires_review" and row["retry_status"] == "manual_review"
    )
    assert row["network_attempted"] is None


def test_http_codes_are_structured_and_arbitrary_exception_text_is_never_saved():
    assert exception_details(TransportError(429)) == {
        "reason": "http_error",
        "http_status": 429,
        "error_type": "TransportError",
    }
    assert exception_details(ValueError("credential=sk-secret")) == {
        "reason": "historical_detail_unavailable",
        "http_status": None,
        "error_type": "ValueError",
    }
    assert "password" not in safe_url("https://user:password@grocer.test/store?token=private&s=7")
    assert "private" not in safe_url("https://grocer.test/store?token=private&s=7")


def test_observer_backfills_readonly_status_and_store_state_without_touching_catalog(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "stores",
        "1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {
                    "name": "Synthetic",
                    "address": {"region": "Wisconsin"},
                    "website": "https://grocer.test/one",
                },
            }
        ],
    )
    store = p.records("store")[0]
    generation = p.current()["generation"]
    path = tmp_path / "crawl-campaigns/legacy/status.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "campaign_id": "legacy",
                "state": "finished",
                "targets": 1,
                "completed_at": 20,
                "completed": [{"store_id": store["id"], "state": "review_required"}],
            }
        )
    )
    before = path.read_bytes()
    history = CrawlHistory(tmp_path)
    first = observer.observe_once(tmp_path, history)
    second = observer.observe_once(tmp_path, history)
    assert first["events_added"] == 1 and second["events_added"] == 0
    assert first["network"] is False and first["paid_calls"] == 0
    assert events(history)[0]["state"] == "WI"
    assert path.read_bytes() == before and p.current()["generation"] == generation
    with p.control.connect() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_future_state_preparation_holds_targets_with_unresolved_history(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "test_national_helpers", Path(__file__).with_name("test_nationwide.py")
    )
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    directory, _ = helpers.bundle(tmp_path)
    p = Platform(tmp_path / "catalog")
    rows = [json.loads(line) for line in (directory / "NY/roster.jsonl").read_text().splitlines()]
    p.sync("all_the_places", "grocer", "fixture", rows)
    store = p.records("store")[0]
    history = CrawlHistory(p.root)
    history.ingest(
        {
            "campaign_id": "prior-ny",
            "state": "finished",
            "completed_at": 1,
            "completed": [
                {"store_id": store["id"], "state": "host_blocked", "host": "retailer.test"}
            ],
        },
        {
            "campaign_id": "prior-ny",
            "state": "NY",
            "targets": [{"store_id": store["id"], "url": store["website"]}],
        },
    )
    prepared = helpers.runner.prepare(directory, "NY", p)
    assert not prepared["targets"] and prepared["held"][0]["reason"] == "prior_history_hold"


def test_registered_metadata_matches_original_fingerprint_and_redacts_keys(tmp_path):
    import hashlib

    h = CrawlHistory(tmp_path)
    original = config()
    original["decisions"] = {"key_file": "/secret/path", "api_key": "never-save-this"}
    registered = h.register(original)
    text = (h.directory / "run-metadata/run-one.json").read_text()
    assert (
        "never-save-this" not in text and "secret-value" not in text and "/secret/path" not in text
    )
    digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
    assert observer.configs_in(h.directory / "run-metadata")["run-one"][0][0] == digest
    h.ingest(snapshot(), original)
    assert h.ingest(snapshot(), registered) == 0


def test_legacy_string_addresses_do_not_break_history_or_guess_state(tmp_path):
    h = CrawlHistory(tmp_path)
    cfg = config("legacy-full")
    cfg["state"] = None
    cfg["targets"][0]["source_address"] = "10 Synthetic St, Test, Wisconsin 50000"
    h.ingest(snapshot("legacy-full"), cfg)
    cfg = config("legacy-short")
    cfg["state"] = None
    cfg["targets"][0]["source_address"] = "10 Synthetic St"
    h.ingest(snapshot("legacy-short"), cfg, {"store-one": {"address": {"region": "IL"}}})
    assert [r["state"] for r in events(h)] == ["WI", "IL"]


def test_metadata_upgrade_preserves_review_and_inherited_hold_cannot_block_new_host(tmp_path):
    h = CrawlHistory(tmp_path)
    original = snapshot(outcome="review_required")
    original["targets"]["store-one"]["reason"] = "page_review"
    h.ingest(original, config())
    hold = h.blocking(config()["targets"][0])[0]
    h.resolve(hold["hold_key"], "review:exact-retained-page", reviewed_at=20)
    upgraded = snapshot(outcome="review_required", updated=30)
    upgraded["targets"]["store-one"].update(
        reason="historical_detail_unavailable", field_observations={"phone": 1}
    )
    h.ingest(upgraded, config())
    assert h.blocking(config()["targets"][0]) == []
    inherited = snapshot("inherited", "prior_history_hold", 40)
    inherited["targets"]["store-one"]["reason"] = "prior_history_hold"
    cfg = config("inherited")
    cfg["targets"][0]["url"] = "https://canonical.test/branch"
    h.ingest(inherited, cfg)
    assert h.blocking(cfg["targets"][0]) == []
    # A new physical failure still creates a fresh hold.
    failed = snapshot("new-attempt", "host_blocked", 50)
    h.ingest(failed, config("new-attempt"))
    assert h.blocking(config()["targets"][0])
