"""Explicit, durable state branch queue; default inspection makes no source/model calls.

One worker, one shared frontier/model ledger. Daily limits defer pending branches;
access failures hold a host, budget exhaustion pauses the queue without declaring completion.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import signal
import sqlite3
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from bord_food_api.crawl_evidence import collect_evidence
from bord_food_api.crawl_history import capture_snapshot, exception_details, prior_holds
from bord_food_api.crawl_runtime import run_map_discovery
from bord_food_api.crawlers import CrawlBlocked
from bord_food_api.nationwide import JURISDICTIONS, PROFILE
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import Lease, heavy_lock
from bord_food_api.store_enrichment import publish_crawl_evidence
from bord_food_api.transport import PolicyError, TransportError

spec = importlib.util.spec_from_file_location(
    "state_campaign", Path(__file__).with_name("run-iowa-crawl.py")
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
reviewed = campaign.reviewed
SOURCE = campaign.SOURCE


class Stopped(RuntimeError):
    pass


def validate(config, platform):
    if (
        config.get("activation_enabled") is not True
        or config.get("state") not in JURISDICTIONS
        or config.get("collection_profile") != PROFILE
        or config.get("capture_product_inventory") is not False
        or config.get("capture_product_catalog") is not False
    ):
        raise ValueError("explicit_state_store_layout_activation_required")
    targets = config.get("targets", [])
    decision = config["decisions"]
    if (
        not 1 <= len(targets) <= 500
        or len({t["url"] for t in targets}) != len(targets)
        or len({t["store_id"] for t in targets}) != len(targets)
        or type(config.get("duration_seconds")) is not int
        or not 60 <= config["duration_seconds"] <= 7 * 86400
        or type(decision.get("max_calls")) is not int
        or not 1 <= decision["max_calls"] <= 1000
        or type(decision.get("budget_nanousd")) is not int
        or not 0 < decision["budget_nanousd"] <= reviewed.GLOBAL_CAP_NANOUSD
    ):
        raise ValueError("statewide_limits_invalid")
    # Preserve all original per-request/branch gates. Campaign-wide budgets are
    # independently bounded above; no per-page transport limits are enlarged.
    for offset in range(0, len(targets), 25):
        campaign.validate(
            {
                **config,
                "targets": targets[offset : offset + 25],
                "decisions": {
                    **decision,
                    "max_calls": min(100, decision["max_calls"]),
                    "budget_nanousd": min(1_000_000_000, decision["budget_nanousd"]),
                },
            },
            platform,
        )
    if any(s["crawl"]["min_spacing"] < 45 for s in config["scopes"].values()):
        raise ValueError("statewide_spacing_too_short")
    return targets


def budget_room(root, config, needed=2):
    path = Path(root) / "control/jev-crawl-budget.sqlite"
    total = used = calls = 0
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            total = db.execute("SELECT coalesce(sum(reserved),0) FROM decisions").fetchone()[0]
            used, calls = db.execute(
                "SELECT coalesce(sum(reserved),0),count(*) FROM decisions WHERE campaign=?",
                (config["campaign_id"],),
            ).fetchone()
    available = min(
        config["decisions"].get("global_budget_nanousd", reviewed.GLOBAL_CAP_NANOUSD)
        - reviewed.PRIOR_PILOT_NANOUSD
        - total,
        config["decisions"]["budget_nanousd"] - used,
    )
    return {
        "can_start": available >= needed * reviewed.RESERVATION_NANOUSD
        and calls + needed <= config["decisions"]["max_calls"],
        "total_reserved_nanousd": total,
        "campaign_reserved_nanousd": used,
        "campaign_calls": calls,
        "remaining_nanousd": max(0, available),
    }


def host_due(root, host, policy, now):
    """No networking or paid decisions while a host lacks daily request capacity."""
    path = Path(root) / "control/crawl_frontier.sqlite"
    if not path.exists():
        return now
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT day,requests,last_request FROM crawl_hosts WHERE host=?", (host,)
        ).fetchone()
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        backoff = (
            db.execute("SELECT until FROM crawl_host_backoff WHERE host=?", (host,)).fetchone()
            if "crawl_host_backoff" in tables
            else None
        )
        if backoff and backoff[0] > now:
            return backoff[0]
        cached = (
            db.execute(
                "SELECT body,status,expires FROM crawl_robots WHERE host=?", (host,)
            ).fetchone()
            if "crawl_robots" in tables
            else None
        )
    fresh = cached and cached[2] > now
    needed = 1 if fresh else 2
    if row and row[0] == int(now // 86400) and row[1] + needed > policy["max_pages_day"]:
        return (int(now // 86400) + 1) * 86400 + 60
    spacing = policy["min_spacing"]
    if fresh and cached[1] == 200:
        parser = RobotFileParser("https://" + host + "/robots.txt")
        parser.parse(cached[0].splitlines())
        agent = "BordFoodCatalog/1.0 (+mailto:" + policy["contact"] + ")"
        rate = parser.request_rate(agent)
        spacing = max(
            spacing,
            parser.crawl_delay(agent) or 0,
            rate.seconds / rate.requests if rate and rate.requests else 0,
        )
    return max(now, row[2] + spacing) if row else now


def _snapshot(status, path, clock, config=None):
    status["counts"] = dict(Counter(t["state"] for t in status["targets"].values()))
    status["updated_at"] = clock()
    atomic_json(path, status)
    if config is not None:
        capture_snapshot(path.parent.parent.parent, status, config)


@contextmanager
def controller_lock(directory):
    with (directory / "controller.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def amend_pacing(previous, config, root, *, clock=time.time):
    """Explicit offline pacing amendment; keep outcomes, counters and spend intact.

    The controller lock excludes a live worker. Only request pacing fields may
    change; a new target list, budget or campaign needs separate authorization.
    """
    validate(config, Platform(root))
    allowed = {"max_pages_day", "min_spacing", "spacing_jitter_seconds"}

    def without_pacing(value):
        result = json.loads(json.dumps(value))
        for scope in result["scopes"].values():
            for key in allowed:
                scope["crawl"].pop(key, None)
        return result

    if without_pacing(previous) != without_pacing(config):
        raise ValueError("only_pacing_amendments_allowed")
    directory = Path(root) / "crawl-campaigns" / config["campaign_id"]
    with controller_lock(directory):
        path = directory / "status.json"
        status = json.loads(path.read_text())
        old_hash = hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()
        new_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        if status["config_sha256"] != old_hash:
            raise ValueError("amendment_previous_config_mismatch")
        if status.get("active") or any(
            item["state"] == "running" for item in status["targets"].values()
        ):
            raise ValueError("amendment_requires_idle_worker")
        status.setdefault("config_revisions", []).append(
            {
                "previous_sha256": old_hash,
                "config_sha256": new_hash,
                "changed_at": clock(),
                "reason": "operator_pacing_update",
                "policies": {
                    host: {key: scope["crawl"].get(key, 0) for key in sorted(allowed)}
                    for host, scope in config["scopes"].items()
                },
            }
        )
        status.update(config_sha256=new_hash, state="stopped", active=None, next_due=None)
        _snapshot(status, path, clock, config)
        return status


@contextmanager
def worker_slot(root, check, sleep, waiting=lambda: None):
    while True:
        slot = heavy_lock(root)
        try:
            slot.__enter__()
            break
        except BlockingIOError:
            check()
            waiting()
            sleep(5)
    try:
        yield
    finally:
        slot.__exit__(None, None, None)


def run(
    config,
    root,
    *,
    resume=False,
    judge_factory=reviewed.Judge,
    discover=run_map_discovery,
    clock=time.time,
    sleep=time.sleep,
    install_signals=True,
    external_check=None,
):
    platform = Platform(root)
    targets = validate(config, platform)
    directory = Path(root) / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "status.json"
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    stopped = [False]
    if install_signals:
        signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
        signal.signal(signal.SIGINT, lambda *_: stopped.__setitem__(0, True))
    with controller_lock(directory):
        if path.exists():
            if not resume:
                raise ValueError("explicit_resume_required")
            status = json.loads(path.read_text())
            if status["config_sha256"] != fingerprint:
                raise ValueError("resume_config_changed")
            for item in status["targets"].values():
                if item["state"] == "running":
                    item["state"] = "interrupted_requires_review"
        else:
            status = {
                "campaign_id": config["campaign_id"],
                "state": "starting",
                "started_at": clock(),
                "config_sha256": fingerprint,
                "active": None,
                "last_host": None,
                "blocked_hosts": dict(config.get("blocked_hosts", {})),
                "directory_stores": config.get("directory_stores"),
                "missing_branch_urls": config.get("missing_branch_urls", 0),
                "targets": {
                    t["store_id"]: {
                        "state": "pending",
                        "host": urlsplit(t["url"]).hostname,
                        "network_attempted": False,
                    }
                    for t in targets
                },
            }
            if config.get("field_focus") is True:
                for gap in config.get("coverage_gaps", []):
                    status["targets"][gap["store_id"]] = {
                        **gap,
                        "state": "missing_branch_url",
                        "network_attempted": False,
                    }
        by_id = {t["store_id"]: t for t in targets}
        judge = judge_factory(root, {**config["decisions"], "campaign_id": config["campaign_id"]})

        def check(require_source=True):
            if external_check:
                external_check()
            if (
                stopped[0]
                or (directory / "STOP").exists()
                or (require_source and not platform.control.enabled(SOURCE))
            ):
                raise Stopped("operator_stop")
            if clock() - status["started_at"] > config["duration_seconds"]:
                raise Stopped("campaign_deadline")

        try:
            status.update(state="starting", phase="recovering")
            _snapshot(status, path, clock, config)
            with worker_slot(root, lambda: check(False), sleep):
                check(False)
                platform.recover()
                platform.control.set_source(SOURCE, True)
            while True:
                check()
                for key, item in status["targets"].items():
                    if item["state"] == "pending" and item["host"] in status["blocked_hosts"]:
                        item.update(
                            state="host_blocked", reason=status["blocked_hosts"][item["host"]]
                        )
                    elif item["state"] == "pending" and prior_holds(root, by_id[key]):
                        item.update(
                            state="prior_history_hold",
                            reason="prior_history_hold",
                            network_attempted=False,
                        )
                pending = [
                    (key, item)
                    for key, item in status["targets"].items()
                    if item["state"] == "pending"
                ]
                if not pending:
                    status.update(
                        state="finished_with_holds"
                        if any(i["state"] != "published" for i in status["targets"].values())
                        or status["missing_branch_urls"]
                        else "finished",
                        completed_at=clock(),
                        active=None,
                    )
                    break
                status["budget"] = budget_room(
                    root, config, needed=0 if config.get("field_focus") else 2
                )
                if config.get("field_focus") is True:
                    # The field judge holds ambiguous pages when its model budget
                    # is exhausted; deterministic exact-address pages may continue.
                    status["budget"]["can_start"] = True
                if not status["budget"]["can_start"]:
                    status.update(state="paused_budget", active=None)
                    break
                hosts = sorted({item["host"] for _, item in pending})
                if status["last_host"] in hosts:
                    position = hosts.index(status["last_host"]) + 1
                    hosts = hosts[position:] + hosts[:position]
                due = {
                    host: host_due(root, host, config["scopes"][host]["crawl"], clock())
                    for host in hosts
                }
                host = next((h for h in hosts if due[h] <= clock()), None)
                if host is None:
                    status.update(
                        state="waiting_host_limits", active=None, next_due=min(due.values())
                    )
                    _snapshot(status, path, clock, config)
                    sleep(min(5, max(0.1, status["next_due"] - clock())))
                    continue
                key, item = next((key, item) for key, item in pending if item["host"] == host)
                target = by_id[key]
                # Recheck source identity/address before spending or fetching.
                try:
                    campaign.validate(
                        {
                            **config,
                            "targets": [target],
                            "decisions": {
                                **config["decisions"],
                                "max_calls": 2,
                                "budget_nanousd": 20_000_000,
                            },
                        },
                        platform,
                    )
                except ValueError:
                    item.update(
                        state="review_required",
                        reason="branch_snapshot_changed",
                        stage="identity",
                        finished_at=clock(),
                    )
                    _snapshot(status, path, clock, config)
                    continue
                status.update(state="running", active=key, last_host=host, phase="jev_before_fetch")
                item.update(
                    state="running",
                    stage="before_fetch",
                    attempt_started_at=clock(),
                    network_attempted=False,
                )
                _snapshot(status, path, clock, config)

                def waiting_for_worker():
                    status.update(state="waiting_worker", phase="waiting_worker")
                    _snapshot(status, path, clock, config)

                with worker_slot(root, check, sleep, waiting_for_worker):
                    check()
                    try:
                        judge.before(target)
                    except reviewed.ReviewRequired:
                        item.update(
                            state="review_required",
                            reason="pre_fetch_confidence",
                            finished_at=clock(),
                        )
                        _snapshot(status, path, clock, config)
                        continue
                    job_id = platform.control.enqueue(
                        SOURCE,
                        host,
                        operation="operator_discover_map",
                        version=config["campaign_id"] + ":" + key,
                    )
                    job = platform.control.claim(config["campaign_id"], ttl=120, job_id=job_id)
                    if not job:
                        raise ValueError("job_claim_failed")
                    item["job_id"] = job_id
                    with Lease(platform.control, job, 120, 20) as lease:
                        lease.policy_check = check

                        captured_fields = []

                        def evidence_sink(
                            html, branch_target, captured=captured_fields, attempt=item
                        ):
                            evidence = collect_evidence(html, branch_target, retrieved_at=clock())
                            captured.append(evidence)
                            evidence["visible_text_excerpt"] = reviewed.review_text(html)
                            evidence["text_excerpt_limit"] = 4500
                            evidence_dir = directory / "evidence"
                            evidence_dir.mkdir(exist_ok=True)
                            atomic_json(
                                evidence_dir
                                / (
                                    hashlib.sha256(branch_target["url"].encode()).hexdigest()
                                    + ".json"
                                ),
                                evidence,
                            )
                            attempt["field_observations"] = {
                                "branch_match": evidence["branch_match"],
                                "valid_fields": sorted(
                                    {
                                        r["field"]
                                        for r in evidence["field_assertions"]
                                        if r["validation"] == "valid"
                                        and r["branch_match"] == "exact_address"
                                    }
                                ),
                                "parser_version": evidence["parser_version"],
                            }

                        crawl = {
                            **config["scopes"][host]["crawl"],
                            "approved_targets": [target],
                            "_check": lease.check,
                            "_evidence_sink": evidence_sink,
                            "_fields_only": config.get("field_focus") is True,
                        }
                        status["phase"] = "robots_and_branch_fetch"
                        _snapshot(status, path, clock, config)

                        def transport_attempt(url, attempt=item):
                            attempt.update(
                                network_attempted=True,
                                stage="robots" if url.endswith("/robots.txt") else "branch_page",
                            )
                            _snapshot(status, path, clock, config)

                        try:
                            result = discover(
                                platform,
                                job,
                                crawl,
                                transport_factory=reviewed.reviewed_transport(
                                    judge, target, on_request=transport_attempt
                                ),
                                clock=clock,
                                sleep=sleep,
                            )
                            if captured_fields:
                                try:
                                    fields = publish_crawl_evidence(
                                        platform, captured_fields[-1], now=clock(), fence=job
                                    )
                                    item["field_enrichment"] = {
                                        "state": "published",
                                        "changed": fields["changed"],
                                    }
                                except ValueError:
                                    item["field_enrichment"] = {
                                        "state": "retained_for_retry",
                                        "reason": "field_publication_requires_review",
                                    }
                            platform.control.finish(job)
                            item.update(
                                state="published",
                                map_records=result["map_records"],
                                stage="publication",
                                finished_at=clock(),
                            )
                        except reviewed.ReviewRequired:
                            platform.control.finish(job, reason="machine_review_required")
                            item.update(
                                state="review_required",
                                reason="page_review",
                                stage="page_review",
                                finished_at=clock(),
                            )
                        except (CrawlBlocked, TransportError, PolicyError, OSError) as error:
                            platform.control.finish(
                                job, state="failed", reason="host_access_or_policy_block"
                            )
                            status["blocked_hosts"][host] = type(error).__name__
                            item.update(
                                state="host_blocked",
                                finished_at=clock(),
                                **exception_details(error),
                            )
                        except (ValueError, TypeError, KeyError, RecursionError) as error:
                            if not config.get("field_focus") or str(error).startswith("decision_"):
                                raise
                            platform.control.finish(
                                job, state="failed", reason="field_parser_requires_review"
                            )
                            item.update(
                                state="review_required",
                                reason="field_parser_error",
                                stage="page_review",
                                finished_at=clock(),
                                error_type=type(error).__name__,
                                error_frames=[
                                    {
                                        "file": Path(f.filename).name,
                                        "line": f.lineno,
                                        "function": f.name,
                                    }
                                    for f in traceback.extract_tb(error.__traceback__)[-8:]
                                ],
                            )
                        except BaseException:
                            try:
                                platform.control.finish(
                                    job, state="failed", reason="statewide_campaign_interrupted"
                                )
                            except ValueError:
                                pass  # Paused or fenced work cannot be finished by this worker.
                            item.update(
                                state="interrupted_requires_review",
                                reason="interrupted",
                                finished_at=clock(),
                            )
                            raise
                _snapshot(status, path, clock, config)
        except Stopped:
            status.update(state="stopped", active=None)
        except BaseException as error:  # noqa: BLE001 - never log provider exceptions or secrets
            if status.get("active"):
                item = status["targets"][status["active"]]
                if item["state"] == "running":
                    item["state"] = "interrupted_requires_review"
            status.update(
                state="paused_error",
                error_type=type(error).__name__,
                active=None,
                error_frames=[
                    {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                    for f in traceback.extract_tb(error.__traceback__)[-8:]
                ],
            )
        finally:
            platform.control.set_source(SOURCE, False)
            status["budget"] = budget_room(root, config)
            _snapshot(status, path, clock, config)
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--amend-pacing-from", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.amend_pacing_from:
        if args.run or args.resume:
            parser.error("pacing amendment is offline; resume in a separate invocation")
        result = amend_pacing(json.loads(args.amend_pacing_from.read_text()), config, args.data_dir)
        print(json.dumps({"state": result["state"], "config_sha256": result["config_sha256"]}))
        return
    if not args.run:
        targets = validate(config, Platform(args.data_dir))
        print(
            json.dumps(
                {
                    "network": False,
                    "targets": len(targets),
                    "campaign_id": config["campaign_id"],
                    "budget": budget_room(args.data_dir, config),
                    "blocked_hosts": config.get("blocked_hosts", {}),
                }
            )
        )
    else:
        result = run(config, args.data_dir, resume=args.resume)
        print(json.dumps({k: result.get(k) for k in ("campaign_id", "state", "counts", "budget")}))
        if result["state"] not in ("finished", "finished_with_holds", "paused_budget"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
