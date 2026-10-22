"""Serial, explicitly activated small-state scans using the shared field runner.

Default is inspection. --run imports only new native retained ATP identities,
reconciles selected-state fields, then runs a five-page pilot and <=25-page chunks.
No source downloads, product inventories, images, prices or OpenAI submissions.
"""

import argparse
import fcntl
import importlib.util
import json
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from bord_food_api.domain import content_hash
from bord_food_api.nationwide import REGIONS, STATES, verify_bundle
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import Lease
from bord_food_api.state_campaigns import field_config, new_roster_records, prepare_targets
from bord_food_api.store_enrichment import publish_enrichment, reconcile_fields, snapshot_assertions
from bord_food_api.store_quality import clean_store

spec = importlib.util.spec_from_file_location(
    "state_fields", Path(__file__).with_name("run-iowa-fields.py")
)
fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fields)


def validate_plan(plan):
    states = [s for b in plan["batches"] for s in b["states"]]
    if (
        plan.get("activation_enabled") is not True
        or not 1 <= len(states) <= 12
        or len(set(states)) != len(states)
        or any(s not in STATES or s == "IA" for s in states)
        or any(not 1 <= len(b["states"]) <= 3 for b in plan["batches"])
        or plan.get("global_jev_cap_nanousd") != 15000000000
    ):
        raise ValueError("explicit_bounded_state_plan_required")
    return states


def verify_backup(directory):
    """An interrupted backup directory is not evidence of a completed backup."""
    directory = Path(directory)
    try:
        manifest = json.loads((directory / "current.json").read_text())
        for name in manifest["packs"].values():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                raise ValueError("backup_incomplete_requires_review")
        for name, table in [
            ("control.sqlite", "identities"),
            ("control/crawl_frontier.sqlite", "crawl_hosts"),
            ("control/crawl-history/history.sqlite", "events"),
            ("control/jev-crawl-budget.sqlite", "decisions"),
        ]:
            path = directory / name
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                if (
                    db.execute("pragma quick_check").fetchone()[0] != "ok"
                    or not db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    ).fetchone()
                ):
                    raise ValueError("backup_incomplete_requires_review")
    except (OSError, KeyError, sqlite3.DatabaseError) as error:
        raise ValueError("backup_incomplete_requires_review") from error


def state_complete(summary):
    if summary.get("state") in {"held_after_pilot", "no_eligible_targets"}:
        return True
    if summary.get("state") not in {"finished", "finished_with_holds"}:
        return False
    targets = summary.get("targets", 0)
    expected = int(targets > 0) + (max(0, targets - 5) + 24) // 25
    phases = summary.get("phases", [])
    return len(phases) == expected and all(
        p["state"] in {"finished", "finished_with_holds"} for p in phases
    )


def import_state(root, bundle, state, directory, check):
    p = Platform(root)
    with fields.statewide.worker_slot(root, check, time.sleep):
        check()
        previous = p.current()
        before = {s["id"]: s for s in p.records("store")}
        plan = new_roster_records(p, bundle, state)
        atomic_json(
            directory / "roster-review.json", {k: v for k, v in plan.items() if k != "records"}
        )
        if plan["records"]:
            partition = "operator-small-state-" + state
            job_id = p.control.enqueue(
                "all_the_places",
                partition,
                operation="operator_partial_state_roster",
                version=plan["release"],
            )
            job = p.control.claim("small-state-roster", ttl=120, job_id=job_id)
            if not job:
                raise ValueError("state_import_claim_failed")
            try:
                with Lease(p.control, job, 120, 20) as lease:
                    p.sync(
                        "all_the_places",
                        partition,
                        plan["source_run"] + ":partial-state:" + plan["release"],
                        plan["records"],
                        complete=False,
                        parser_version="retained-state-roster-v1",
                        cursor={
                            "source_run": plan["source_run"],
                            "region": state,
                            "complete": False,
                            "archive_sha256": plan["archive_sha256"],
                        },
                        fence=job,
                    )
                    lease.check()
                    p.control.finish(job)
            except BaseException:
                p.control.finish(job, state="failed", reason="state_roster_publication_failed")
                raise
        raw = {s["id"]: s for s in p.records("store")}
        assert all(raw.get(i) == r for i, r in before.items()), "existing_store_changed_by_roster"
        for pack, value in previous["packs"].items():
            assert pack in {"stores", "chains"} or p.current()["packs"].get(pack) == value
        selected = [
            r
            for r in p.iter_records("store")
            if REGIONS.get(str(r.get("address", {}).get("region", "")).casefold()) == state
        ]
        updated = [
            reconcile_fields(
                clean_store(r),
                snapshot_assertions(r, source_id=r.get("catalog_source")),
                now=time.time(),
            )
            for r in selected
        ]
        base = p.current()["generation"]
        enrichment = publish_enrichment(
            p, updated, base_generation=base, release=content_hash(updated), now=time.time()
        )
        after = {s["id"]: s for s in p.records("store")}
        assert all(
            after.get(i) == r
            for i, r in before.items()
            if REGIONS.get(str(r.get("address", {}).get("region", "")).casefold()) != state
        ), "other_state_payload_changed"
        receipt = {
            "state": state,
            "new_native_records": len(plan["records"]),
            "roster_holds": len(plan["held"]),
            "generation": p.current()["generation"],
            "enrichment_changes": enrichment["changed"],
            "all_existing_native_records_preserved_by_roster": True,
            "other_states_unchanged": True,
            "non_store_packs_unchanged": True,
            "census_complete": False,
        }
        atomic_json(directory / "publication.json", receipt)
        return receipt


def run(plan, root, *, resume=False):
    states = validate_plan(plan)
    root = Path(root)
    directory = root / "crawl-campaigns" / plan["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    fingerprint = content_hash(plan)
    status_path = directory / "status.json"
    if status_path.exists() and not resume:
        raise ValueError("explicit_resume_required")
    status = (
        json.loads(status_path.read_text())
        if status_path.exists()
        else {
            "campaign_id": plan["campaign_id"],
            "config_sha256": fingerprint,
            "state": "starting",
            "states": {},
            "started_at": time.time(),
        }
    )
    if status["config_sha256"] != fingerprint:
        raise ValueError("resume_plan_changed")
    stopped = [False]
    signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stopped.__setitem__(0, True))

    def save():
        status["updated_at"] = time.time()
        atomic_json(status_path, status)

    def check():
        if stopped[0] or (directory / "STOP").exists() or time.time() > plan["deadline"]:
            raise ValueError("operator_stop_or_deadline")

    def child(config_path, config):
        child_dir = root / "crawl-campaigns" / config["campaign_id"]
        old_path = child_dir / "status.json"
        old = json.loads(old_path.read_text()) if old_path.exists() else None
        if old and old["state"] in {"finished", "finished_with_holds"}:
            return old
        command = [
            sys.executable,
            str(Path(__file__).with_name("run-iowa-fields-campaign.py")),
            str(config_path),
            "--data-dir",
            str(root),
            "--run",
        ]
        if old:
            command.append("--resume")
        with (directory / (config["campaign_id"] + ".log")).open("a") as output:
            proc = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
            try:
                while proc.poll() is None:
                    check()
                    time.sleep(5)
            except ValueError:
                child_dir.mkdir(parents=True, exist_ok=True)
                (child_dir / "STOP").touch()
                proc.wait(timeout=180)
                raise
        if not old_path.exists():
            return {
                "state": "held_requires_review",
                "error_type": "child_no_status",
                "returncode": proc.returncode,
            }
        return json.loads(old_path.read_text())

    with (directory / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            bundle = Path(plan["bundle"])
            verified = verify_bundle(bundle)
            if verified["archive_sha256"] != plan["archive_sha256"]:
                raise ValueError("state_source_bundle_changed")
            save()
            backup = root / "backups" / ("before-" + plan["campaign_id"])
            if not backup.exists():
                status.update(state="backing_up", active=None)
                save()
                with fields.statewide.worker_slot(root, check, time.sleep):
                    check()
                    Platform(root).backup(backup)
                    for name in [
                        "control/crawl_frontier.sqlite",
                        "control/crawl-history/history.sqlite",
                        "control/jev-crawl-budget.sqlite",
                    ]:
                        target = backup / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with (
                            sqlite3.connect(
                                (root / name).as_uri() + "?mode=ro", uri=True
                            ) as source,
                            sqlite3.connect(target) as dest,
                        ):
                            source.backup(dest)
                            assert dest.execute("pragma quick_check").fetchone()[0] == "ok"
            verify_backup(backup)
            for state in states:
                check()
                if state_complete(status["states"].get(state, {})):
                    continue
                status.update(state="running", active=state)
                save()
                sd = directory / state
                sd.mkdir(exist_ok=True)
                if not (sd / "publication.json").exists():
                    import_state(root, bundle, state, sd, check)
                prepared_path = sd / "targets.json"
                if not prepared_path.exists():
                    atomic_json(prepared_path, prepare_targets(Platform(root), state))
                prepared = json.loads(prepared_path.read_text())
                summary = status["states"].setdefault(
                    state,
                    {
                        "phases": [],
                        "targets": len(prepared["targets"]),
                        "gaps": len(prepared["gaps"]),
                    },
                )
                summary["state"] = "running"
                targets = prepared["targets"]
                if not targets:
                    summary["state"] = "no_eligible_targets"
                    save()
                    continue
                groups = [targets[:5]] + [targets[i : i + 25] for i in range(5, len(targets), 25)]
                for index, group in enumerate(groups):
                    check()
                    identifier = f"{plan['campaign_id']}-{state.lower()}-b{index:02d}"
                    path = sd / (f"b{index:02d}.json")
                    if not path.exists():
                        atomic_json(
                            path,
                            field_config(
                                state,
                                group,
                                campaign_id=identifier,
                                directory_stores=prepared["directory_stores"],
                                pilot=index == 0,
                            ),
                        )
                    config = json.loads(path.read_text())
                    fields.validate(config, Platform(root))
                    status["active_run"] = identifier
                    save()
                    result = child(path, config)
                    summary["phases"] = [
                        p for p in summary["phases"] if p["campaign_id"] != identifier
                    ]
                    summary["phases"].append(
                        {
                            "campaign_id": identifier,
                            "state": result["state"],
                            "passes": result.get("passes", {}),
                        }
                    )
                    if result["state"] == "paused_budget":
                        status["state"] = "paused_budget"
                        save()
                        return status
                    passes = result.get("passes", {})
                    published = sum(
                        p.get("counts", {}).get("published", 0) for p in passes.values()
                    )
                    if (
                        result["state"] not in {"finished", "finished_with_holds"}
                        or index == 0
                        and published == 0
                    ):
                        summary.update(
                            state="held_after_pilot",
                            reason="pilot_or_child_requires_review",
                            unattempted_after_pilot=sum(len(g) for g in groups[index + 1 :]),
                        )
                        break
                    save()
                if summary["state"] == "running":
                    summary["state"] = (
                        "finished_with_holds"
                        if prepared["gaps"]
                        or any(p["state"] == "finished_with_holds" for p in summary["phases"])
                        else "finished"
                    )
                save()
            status.update(
                state="finished_with_holds"
                if any(s["state"] != "finished" for s in status["states"].values())
                else "finished",
                active=None,
                active_run=None,
            )
        except (OSError, ValueError, AssertionError) as error:
            status.update(
                state="stopped"
                if str(error) == "operator_stop_or_deadline"
                else "held_requires_review",
                error_type=type(error).__name__,
                active=None,
            )
        save()
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--run", action="store_true")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())
    states = validate_plan(plan)
    if not a.run:
        print(
            json.dumps(
                {
                    "state": "staged",
                    "states": states,
                    "batches": plan["batches"],
                    "source_requests": 0,
                    "paid_calls": 0,
                }
            )
        )
        return
    result = run(plan, a.data_dir, resume=a.resume)
    print(json.dumps(result))
    if result["state"] not in {"finished", "finished_with_holds"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
