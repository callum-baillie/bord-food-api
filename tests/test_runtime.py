import json
import time

import pytest

from bord_food_api.control import Control
from bord_food_api.platform import Platform
from bord_food_api.runtime import heavy_lock, plan, schedule, worker_once
from bord_food_api.settings import Settings, load_policy
from bord_food_api.transport import TransportError


def policy_file(tmp_path, monkeypatch, *, sources=None, mode="bulk_only", **sections):
    config = {
        "network": {"mode": mode},
        "sources": {
            "usda_fdc": {"enabled": False},
            "all_the_places": {"enabled": False},
            **(sources or {}),
        },
        **sections,
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(config))
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(path))
    return Settings(data_dir=tmp_path / "data", import_dir=tmp_path / "imports")


def test_empty_policy_bootstrap_defaults_and_legacy_false(tmp_path, monkeypatch):
    monkeypatch.delenv("BORD_FOOD_CONFIG", raising=False)
    monkeypatch.delenv("AUTO_DOWNLOAD", raising=False)
    settings = Settings(data_dir=tmp_path)
    policy = load_policy(settings)
    assert {name for name, config in policy["sources"].items() if config["enabled"]} == {
        "usda_fdc",
        "all_the_places",
    }
    assert all(not row["would_crawl"] for row in plan(settings))
    assert Platform(tmp_path).current() is None
    monkeypatch.setenv("AUTO_DOWNLOAD", "false")
    assert not load_policy(Settings())["sources"]["usda_fdc"]["enabled"]
    settings = policy_file(tmp_path, monkeypatch, sources={"usda_fdc": {"enabled": True}})
    assert load_policy(settings)["sources"]["usda_fdc"]["enabled"]


def test_durable_restart_dedup_and_missed_intervals_coalesce(tmp_path, monkeypatch):
    settings = policy_file(tmp_path, monkeypatch, sources={"all_the_places": {"enabled": True}})
    assert len(schedule(settings)) == 1
    assert schedule(settings) == []
    control = Control(settings.data_dir)
    job = control.claim("fixture")
    control.finish(job)
    assert schedule(settings) == []
    with control.connect() as db:
        db.execute("UPDATE jobs SET due=?", (time.time() - 10 * 86400,))
    assert len(schedule(settings)) == 1
    assert schedule(settings) == []
    assert plan(settings) == plan(settings)  # Stable installation-specific interval jitter.


def test_worker_mock_bulk_publication_cursor_resume_and_pause(tmp_path, monkeypatch):
    settings = policy_file(tmp_path, monkeypatch, sources={"all_the_places": {"enabled": True}})
    seen = []

    def acquisition(source, policy, transport, directory, cursor):
        seen.append(cursor)
        yield {
            "partition": "synthetic",
            "release": "fixture-r1",
            "records": [
                {"kind": "store", "source_key": "001", "payload": {"name": "Fixture market"}}
            ],
            "complete": True,
            "cursor": {"release": "fixture-r1"},
        }

    assert worker_once(settings, acquisition=acquisition)[0]["state"] == "succeeded"
    platform = Platform(settings.data_dir)
    assert len(platform.records("store")) == 1
    control = platform.control
    control.enqueue("all_the_places", "all", version="next")
    assert worker_once(settings, acquisition=acquisition)[0]["state"] == "succeeded"
    assert seen == [None, {"release": "fixture-r1"}]
    control.set_source("all_the_places", False)
    assert not next(row for row in plan(settings) if row["source"] == "all_the_places")["enabled"]
    assert schedule(settings) == []


def test_worker_local_precedence_and_offline_pin(tmp_path, monkeypatch, foods):
    settings = policy_file(tmp_path, monkeypatch, mode="offline")
    settings.import_dir.mkdir()
    (settings.import_dir / "fixture.json").write_text(json.dumps(foods))
    assert worker_once(settings) == []
    platform = Platform(settings.data_dir)
    assert platform.legacy_path().exists()
    manifest = platform.current()
    assert worker_once(settings) == []
    assert platform.current() == manifest
    monkeypatch.delenv("BORD_FOOD_CONFIG")
    assert (
        next(row for row in plan(settings) if row["source"] == "usda_fdc")["reason"]
        == "local_import_pinned"
    )


def test_worker_retries_transient_and_blocks_credentials(tmp_path, monkeypatch):
    settings = policy_file(tmp_path, monkeypatch, sources={"all_the_places": {"enabled": True}})

    def refused(*_):
        raise TransportError(403)

    assert worker_once(settings, acquisition=refused)[0]["state"] == "blocked_by_credentials"
    control = Control(settings.data_dir)
    assert not control.enabled("all_the_places")
    control.set_source("all_the_places", True)
    control.enqueue("all_the_places", "all", version="transient")

    def unavailable(*_):
        raise TransportError(503, "3600")

    result = worker_once(settings, acquisition=unavailable)
    assert result[0]["state"] == "retry_wait"
    with control.connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE state='retry_wait'").fetchone()
        assert job["due"] >= time.time() + 3590
    assert "secret" not in json.dumps(result)


def test_one_heavy_worker_and_policy_numeric_validation(tmp_path, monkeypatch):
    with heavy_lock(tmp_path), pytest.raises(BlockingIOError), heavy_lock(tmp_path):
        pass
    settings = policy_file(tmp_path, monkeypatch, scheduler={"lease_seconds": 0})
    with pytest.raises(ValueError, match="positive"):
        load_policy(settings)
    settings = policy_file(tmp_path, monkeypatch, runtime={"required_packs": ["imaginary"]})
    with pytest.raises(ValueError, match="unsupported"):
        load_policy(settings)


def test_supervisor_reaps_peer_when_child_fails(monkeypatch):
    from bord_food_api.runtime import supervise

    children = []

    class Child:
        def __init__(self, command):
            self.command = command
            self.returncode = 7 if command[-1] == "serve" else None
            self.waited = False
            children.append(self)

        def poll(self):
            return self.returncode

        def send_signal(self, signum):
            self.returncode = -signum

        def wait(self, timeout):
            self.waited = True
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr("bord_food_api.runtime.subprocess.Popen", Child)
    assert supervise() == 7
    assert [child.command[-1] for child in children] == ["serve", "worker"]
    assert all(child.waited for child in children)


def test_config_retention_expiry_and_shutdown_fence(tmp_path, monkeypatch):
    import threading

    settings = policy_file(
        tmp_path,
        monkeypatch,
        sources={"all_the_places": {"enabled": True, "retention_until": time.time() - 60}},
    )
    assert not next(row for row in plan(settings) if row["source"] == "all_the_places")["enabled"]
    assert "all_the_places" in Control(settings.data_dir).denied_sources()
    settings = policy_file(tmp_path, monkeypatch, sources={"all_the_places": {"enabled": True}})
    control = Control(settings.data_dir)
    control.restrict_source("all_the_places", denied=False, reason="fixture rights restored")
    control.set_source("all_the_places", True)
    stopping = threading.Event()

    def acquired(*_):
        stopping.set()
        yield {"partition": "fixture", "release": "r1", "records": []}

    assert worker_once(settings, acquisition=acquired, cancellation=stopping)[0] == {
        "job_id": next(iter_rows(control))["id"],
        "state": "cancelled",
        "reason": "worker_stopped",
    }
    assert Platform(settings.data_dir).current() is None


def iter_rows(control):
    with control.connect() as db:
        yield from (dict(row) for row in db.execute("SELECT * FROM jobs"))


def test_unchanged_usda_release_does_not_rebuild_or_publish(tmp_path, monkeypatch, foods):
    settings = policy_file(tmp_path, monkeypatch, sources={"usda_fdc": {"enabled": True}})
    source = tmp_path / "synthetic-usda.json"
    source.write_text(json.dumps(foods))

    def acquisition(*_):
        yield {
            "partition": "catalog",
            "release": "fixture-r1",
            "paths": [source],
            "cursor": {"fixture": True},
        }

    first = worker_once(settings, acquisition=acquisition)[0]
    generation = Platform(settings.data_dir).current()["generation"]
    Control(settings.data_dir).enqueue("usda_fdc", "all", version="next")
    monkeypatch.setattr(
        "bord_food_api.importer.build_catalog",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unchanged release rebuilt")),
    )
    second = worker_once(settings, acquisition=acquisition)[0]
    assert not first["no_change"]
    assert second["no_change"]
    assert Platform(settings.data_dir).current()["generation"] == generation


def test_raw_storage_denial_blocks_jobs_and_display_denial_preserves_retained_data(
    tmp_path, monkeypatch
):
    settings = policy_file(
        tmp_path,
        monkeypatch,
        sources={
            "all_the_places": {"enabled": True, "can_store_raw": "deny", "can_display": "deny"}
        },
    )
    platform = Platform(settings.data_dir)
    platform.sync(
        "all_the_places",
        "fixture",
        "r1",
        [{"kind": "store", "source_key": "1", "payload": {"name": "Retained synthetic store"}}],
    )
    assert schedule(settings) == []
    assert platform.records("store") == []
    assert "all_the_places" not in platform.control.denied_sources()
    import sqlite3

    catalog = platform.object_path(platform.current()["packs"]["stores"])
    with sqlite3.connect(catalog) as db:
        assert db.execute("SELECT count(*) FROM entities WHERE kind='store'").fetchone()[0] == 1


def test_normalized_storage_denial_does_not_revoke_existing_display_rights(tmp_path, monkeypatch):
    settings = policy_file(
        tmp_path,
        monkeypatch,
        sources={
            "all_the_places": {
                "enabled": True,
                "can_store_normalized": "deny",
                "can_display": "allow",
            }
        },
    )
    platform = Platform(settings.data_dir)
    platform.sync(
        "all_the_places",
        "fixture",
        "r1",
        [{"kind": "store", "source_key": "1", "payload": {"name": "Retained synthetic store"}}],
    )
    assert schedule(settings) == []
    assert len(platform.records("store")) == 1
    assert "all_the_places" not in platform.control.denied_sources()


def test_disabled_accidental_crawl_job_and_offline_plan_do_not_touch_transport(
    tmp_path, monkeypatch
):
    from bord_food_api.runtime import crawl_plan

    settings = policy_file(tmp_path, monkeypatch)
    assert crawl_plan(settings)["allowed"] is False
    assert crawl_plan(settings)["would_crawl"] is False
    assert crawl_plan(settings)["would_download_assets"] is False
    control = Control(settings.data_dir)
    job_id = control.enqueue("woodmans_maps", "maps", operation="discover_map")
    monkeypatch.setattr(
        "bord_food_api.crawl_runtime.run_map_discovery",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("disabled crawler dispatched")),
    )
    result = worker_once(settings, job_id=job_id, schedule_due=False)
    assert result[0]["state"] == "blocked_by_policy"


def test_explicit_approved_crawl_dispatch_only_claims_requested_job(tmp_path, monkeypatch):
    from bord_food_api.runtime import crawl_plan

    settings = policy_file(
        tmp_path,
        monkeypatch,
        network={"mode": "bulk_only", "crawl_enabled": True},
        crawler={
            "enabled": True,
            "adapters_enabled": ["woodmans_maps"],
            "operator_contact": "catalog@selfhost.net",
            "adapters": {
                "woodmans_maps": {
                    "enabled": True,
                    "source_authorized": True,
                    "terms_reviewed": True,
                    "robots_reviewed": True,
                    "approved_targets": [
                        {
                            "url": "https://www.woodmans-food.com/store-locations/synthetic/",
                            "store_id": "synthetic",
                            "expected_branch": "Synthetic branch",
                        }
                    ],
                }
            },
        },
    )
    assert crawl_plan(settings)["allowed"]
    control = Control(settings.data_dir)
    bulk_id = control.enqueue("usda_fdc", "all")
    job_id = control.enqueue("woodmans_maps", "maps", operation="discover_map")
    called = []

    def discover(platform, job, config):
        called.append(config)
        config["_check"]()
        return platform.sync(
            "woodmans_maps",
            "maps",
            "synthetic-r1",
            [
                {
                    "kind": "map",
                    "source_key": "synthetic",
                    "payload": {
                        "status": "available",
                        "store_id": "synthetic",
                        "asset_downloaded": False,
                    },
                }
            ],
            fence=job,
        )

    monkeypatch.setattr("bord_food_api.crawl_runtime.run_map_discovery", discover)
    result = worker_once(settings, batch_size=1, job_id=job_id, schedule_due=False)
    assert result[0]["state"] == "succeeded"
    assert len(called) == 1
    assert len(Platform(settings.data_dir).records("map")) == 1
    with control.connect() as db:
        assert db.execute("SELECT state FROM jobs WHERE id=?", (bulk_id,)).fetchone()[0] == "queued"


def test_usda_compound_parser_version_is_published_and_reused(tmp_path, monkeypatch, foods):
    settings = policy_file(tmp_path, monkeypatch, sources={"usda_fdc": {"enabled": True}})
    source = tmp_path / "synthetic.json"
    source.write_text(json.dumps(foods))

    def acquisition(*_):
        yield {
            "partition": "catalog",
            "release": "fixture-r1",
            "paths": [source],
            "parser_version": "1:synthetic-filter",
            "cursor": {"fixture": True},
        }

    assert worker_once(settings, acquisition=acquisition)[0]["state"] == "succeeded"
    platform = Platform(settings.data_dir)
    assert (
        platform.current()["sources"]["usda_fdc:catalog"]["parser_version"] == "1:synthetic-filter"
    )
    platform.control.enqueue("usda_fdc", "all", version="second")
    assert worker_once(settings, acquisition=acquisition)[0]["no_change"]


@pytest.mark.parametrize(
    "error_name,reason",
    [
        ("SourceUnresolved", "source_location_unresolved"),
        ("ReconciliationRequired", "source_reconciliation_required"),
    ],
)
def test_source_failures_expose_only_whitelisted_reason_codes(
    tmp_path, monkeypatch, error_name, reason
):
    from bord_food_api import sources

    settings = policy_file(tmp_path, monkeypatch, sources={"all_the_places": {"enabled": True}})
    error_type = getattr(sources, error_name)

    def acquisition(*_):
        raise error_type("private source response https://secret.invalid/?api_key=SECRET")

    report = worker_once(settings, acquisition=acquisition)
    assert report[0]["state"] == "quarantined"
    assert report[0]["reason"] == reason
    assert "SECRET" not in json.dumps(report)
    with Control(settings.data_dir).connect() as db:
        assert db.execute("SELECT reason FROM jobs").fetchone()[0] == reason
