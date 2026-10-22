"""Explicit serial field plan: wait for a pilot, gate follow-up phases on accepted gains.

Configs and this plan are operator files. This never generates URLs, retries holds,
resubmits model jobs, or activates a different state.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from bord_food_api.platform import Platform, atomic_json

TERMINAL = {"finished", "finished_with_holds"}
FIELDS = ("phone", "opening_hours")


def accepted_gains(baseline, rows):
    by = {r["id"]: r for r in rows}
    return sum(
        not old.get(f)
        and bool(by.get(i, {}).get(f))
        and by[i].get("field_provenance", {}).get(f, {}).get("status")
        in {"source_reported", "corroborated", "reviewed"}
        and (f != "opening_hours" or by[i]["field_provenance"][f].get("complete_week") is True)
        and (
            f != "phone"
            or by[i].get("contact_channels", {}).get("phone", {}).get("direct_branch_contact")
            is not False
        )
        for i, old in baseline.items()
        for f in FIELDS
    )


def run(plan, root, *, sleep=time.sleep, invoke=None):
    root = Path(root)
    directory = root / "crawl-campaigns" / plan["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    status = {"state": "waiting_for_pilot", "phases": [], "state_filter": plan["state"]}

    def save():
        status["updated_at"] = time.time()
        atomic_json(directory / "status.json", status)

    def check():
        if (directory / "STOP").exists() or time.time() > plan["deadline"]:
            raise ValueError("operator_stop_or_deadline")

    # Validate the entire planned state before invoking any child.
    for step in plan["phases"]:
        config = json.loads(Path(step["config"]).read_text())
        if config["state"] != plan["state"] or config["campaign_id"] != step["campaign_id"]:
            raise ValueError("field_plan_state_or_campaign_mismatch")
    save()
    try:
        watched = root / "crawl-campaigns" / plan["wait_for"] / "status.json"
        while True:
            check()
            initial = json.loads(watched.read_text()) if watched.exists() else {}
            if initial.get("state") in TERMINAL:
                break
            if initial.get("state") in {
                "stopped",
                "paused_error",
                "paused_budget",
                "paused_source",
            }:
                raise ValueError("pilot_requires_review")
            sleep(15)
        p = Platform(root)
        rows = [p.get("store", i) for i in plan["baseline"]]
        rows = [r for r in rows if r]
        gains = accepted_gains(plan["baseline"], rows)
        status["pilot_accepted_field_gains"] = gains
        if gains < plan.get("minimum_gains", 2):
            raise ValueError("pilot_gain_gate_not_met")
        for step in plan["phases"]:
            check()
            config = json.loads(Path(step["config"]).read_text())
            phase_baseline = {
                t["store_id"]: {f: (p.get("store", t["store_id"]) or {}).get(f) for f in FIELDS}
                for t in config.get("targets", [])
            }
            status.update(state="running", active=step["campaign_id"])
            save()
            log = directory / (step["campaign_id"] + ".log")
            with log.open("a") as output:
                command = [
                    sys.executable,
                    str(Path(__file__).with_name("run-iowa-fields-campaign.py")),
                    step["config"],
                    "--data-dir",
                    str(root),
                    "--run",
                ]
                if invoke:
                    result = invoke(command, stdout=output, stderr=subprocess.STDOUT, check=False)
                else:
                    result = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
                    try:
                        while result.poll() is None:
                            check()
                            sleep(5)
                    except ValueError:
                        child = root / "crawl-campaigns" / step["campaign_id"]
                        child.mkdir(parents=True, exist_ok=True)
                        (child / "STOP").touch()
                        raise
            receipt = json.loads(
                (root / "crawl-campaigns" / step["campaign_id"] / "status.json").read_text()
            )
            status["phases"].append(
                {
                    "campaign_id": step["campaign_id"],
                    "state": receipt["state"],
                    "returncode": result.returncode,
                }
            )
            if receipt["state"] not in TERMINAL:
                raise ValueError("child_requires_review")
            phase_rows = [p.get("store", i) for i in phase_baseline]
            phase_gains = accepted_gains(phase_baseline, [r for r in phase_rows if r])
            status["phases"][-1]["accepted_field_gains"] = phase_gains
            if phase_gains < step.get("minimum_gains", 0):
                raise ValueError("phase_gain_gate_not_met")
        status.update(state="finished", active=None)
    except (OSError, ValueError, KeyError) as error:
        status.update(
            state="held_requires_review",
            reason=str(error) if isinstance(error, ValueError) else type(error).__name__,
            active=None,
        )
    save()
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--run", action="store_true")
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())
    if not a.run:
        print(json.dumps({"state": "staged", "phases": len(plan["phases"]), "network": False}))
        return
    result = run(plan, a.data_dir)
    print(json.dumps(result))
    if result["state"] != "finished":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
