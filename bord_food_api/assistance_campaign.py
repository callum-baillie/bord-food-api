"""Durable food-assistance refresh/enrichment phase after supermarket campaigns."""

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

from .assistance import duplicate_candidates, validate_states
from .assistance_crawl import crawl_target, target_plan
from .platform import Platform, atomic_json
from .runtime import heavy_lock, plan, worker_once
from .settings import load_policy

SOURCES = frozenset({"feed_america", "osm_food_assistance", "community_food_assistance"})


def supermarket_gate(root, campaign_ids):
    """Check the whole controller, not the initial runner's premature state summaries."""
    if not campaign_ids:
        return {"ready": False, "reason": "explicit_supermarket_dependency_required"}
    for identifier in campaign_ids:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier):
            raise ValueError("invalid_supermarket_dependency")
        path = Path(root) / "crawl-campaigns" / identifier / "status.json"
        if not path.exists():
            return {"ready": False, "reason": "waiting_for_supermarkets", "campaign": identifier}
        status = json.loads(path.read_text())
        if (
            status.get("state") not in {"finished", "finished_with_holds"}
            or status.get("active_run")
            or status.get("active")
        ):
            return {
                "ready": False,
                "reason": "waiting_for_supermarkets",
                "campaign": identifier,
                "supermarket_state": status.get("state"),
            }
        for summary in status.get("states", {}).values():
            if summary.get("state") in {"held_after_pilot", "no_eligible_targets"}:
                continue
            targets = summary.get("targets", 0)
            expected = int(targets > 0) + (max(0, targets - 5) + 24) // 25
            phases = summary.get("phases", [])
            if len(phases) != expected or any(
                p.get("state") not in {"finished", "finished_with_holds"} for p in phases
            ):
                return {
                    "ready": False,
                    "reason": "incomplete_supermarket_chunks",
                    "campaign": identifier,
                }
    return {"ready": True, "reason": "supermarket_passes_terminal"}


def run_pass(
    settings,
    config,
    *,
    acquisition=None,
    crawl=crawl_target,
    clock=time.time,
    cancellation=None,
    reviewer_factory=None,
):
    """One due-source pass and a bounded enrichment chunk. Caller holds campaign lock."""

    def check():
        if (cancellation is not None and cancellation.is_set()) or (
            Path(settings.data_dir) / "crawl-campaigns" / config["campaign_id"] / "STOP"
        ).exists():
            raise ValueError("assistance_operator_stopped")

    check()
    states = validate_states(config["states"])
    gate = supermarket_gate(settings.data_dir, config["after_campaigns"])
    if not gate["ready"]:
        return {
            "state": "waiting_for_supermarkets",
            "dependency": gate,
            "source_requests": 0,
            "paid_calls": 0,
        }
    maximum = config.get("max_operator_pages", 25)
    if type(maximum) is not int or not 0 <= maximum <= 50:
        raise ValueError("assistance_operator_page_budget_invalid")
    policy = load_policy(settings)
    if any(p["enabled"] and name not in SOURCES for name, p in policy["sources"].items()):
        raise ValueError("assistance_worker_must_not_activate_other_sources")
    for source in SOURCES:
        source_config = policy["sources"][source]
        if source_config["enabled"]:
            source_states = (
                {p["state"] for p in source_config.get("profiles", [])}
                if source == "community_food_assistance"
                else set(source_config.get("states", ["IA"]))
            )
            if source_states - set(states):
                raise ValueError("assistance_source_state_scope_exceeds_campaign")
    p = Platform(settings.data_dir)

    def model_ledger():
        path = p.root / "control/jev-crawl-budget.sqlite"
        if not path.exists():
            return {"reservations": 0, "reserved_nanousd": 0, "answered": 0}
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            count, reserved, answered = db.execute(
                "SELECT count(*),coalesce(sum(reserved),0),coalesce(sum(state='answered'),0) FROM decisions WHERE campaign GLOB ?",
                (config["campaign_id"] + "-*",),
            ).fetchone()
        return {"reservations": count, "reserved_nanousd": reserved, "answered": answered}

    ledger_before = model_ledger()
    outcomes = []
    for source in sorted(SOURCES):
        check()
        due = next(row for row in plan(settings, source=source) if row["source"] == source)
        with p.control.connect() as db:
            pending = db.execute(
                "SELECT id FROM jobs WHERE source=? AND operation='sync' AND state IN ('queued','retry_wait') AND due<=? ORDER BY due LIMIT 1",
                (source, clock()),
            ).fetchone()
        job_id = pending[0] if pending else None
        if due["due"]:
            version = hashlib.sha256(
                json.dumps(policy["sources"][source], sort_keys=True).encode()
            ).hexdigest()[:16]
            job_id = p.control.enqueue(source, "all", version=version)
        if job_id and policy["sources"][source]["enabled"]:
            outcomes.extend(
                worker_once(
                    settings,
                    batch_size=1,
                    acquisition=acquisition,
                    job_id=job_id,
                    schedule_due=False,
                    cancellation=cancellation,
                )
            )
    # A phase can enrich retained last-good rows even if one source failed; status is explicit.
    prepared = target_plan(p, states)
    directory = p.root / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "targets.json", prepared)
    duplicate_review = duplicate_candidates(
        [
            r
            for dataset in ("assistance_site", "osm_assistance_site")
            for r in p.iter_records(dataset)
            if r.get("address", {}).get("region") in states
        ]
    )
    atomic_json(directory / "duplicate-review.json", duplicate_review)
    completed = []
    if config.get("operator_crawl_enabled") is True:
        if config.get("operator_contact") != "hello@foldlab.app" and not config.get(
            "operator_contact"
        ):
            raise ValueError("assistance_operator_contact_required")
        selected = []
        for target in prepared["targets"]:
            from .crawl_history import prior_holds

            if prior_holds(p.root, target):
                continue
            source = (
                "osm_assistance_operator" if target["dataset"] == "osm" else "assistance_operator"
            )
            evidence = p.get_by_source(
                "osm_assistance_evidence" if target["dataset"] == "osm" else "assistance_evidence",
                source,
                target["site_id"],
            )
            latest = max(
                (a.get("checked_at", 0) for a in (evidence or {}).get("assertions", {}).values()),
                default=0,
            )
            if clock() - latest >= 7 * 86400:
                selected.append(target)
        for index, target in enumerate(selected[:maximum]):
            check()
            child_id = config["campaign_id"] + "-" + str(int(clock())) + "-" + str(index)
            with heavy_lock(p.root):
                completed.append(
                    crawl(
                        p,
                        target,
                        {
                            "campaign_id": child_id,
                            "mode": policy["network"]["mode"],
                            "global_enabled": True,
                            "adapter_enabled": True,
                            "source_authorized": True,
                            "owner_public_robots_authorized": True,
                            "robots_reviewed": True,
                            "contact": config["operator_contact"],
                            "min_spacing": 45,
                            "spacing_jitter_seconds": 45,
                            "max_pages_day": 500,
                            "max_pages_run": 2,
                            "max_run_seconds": 900,
                            "reviewed_operator_hosts": config.get("reviewed_operator_hosts", []),
                        },
                        external_check=check,
                        review=reviewer_factory(child_id) if reviewer_factory is not None else None,
                    )
                )
            if completed[-1]["state"] == "paused_budget":
                break
    return {
        "state": "finished_with_holds"
        if prepared["gaps"]
        or any(r["state"] not in {"succeeded", "finished"} for r in outcomes + completed)
        else "finished",
        "source_jobs": outcomes,
        "operator_runs": completed,
        "prepared_targets": len(prepared["targets"]),
        "gaps": len(prepared["gaps"]),
        "duplicate_candidates": len(duplicate_review),
        "jev_ledger_before": ledger_before,
        "jev_ledger_after": model_ledger(),
        "actual_billing": "not_measured",
        "supermarket_dependency": gate,
        "updated_at": clock(),
    }
