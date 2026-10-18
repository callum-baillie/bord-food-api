"""Durable coalescing scheduler and one-heavy-job worker role."""

import fcntl
import hashlib
import json
import logging
import os
import random
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .control import Control
from .settings import load_policy
from .transport import PolicyError, Transport, TransportError

LOG = logging.getLogger(__name__)


class WorkerStopping(PolicyError):
    """Cooperative shutdown revokes the worker's in-flight publication fence."""


def local_sources(directory):
    root = Path(directory).resolve()
    return sorted(
        path
        for path in root.glob("*")
        if path.is_file()
        and path.resolve().is_relative_to(root)
        and not path.is_symlink()
        and path.suffix.lower() in {".json", ".zip"}
        and not path.name.endswith(".source.json")
    )


def apply_rights_policy(settings, control):
    """Persist retention denials/expiry; configuration never silently clears a denial."""
    policy = load_policy(settings)
    denied = control.denied_sources()
    with control.connect() as db:
        existing_actions = {
            (row["source"], row["action"]): bool(row["allowed"])
            for row in db.execute("SELECT * FROM policy_actions")
        }
    for source, config in policy["sources"].items():
        retention = config.get("retention_until")
        for action in ("can_display", "can_redistribute"):
            if action in config:
                allowed = config[action] in (True, "allow")
                if existing_actions.get((source, action)) != allowed:
                    control.set_action(source, action, allowed)
        restrict = config.get("can_retain", True) is False
        if restrict or retention is not None:
            with control.connect() as db:
                existing = db.execute(
                    "SELECT denied,retention_until FROM rights WHERE source=?", (source,)
                ).fetchone()
            effective_denial = restrict or source in denied
            if (
                existing is None
                or bool(existing["denied"]) != effective_denial
                or existing["retention_until"] != retention
            ):
                control.restrict_source(
                    source,
                    denied=effective_denial,
                    retention_until=retention,
                    reason="configured_rights_policy",
                )
    return policy


def effective_sources(settings, control=None):
    policy = (
        apply_rights_policy(settings, control) if control is not None else load_policy(settings)
    )
    denied = control.denied_sources() if control is not None else set()
    for source, config in policy["sources"].items():
        config["enabled"] = (
            config["enabled"]
            and all(
                config.get(action, True) in (True, "allow")
                for action in ("can_fetch", "can_store_raw", "can_store_normalized")
            )
            and source not in denied
            and (control is None or control.enabled(source))
        )
    return policy


def plan(settings, *, source=None, now=None):
    """No URL discovery and no network I/O, including when called on an empty install."""
    control = Control(settings.data_dir)
    policy = effective_sources(settings, control)
    now = time.time() if now is None else now
    with control.connect() as db:
        installation = db.execute("SELECT id FROM installation").fetchone()[0]
        jobs = [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY due")]
        states = [dict(row) for row in db.execute("SELECT * FROM source_state")]
    result = []
    for name, config in policy["sources"].items():
        if source and source != name:
            continue
        history = [job for job in jobs if job["source"] == name]
        active = [
            job
            for job in history
            if job["state"]
            in {"queued", "leased", "running", "validating", "publishing", "retry_wait"}
        ]
        # Persisted terminal job due time coalesces all missed intervals into one check.
        stagger = (
            int(hashlib.sha256(f"{installation}:{name}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        )
        interval = config["interval_seconds"] * (1 + 0.15 * stagger)
        next_due = max((job["due"] for job in history), default=0) + (interval if history else 0)
        published = [
            state
            for state in states
            if state["source"] == name or (name == "usda_fdc" and state["source"] == "local_usda")
        ]
        local_pin = any(
            state["source"] == "local_usda"
            or ((json.loads(state["cursor"]) or {}).get("manual") if state.get("cursor") else False)
            for state in published
        )
        manual_block = (
            name == "usda_fdc"
            and local_pin
            and not config.get("allow_managed_refresh_after_local_import", False)
        )
        allowed = (
            config["enabled"]
            and policy["scheduler"]["enabled"]
            and policy["bootstrap"]["mode"] == "automatic"
            and not manual_block
        )
        result.append(
            {
                "source": name,
                "enabled": bool(allowed),
                "partition": "all",
                "due": bool(allowed and not active and next_due <= now),
                "next_due": next_due or None,
                "active_jobs": len(active),
                "would_discover": bool(allowed),
                "would_download": bool(allowed),
                "would_crawl": False,
                "reason": "local_import_pinned"
                if manual_block
                else (None if allowed else "disabled_by_policy"),
            }
        )
    return result


def schedule(settings, *, now=None):
    control = Control(settings.data_dir)
    rows = plan(settings, now=now)
    policy = load_policy(settings)
    enqueued = []
    for row in rows:
        if row["due"]:
            config = policy["sources"][row["source"]]
            version = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
            enqueued.append(control.enqueue(row["source"], "all", version=version, due=now))
    return enqueued


@contextmanager
def heavy_lock(data_dir):
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "worker.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Lease:
    def __init__(self, control, job, ttl, interval):
        self.control, self.job = control, job
        self.ttl, self.interval = ttl, min(interval, ttl / 3)
        self.stop = threading.Event()
        self.error = None
        self.policy_check = lambda: None
        self.cancellation = None

    def _loop(self):
        while not self.stop.wait(self.interval):
            try:
                self.policy_check()
                self.control.heartbeat(self.job, ttl=self.ttl)
                _touch_worker(self.control.root)
            except Exception as error:  # noqa: BLE001 - Background failures revoke the publication fence.
                self.error = error
                return

    def __enter__(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def check(self):
        if self.error:
            raise self.error
        self.policy_check()
        self.control.check_fence(self.job)

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)


def import_usda(
    settings,
    paths,
    *,
    platform=None,
    fence=None,
    local=True,
    release="",
    cursor=None,
    partition="all",
    parser_version="1",
):
    """Build a private USDA object and route replacement through the common publisher."""
    import tempfile

    from .importer import build_catalog
    from .platform import Platform

    platform = platform or Platform(settings.data_dir)
    apply_rights_policy(settings, platform.control)
    if platform.control.denied_sources() & {"usda_fdc", "local_usda"}:
        raise PolicyError("usda_retention_denied")
    staging = Path(settings.data_dir) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="usda-", dir=staging) as directory:
        database = Path(directory) / "foods.sqlite"
        budgets = load_policy(settings)["budgets"]
        occupied = sum(
            path.stat().st_size
            for path in Path(settings.data_dir).rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        remaining = budgets["data_quota_bytes"] - occupied
        if remaining <= 0:
            raise PolicyError("installation_quota_exhausted")
        build_catalog(
            paths,
            database,
            max_staging_bytes=min(budgets.get("max_staging_bytes", remaining), remaining),
            free_space_reserve_bytes=budgets["free_space_reserve_bytes"],
        )
        return platform.publish_usda(
            database,
            release=release,
            partition=partition,
            fence=fence,
            cursor={**(cursor or {}), "manual": local},
            parser_version=parser_version,
        )


def _checkpoint(control, job, phase, *, state="running", **evidence):
    with control.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        control.check_fence(job, db)
        db.execute(
            "UPDATE jobs SET state=?,checkpoint=? WHERE id=?",
            (state, json.dumps({"phase": phase, **evidence}, sort_keys=True), job["id"]),
        )


def crawl_configuration(settings, adapter="woodmans_maps"):
    policy = load_policy(settings)
    crawler = policy["crawler"]
    if adapter not in crawler["adapters"]:
        raise ValueError("Unknown crawler adapter")
    descriptor = crawler["adapters"][adapter]
    for gate in ("enabled", "source_authorized", "terms_reviewed", "robots_reviewed"):
        if type(descriptor.get(gate)) is not bool:
            raise TypeError("Crawler activation gates must be boolean")
    config = {
        "global_enabled": bool(policy["network"]["crawl_enabled"] and crawler["enabled"]),
        "adapter_enabled": bool(adapter in crawler["adapters_enabled"] and descriptor["enabled"]),
        "source_authorized": descriptor["source_authorized"],
        "terms_reviewed": descriptor["terms_reviewed"],
        "robots_reviewed": descriptor["robots_reviewed"],
        "contact": crawler.get("operator_contact") or "",
        "allowed_host": descriptor["allowed_host"],
        "scope_prefix": descriptor.get("scope_prefix", "/store-locations/"),
        "approved_targets": descriptor.get("approved_targets", []),
        "mode": policy["network"]["mode"],
        "max_pages_run": crawler["max_pages_per_run"],
        "max_pages_day": crawler["max_pages_per_day"],
        "min_spacing": crawler["min_delay_seconds"],
        "max_bytes": crawler["max_html_bytes"],
        "robots_ttl_seconds": descriptor.get("robots_ttl_seconds", 3600),
        **{
            key: descriptor[key]
            for key in ("can_fetch", "can_store_raw", "can_store_normalized", "rights_policy_id")
            if key in descriptor
        },
    }
    if (
        config["allowed_host"] != "www.woodmans-food.com"
        or config["scope_prefix"] != "/store-locations/"
    ):
        raise ValueError("Crawler adapter targets require the reviewed official host/path")
    for name, low, high in (
        ("max_pages_run", 1, 50),
        ("max_pages_day", 1, 500),
        ("min_spacing", 5, 86400),
        ("max_bytes", 1, 2 * 1024**2),
        ("robots_ttl_seconds", 1, 86400),
    ):
        if type(config[name]) not in (int, float) or not low <= config[name] <= high:
            raise ValueError("Crawler resource limits exceed the bounded adapter policy")
    if (
        not isinstance(config["approved_targets"], list)
        or len(config["approved_targets"]) > config["max_pages_run"]
    ):
        raise ValueError("Crawler approved targets exceed per-run limits")
    return config


def crawl_plan(settings, adapter="woodmans_maps", *, control=None):
    config = crawl_configuration(settings, adapter)
    reasons = [
        gate
        for gate in (
            "global_enabled",
            "adapter_enabled",
            "source_authorized",
            "terms_reviewed",
            "robots_reviewed",
        )
        if not config[gate]
    ]
    if config["mode"] == "offline":
        reasons.append("offline")
    for action in ("can_fetch", "can_store_normalized"):
        if config.get(action, True) not in (True, "allow"):
            reasons.append(action + "_denied")
    if not config["approved_targets"]:
        reasons.append("approved_targets_missing")
    contact = config["contact"]
    if "@" not in contact or any(
        word in contact.casefold() for word in ("example.", "placeholder", "changeme", ".test")
    ):
        reasons.append("operator_contact_missing")
    if control is not None:
        if not control.enabled(adapter):
            reasons.append("source_paused")
        if adapter in control.denied_sources():
            reasons.append("source_retention_denied")
        if adapter in control.hidden_sources("can_fetch"):
            reasons.append("source_fetch_denied")
    allowed = not reasons
    return {
        "adapter": adapter,
        "allowed": allowed,
        "blocked_reasons": reasons,
        "targets": len(config["approved_targets"]),
        "would_check_robots": allowed,
        "would_crawl": allowed,
        "would_download_assets": False,
        "would_download": False,
        "would_discover": False,
    }


def execute_job(settings, job, platform, lease, *, acquisition=None):
    if job["operation"] == "discover_map":
        from .crawl_runtime import run_map_discovery

        def check():
            platform.control.check_fence(job)
            if lease.cancellation is not None and lease.cancellation.is_set():
                platform.control.finish(job, state="cancelled", reason="worker_stopped")
                raise WorkerStopping("worker_stopped")
            if not crawl_plan(settings, job["source"], control=platform.control)["allowed"]:
                raise PolicyError("crawler_activation_blocked")

        lease.policy_check = check
        check()
        config = crawl_configuration(settings, job["source"])
        config["_check"] = lease.check
        _checkpoint(platform.control, job, "discovering_map")
        result = run_map_discovery(platform, job, config)
        return {
            "partitions": 1,
            "changed": result.get("changed", 0),
            "unchanged": result.get("unchanged", 0),
            "no_change": result.get("no_change", False),
        }

    from .sources import acquire_source

    policy = effective_sources(settings, platform.control)
    config = policy["sources"].get(job["source"], {})
    if not config.get("enabled"):
        raise PolicyError("source_disabled_by_policy")

    def policy_check():
        if lease.cancellation is not None and lease.cancellation.is_set():
            platform.control.finish(job, state="cancelled", reason="worker_stopped")
            raise WorkerStopping("worker_stopped")
        if not effective_sources(settings, platform.control)["sources"][job["source"]]["enabled"]:
            platform.control.set_source(job["source"], False)
            raise PolicyError("source_disabled_by_policy")

    lease.policy_check = policy_check
    lease.check()
    config["_check"] = lease.check
    config["data_root"] = str(settings.data_dir)
    transport = Transport(config)
    directory = Path(settings.data_dir) / "downloads" / job["source"]
    with platform.control.connect() as db:
        states = db.execute(
            "SELECT partition,cursor FROM source_state WHERE source=? ORDER BY checked_at DESC",
            (job["source"],),
        ).fetchall()
    cursors = {
        state["partition"]: json.loads(state["cursor"]) if state["cursor"] else None
        for state in states
    }
    cursor = (
        cursors.get("products")
        if job["source"] == "open_food_facts"
        else (next(iter(cursors.values()), None) if len(cursors) <= 1 else {"partitions": cursors})
    )
    _checkpoint(platform.control, job, "discovering")
    acquired = (acquisition or acquire_source)(job["source"], config, transport, directory, cursor)
    count = changed = unchanged = 0
    for scope in acquired:
        lease.check()
        if scope.get("error"):
            raise ValueError("source_partition_quarantined")
        _checkpoint(
            platform.control,
            job,
            "validating",
            state="validating",
            partition=scope["partition"],
            transferred_bytes=transport.bytes,
        )
        if job["source"] == "usda_fdc":
            previous = (
                (platform.current() or {})
                .get("sources", {})
                .get(f"{job['source']}:{scope['partition']}")
            )
            if (
                previous
                and previous["release"] == scope["release"]
                and previous["parser_version"] == scope.get("parser_version", "1")
            ):
                result = {"no_change": True, "changed": 0, "unchanged": 1}
            else:
                result = import_usda(
                    settings,
                    scope["paths"],
                    platform=platform,
                    fence=job,
                    local=False,
                    release=scope["release"],
                    cursor=scope.get("cursor"),
                    partition=scope["partition"],
                    parser_version=scope.get("parser_version", "1"),
                )
        else:
            result = platform.sync(
                job["source"],
                scope["partition"],
                scope["release"],
                scope["records"],
                complete=scope.get("complete", True),
                cursor=scope.get("cursor"),
                parser_version=scope.get("parser_version", "1"),
                fence=job,
            )
        changed += result.get("changed", int(not result.get("no_change", False)))
        unchanged += result.get("unchanged", 0)
        with platform.control.connect() as db:
            platform.control.check_fence(job, db)
            db.execute(
                "UPDATE source_state SET checked_at=? WHERE source=? AND partition=?",
                (time.time(), job["source"], scope["partition"]),
            )
        _checkpoint(
            platform.control,
            job,
            "published",
            partition=scope["partition"],
            generation=(platform.current() or {}).get("generation"),
            transferred_bytes=transport.bytes,
        )
        count += 1
    return {
        "partitions": count,
        "changed": changed,
        "unchanged": unchanged,
        "no_change": changed == 0,
    }


def worker_once(
    settings, *, batch_size=2, acquisition=None, cancellation=None, job_id=None, schedule_due=True
):
    from .platform import Platform

    with heavy_lock(settings.data_dir):
        platform = Platform(settings.data_dir)
        platform.initialize()
        platform.recover()
        apply_rights_policy(settings, platform.control)
        # Adoption is local and validated. A bad legacy catalog must stop all acquisition.
        usda_denied = bool(platform.control.denied_sources() & {"usda_fdc", "local_usda"})
        if not usda_denied and schedule_due:
            platform.adopt_legacy()
        paths = local_sources(settings.import_dir)
        if paths and not platform.legacy_path().exists() and not usda_denied and schedule_due:
            import_usda(settings, paths, platform=platform)
        if schedule_due:
            schedule(settings)
        policy = load_policy(settings)
        control = platform.control
        results = []
        owner = "worker_" + uuid.uuid4().hex
        for _ in range(batch_size):
            if cancellation is not None and cancellation.is_set():
                break
            job = control.claim(owner, ttl=policy["scheduler"]["lease_seconds"], job_id=job_id)
            if not job:
                break
            try:
                with Lease(
                    control,
                    job,
                    policy["scheduler"]["lease_seconds"],
                    policy["scheduler"]["heartbeat_seconds"],
                ) as lease:
                    lease.cancellation = cancellation
                    report = execute_job(settings, job, platform, lease, acquisition=acquisition)
                    control.finish(job, reason="no_change" if report["no_change"] else None)
                results.append({"job_id": job["id"], "state": "succeeded", **report})
            except (TransportError, OSError) as error:
                attempt = job["attempt"]
                status = getattr(error, "status", None)
                if status in (401, 403):
                    state, reason = "blocked_by_credentials", "source_access_refused"
                elif status is not None and status != 429 and status < 500:
                    state, reason = "failed", "source_request_refused"
                elif attempt >= policy["scheduler"]["max_retries"]:
                    state, reason = "failed", "transport_retry_exhausted"
                else:
                    state, reason = "retry_wait", "transient_transport_error"
                control.finish(job, state=state, reason=reason)
                if state == "blocked_by_credentials":
                    control.set_source(job["source"], False)
                if state == "retry_wait":
                    delay = random.uniform(
                        0,
                        min(86400, policy["scheduler"]["retry_base_seconds"] * 2 ** (attempt - 1)),
                    )
                    retry_after = getattr(error, "retry_after", None)
                    if retry_after:
                        from email.utils import parsedate_to_datetime

                        try:
                            wait = (
                                float(retry_after)
                                if str(retry_after).isdigit()
                                else (parsedate_to_datetime(retry_after).timestamp() - time.time())
                            )
                            delay = max(delay, min(wait, 86400))
                        except (ValueError, TypeError, OverflowError):
                            pass
                    with control.connect() as db:
                        db.execute(
                            "UPDATE jobs SET due=? WHERE id=?", (time.time() + delay, job["id"])
                        )
                results.append({"job_id": job["id"], "state": state, "reason": reason})
            except Exception as error:  # noqa: BLE001 - Persist sanitized per-source failure, retaining last-good packs.
                state = (
                    "cancelled"
                    if isinstance(error, WorkerStopping)
                    else "blocked_by_policy"
                    if isinstance(error, PolicyError)
                    else "quarantined"
                )
                # No response body, URL, local path or credentials enter persisted reason text.
                reason = (
                    "worker_stopped"
                    if isinstance(error, WorkerStopping)
                    else "source_policy_blocked"
                    if isinstance(error, PolicyError)
                    else "source_validation_failed"
                )
                source_reason = getattr(error, "reason_code", None)
                if source_reason in {
                    "source_location_unresolved",
                    "source_reconciliation_required",
                }:
                    reason = source_reason
                if not isinstance(error, WorkerStopping):
                    try:
                        control.finish(job, state=state, reason=reason)
                    except ValueError:
                        reason = "worker_fence_lost"
                results.append({"job_id": job["id"], "state": state, "reason": reason})
        _touch_worker(settings.data_dir)
        return results


def _touch_worker(data_dir):
    heartbeat = Path(data_dir) / "control" / "worker-heartbeat.json"
    temp = heartbeat.with_suffix(".tmp")
    temp.write_text(json.dumps({"at": time.time(), "pid": os.getpid()}))
    os.replace(temp, heartbeat)


def worker(settings, *, once=False):
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            result = worker_once(settings, cancellation=stop)
            if once:
                return result
        except BlockingIOError:
            if once:
                return [{"state": "busy"}]
        stop.wait(load_policy(settings)["scheduler"]["tick_seconds"])


def supervise():
    """Forward signals, reap both roles and fail visibly if either child exits."""
    children = []
    stopping = False

    def terminate(signum, _frame):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                child.send_signal(signum)

    old_handlers = {sig: signal.signal(sig, terminate) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for role in ("serve", "worker"):
            children.append(subprocess.Popen([sys.executable, "-m", "bord_food_api", role]))
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(0.2)
        code = next((child.returncode for child in children if child.poll() is not None), 0)
        terminate(signal.SIGTERM, None)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        return code or 0
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
