import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "field_plan", Path(__file__).parents[1] / "scripts/run-store-field-plan.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_gain_gate_excludes_partial_hours_chain_contacts_and_unsupported_values():
    baseline = {"one": {"phone": None, "opening_hours": None}}
    row = {
        "id": "one",
        "phone": "8555551234",
        "opening_hours": [{"day": "Mo"}],
        "field_provenance": {
            "phone": {"status": "source_reported"},
            "opening_hours": {"status": "source_reported", "complete_week": False},
        },
        "contact_channels": {"phone": {"direct_branch_contact": False}},
    }
    assert m.accepted_gains(baseline, [row]) == 0
    row["contact_channels"] = {}
    row["field_provenance"]["opening_hours"]["complete_week"] = True
    assert m.accepted_gains(baseline, [row]) == 2
    row["field_provenance"]["phone"]["status"] = "conflicted"
    assert m.accepted_gains(baseline, [row]) == 1


def test_no_child_is_invoked_when_initial_pilot_requires_review(tmp_path):
    path = tmp_path / "crawl-campaigns/first"
    path.mkdir(parents=True)
    (path / "status.json").write_text(json.dumps({"state": "paused_error"}))
    config = tmp_path / "second.json"
    config.write_text(json.dumps({"state": "IA", "campaign_id": "second"}))
    plan = {
        "campaign_id": "plan",
        "state": "IA",
        "wait_for": "first",
        "deadline": time.time() + 100,
        "baseline": {},
        "phases": [{"campaign_id": "second", "config": str(config)}],
    }

    def forbidden(*args, **kwargs):
        pytest.fail("child must remain inactive")

    assert m.run(plan, tmp_path, invoke=forbidden)["state"] == "held_requires_review"
    plan["phases"][0]["campaign_id"] = "other"
    with pytest.raises(ValueError, match="mismatch"):
        m.run(plan, tmp_path, invoke=forbidden)


def test_second_pilot_must_add_accepted_fields_before_wider_run(tmp_path, monkeypatch):
    first = tmp_path / "crawl-campaigns/first"
    first.mkdir(parents=True)
    (first / "status.json").write_text(json.dumps({"state": "finished_with_holds"}))
    steps = []
    for name in ["pilot", "wider"]:
        config = tmp_path / (name + ".json")
        config.write_text(
            json.dumps({"state": "IA", "campaign_id": name, "targets": [{"store_id": "one"}]})
        )
        steps.append({"campaign_id": name, "config": str(config), "minimum_gains": 1})
    plan = {
        "campaign_id": "plan",
        "state": "IA",
        "wait_for": "first",
        "deadline": time.time() + 100,
        "baseline": {},
        "minimum_gains": 0,
        "phases": steps,
    }
    monkeypatch.setattr(
        m, "Platform", lambda root: SimpleNamespace(get=lambda kind, key: {"id": key})
    )
    invoked = []

    def invoke(command, **kwargs):
        invoked.append(command)
        assert len(invoked) == 1
        path = tmp_path / "crawl-campaigns/pilot"
        path.mkdir()
        (path / "status.json").write_text(json.dumps({"state": "finished_with_holds"}))
        return SimpleNamespace(returncode=0)

    status = m.run(plan, tmp_path, invoke=invoke)
    assert status["reason"] == "phase_gain_gate_not_met"
    assert status["phases"][0]["accepted_field_gains"] == 0
    assert len(invoked) == 1
