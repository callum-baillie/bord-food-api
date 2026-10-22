import importlib.util
import json
import time
from pathlib import Path

import pytest

from bord_food_api.nationwide import STATES
from bord_food_api.platform import Platform
from bord_food_api.state_campaigns import (
    field_config,
    group_states,
    new_roster_records,
    prepare_targets,
    rank_states,
)
from bord_food_api.transport import file_hash


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_state_ranking_has_one_grain_and_never_counts_convenience_as_grocery():
    groups = [
        {"State": s, "Store_Type": "Grocery Store", "store_count": i}
        for i, s in enumerate(STATES, 1)
    ]
    groups += [{"State": "WY", "Store_Type": "Convenience Store", "store_count": 9999}]
    reference = {
        "groups": groups,
        "reference_rows_all_formats": sum(r["store_count"] for r in groups),
    }
    ranked = rank_states(reference)
    assert len(ranked) == 50 and ranked[-1]["snap_grocery_format_records"] == 50
    batches = group_states(ranked, count=12, capacity=100)
    states = [s for b in batches for s in b["states"]]
    assert len(states) == len(set(states)) == 12 and "IA" not in states
    assert all(len(b["states"]) <= 3 for b in batches)
    with pytest.raises(ValueError, match="reference_group"):
        rank_states({**reference, "groups": groups + groups[:1]})
    with pytest.raises(ValueError, match="incomplete"):
        rank_states({**reference, "reference_rows_all_formats": 1})


def store(key="1", street="1 Main St", region="WY"):
    return {
        "kind": "store",
        "source_key": "fixture:" + key,
        "payload": {
            "name": "Fixture Grocery",
            "country": "US",
            "spider": "fixture",
            "source_id": key,
            "address": {
                "street": street,
                "city": "Fixture City",
                "region": region,
                "postal_code": "82001",
            },
            "website": "https://fixture.test/locations/" + key,
        },
    }


def test_roster_import_plan_preserves_native_ids_and_holds_colocated_duplicates(tmp_path):
    p = Platform(tmp_path / "data")
    p.sync("all_the_places", "fixture", "old", [store()])
    before = p.records("store")
    d = tmp_path / "bundle/WY"
    d.mkdir(parents=True)
    records = [store(), store("2"), store("3", "3 Main St")]
    path = d / "roster.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    (d / "plan.json").write_text(
        json.dumps(
            {
                "state": "WY",
                "roster_sha256": file_hash(path),
                "source_run": "2026-10-10-13-32-41",
                "archive_sha256": "a" * 64,
            }
        )
    )
    plan = new_roster_records(p, tmp_path / "bundle", "WY")
    assert [r["source_key"] for r in plan["records"]] == ["fixture:3"]
    assert {r["reason"] for r in plan["held"]} == {
        "existing_native_identity_preserved",
        "possible_duplicate_requires_review",
    }
    assert p.records("store") == before
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="binding"):
        new_roster_records(p, tmp_path / "bundle", "WY")


def test_generic_field_validation_keeps_state_identity_and_existing_gates(tmp_path):
    p = Platform(tmp_path)
    p.sync("all_the_places", "fixture", "old", [store()])
    prepared = prepare_targets(p, "WY")
    config = field_config(
        "WY", prepared["targets"], campaign_id="fixture-wy", directory_stores=1, pilot=True
    )
    runner = load("run-iowa-fields.py")
    assert len(runner.validate(config, p)) == 1
    config["state"] = "ND"
    with pytest.raises(ValueError, match="source_backed_state"):
        runner.validate(config, p)
    config["state"] = "WY"
    config["scopes"]["fixture.test"]["crawl"]["max_pages_day"] = 501
    with pytest.raises(ValueError, match="host_limit"):
        runner.validate(config, p)


def test_state_plan_does_not_expand_or_resume_without_explicit_authority(tmp_path):
    runner = load("run-small-states.py")
    plan = {
        "activation_enabled": True,
        "campaign_id": "fixture",
        "batches": [{"states": ["WY", "ND"]}],
        "global_jev_cap_nanousd": 15000000000,
        "deadline": time.time() + 100,
    }
    assert runner.validate_plan(plan) == ["WY", "ND"]
    with pytest.raises(ValueError, match="explicit_bounded"):
        runner.validate_plan({**plan, "batches": [{"states": ["WY", "WY"]}]})
    with pytest.raises(ValueError, match="explicit_bounded"):
        runner.validate_plan({**plan, "batches": [{"states": ["IA"]}]})
    with pytest.raises(ValueError, match="explicit_bounded"):
        runner.validate_plan({**plan, "activation_enabled": False})


def test_actual_partial_publication_keeps_other_states_and_native_replay_ids(tmp_path):
    runner = load("run-small-states.py")
    root = tmp_path / "data"
    p = Platform(root)
    p.sync("all_the_places", "fixture", "before", [store(), store("ia", "1 Iowa Ave", "IA")])
    before = {r["id"]: r for r in p.records("store")}
    bundle = tmp_path / "bundle/WY"
    bundle.mkdir(parents=True)
    records = [store(), store("new", "2 Main St")]
    path = bundle / "roster.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    (bundle / "plan.json").write_text(
        json.dumps(
            {
                "state": "WY",
                "roster_sha256": file_hash(path),
                "source_run": "2026-10-10-13-32-41",
                "archive_sha256": "a" * 64,
            }
        )
    )
    out = tmp_path / "operator"
    out.mkdir()
    p.control.set_source("all_the_places", True)
    first = runner.import_state(root, tmp_path / "bundle", "WY", out, lambda: None)
    assert first["new_native_records"] == 1
    assert first["other_states_unchanged"]
    ia = next(r for r in before.values() if r["address"]["region"] == "IA")
    assert p.get("store", ia["id"]) == ia
    identity = p.get_by_source("store", "all_the_places", "fixture:new")["id"]
    second = runner.import_state(root, tmp_path / "bundle", "WY", out, lambda: None)
    assert second["new_native_records"] == 0
    assert p.get_by_source("store", "all_the_places", "fixture:new")["id"] == identity
    assert len(p.records("store")) == 3


def test_same_branch_url_shared_between_states_is_not_crawled(tmp_path):
    p = Platform(tmp_path)
    other = store("ia", "1 Iowa Ave", "IA")
    other["payload"]["website"] = store()["payload"]["website"]
    p.sync("all_the_places", "fixture", "one", [store(), other])
    prepared = prepare_targets(p, "WY")
    assert not prepared["targets"]
    assert prepared["gaps"][0]["reason"] == "shared_url_identity_review"


def test_serial_controller_holds_unqualified_state_and_checks_next_state(tmp_path, monkeypatch):
    runner = load("run-small-states.py")
    root = tmp_path / "data"
    p = Platform(root)
    p.sync(
        "all_the_places",
        "fixture",
        "one",
        [
            store(str(i), f"{i + 1} Main St", state)
            for i, state in enumerate(["WY"] * 6 + ["AK"] * 6)
        ],
    )
    plan = {
        "campaign_id": "synthetic-small",
        "activation_enabled": True,
        "batches": [{"states": ["WY", "AK"]}],
        "global_jev_cap_nanousd": 15000000000,
        "deadline": time.time() + 100,
        "bundle": "fixture",
        "archive_sha256": "a" * 64,
    }
    (root / "backups/before-synthetic-small").mkdir(parents=True)
    monkeypatch.setattr(runner, "verify_bundle", lambda path: {"archive_sha256": "a" * 64})
    monkeypatch.setattr(runner, "import_state", lambda *args: None)
    monkeypatch.setattr(runner, "verify_backup", lambda *args: None)
    monkeypatch.setattr(runner.signal, "signal", lambda *args: None)
    calls = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            config = json.loads(Path(command[2]).read_text())
            calls.append(config["campaign_id"])
            assert config["campaign_id"].endswith("b00")
            path = root / "crawl-campaigns" / config["campaign_id"]
            path.mkdir()
            (path / "status.json").write_text(
                json.dumps(
                    {
                        "state": "finished_with_holds",
                        "passes": {"primary": {"counts": {"review_required": 5}}},
                    }
                )
            )

        def poll(self):
            return 0

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    result = runner.run(plan, root)
    assert result["state"] == "finished_with_holds" and len(calls) == 2
    assert all(
        s["state"] == "held_after_pilot" and s["unattempted_after_pilot"] == 1
        for s in result["states"].values()
    )


def test_partial_backup_directory_cannot_be_used_for_resume(tmp_path):
    runner = load("run-small-states.py")
    with pytest.raises(ValueError, match="backup_incomplete"):
        runner.verify_backup(tmp_path)
    (tmp_path / "current.json").write_text(json.dumps({"packs": {}}))
    with pytest.raises(ValueError, match="backup_incomplete"):
        runner.verify_backup(tmp_path)


def test_completed_pilot_does_not_skip_remaining_chunks_on_resume():
    runner = load("run-small-states.py")
    pilot = {"campaign_id": "pilot", "state": "finished_with_holds"}
    summary = {"state": "finished_with_holds", "targets": 30, "phases": [pilot]}
    assert not runner.state_complete(summary)
    assert runner.state_complete(
        {**summary, "phases": [pilot, {"campaign_id": "rest", "state": "finished"}]}
    )
    assert runner.state_complete({"state": "held_after_pilot", "targets": 30})
