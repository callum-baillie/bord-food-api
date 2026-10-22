"""Durable, append-only crawl outcomes. No source transport, catalog writes or secrets."""

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .nationwide import REGIONS, state_region
from .platform import atomic_json

CATEGORIES = {
    "published": ("success", "none"),
    "failed": ("failed", "manual_review"),
    "host_blocked": ("blocked", "manual_review"),
    "host_deferred": ("blocked", "manual_review"),
    "review_required": ("review", "manual_review"),
    "interrupted_requires_review": ("review", "manual_review"),
    "missing_branch_url": ("unresolved", "resolve_url"),
    "pending": ("queued", "not_started"),
    "running": ("running", "in_progress"),
    "deferred_budget": ("deferred", "budget_review"),
    "deferred_host_limits": ("deferred", "wait_for_host_budget"),
    "prior_history_hold": ("blocked", "manual_review"),
}
REASONS = {
    "pre_fetch_confidence",
    "page_review",
    "branch_snapshot_changed",
    "http_error",
    "robots_unavailable_or_denied",
    "robots_denied",
    "robots_invalid",
    "response_byte_limit",
    "unsupported_content_type",
    "response_status",
    "run_time_limit",
    "host_budget",
    "host_spacing",
    "source_paused",
    "target_unavailable",
    "redirect_limit",
    "network_policy_review_required",
    "non_public_source_address",
    "source_dns_empty",
    "artifact_byte_limit",
    "artifact_time_limit",
    "source_byte_budget_exhausted",
    "source_network_disabled",
    "source_fetch_denied",
    "request_budget_exhausted",
    "branch_url_missing",
    "generic_homepage",
    "unsafe_or_unsupported_url",
    "not_branch_html",
    "non_public_host",
    "inherited_host_hold",
    "interrupted",
    "historical_detail_unavailable",
    "prior_history_hold",
    "budget_exhausted",
    "daily_host_limit",
    "page_check_completed",
    "field_parser_error",
    "source_network_unavailable",
    "source_connection_failed",
    "source_timeout",
    "redirect_requires_review",
}
ERROR_CODES = {
    "Robots policy is unavailable or denies discovery": "robots_unavailable_or_denied",
    "Robots policy does not permit this request": "robots_denied",
    "Robots policy is not valid text": "robots_invalid",
    "Crawl response byte limit exceeded": "response_byte_limit",
    "Only robots text and approved branch HTML can be fetched": "unsupported_content_type",
    "Unexpected crawl response status": "response_status",
    "Crawl run time budget exhausted": "run_time_limit",
    "Crawl request budget exhausted": "host_budget",
    "Crawl host spacing/backoff is active": "host_spacing",
    "Crawl source is disabled by policy": "source_paused",
    "Approved target references an unavailable catalog branch": "target_unavailable",
}


ERROR_TYPES = {
    "CrawlBlocked",
    "PolicyError",
    "TransportError",
    "ValueError",
    "RuntimeError",
    "OSError",
    "TimeoutError",
    "ReviewRequired",
    "CampaignStopped",
    "Stopped",
    "TypeError",
    "KeyError",
    "RecursionError",
    "RedirectNotice",
}


def exception_details(error):
    status = getattr(error, "status", None)
    reason = (
        "redirect_requires_review"
        if type(error).__name__ == "RedirectNotice"
        else "http_error"
        if type(status) is int
        else ERROR_CODES.get(str(error))
    )
    if reason is None and str(error) in REASONS:
        reason = str(error)
    if reason is None and isinstance(error, OSError):
        reason = (
            "source_timeout" if isinstance(error, TimeoutError) else "source_network_unavailable"
        )
    return {
        "reason": reason or "historical_detail_unavailable",
        "error_type": type(error).__name__
        if type(error).__name__ in ERROR_TYPES
        else "UnknownError",
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        **(
            {"redirect_candidate": safe_url(error.target)}
            if type(error).__name__ == "RedirectNotice"
            else {}
        ),
    }


def safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        p = urlsplit(value)
        if p.scheme not in ("https", "http") or not p.hostname:
            return None
        host = p.hostname + (":" + str(p.port) if p.port else "")
        query = urlencode(
            [
                (
                    k,
                    v
                    if k.casefold()
                    in {"s", "store", "storeid", "store_id", "location", "locationid", "id", "ref"}
                    else "[redacted]",
                )
                for k, v in parse_qsl(p.query, keep_blank_values=True)
            ]
        )
        return urlunsplit((p.scheme, host, p.path, query, ""))
    except ValueError:
        return None


def _code(value):
    return value if isinstance(value, str) and value in REASONS else "historical_detail_unavailable"


def _key(target):
    if isinstance(target.get("history_target_key"), str) and re.fullmatch(
        r"[a-f0-9]{64}", target["history_target_key"]
    ):
        return target["history_target_key"]
    value = target.get("store_id") or target.get("source_key")
    if not value and not target.get("url"):
        raise ValueError("history_target_identity_missing")
    return hashlib.sha256(
        json.dumps([value, target.get("url")], sort_keys=True).encode()
    ).hexdigest()


def _region(target, store, config):
    address = target.get("source_address")
    if isinstance(address, dict):
        region = REGIONS.get(str(address.get("region", "")).strip().casefold())
        if region:
            return region
    elif isinstance(address, str):
        region, _ = state_region({"addr:full": address})
        if region:
            return region
    address = store.get("address")
    if isinstance(address, dict):
        region = REGIONS.get(str(address.get("region", "")).strip().casefold())
        if region:
            return region
    return REGIONS.get(str(config.get("state") or "").strip().casefold(), "UNKNOWN")


class CrawlHistory:
    def __init__(self, root, *, directory=None):
        self.directory = Path(directory) if directory else Path(root) / "control/crawl-history"
        self.path = self.directory / "history.sqlite"
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,status TEXT,started_at REAL,
              completed_at REAL,observed_at REAL,source_checkpoint REAL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,run_id TEXT,state TEXT,
              target_key TEXT,signature TEXT,payload TEXT,observed_at REAL);
            CREATE INDEX IF NOT EXISTS history_region ON events(state,run_id,id);
            CREATE INDEX IF NOT EXISTS history_run ON events(run_id,id);
            CREATE TABLE IF NOT EXISTS latest(run_id TEXT,state TEXT,target_key TEXT,signature TEXT,
              event_id INTEGER,PRIMARY KEY(run_id,state,target_key));
            CREATE TABLE IF NOT EXISTS holds(hold_key TEXT PRIMARY KEY,event_id INTEGER,host TEXT,
              store_id TEXT,url_hash TEXT,reason TEXT,active INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,hold_key TEXT,evidence TEXT,
              reviewed_at REAL,event_id INTEGER);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, config):
        run = config.get("campaign_id")
        if not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run):
            raise ValueError("invalid_history_run_id")
        targets = []
        for target in [*config.get("targets", []), *config.get("coverage_gaps", [])]:
            if not target.get("store_id") and not target.get("source_key"):
                continue
            row = {
                key: target[key]
                for key in ("store_id", "source_key", "name", "source_address")
                if key in target
            }
            row["history_target_key"] = _key(target)
            url = target.get("url")
            row["url"] = safe_url(url)
            row["history_url_hash"] = hashlib.sha256(url.encode()).hexdigest() if url else None
            targets.append(row)
        metadata = {
            "campaign_id": run,
            "state": config.get("state"),
            "targets": targets,
            "source_directory": config.get("source_directory"),
            "original_config_sha256": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest(),
        }
        directory = self.directory / "run-metadata"
        directory.mkdir(exist_ok=True)
        path = directory / (run + ".json")
        if not path.exists() or json.loads(path.read_text()) != metadata:
            atomic_json(path, metadata)
        return metadata

    def ingest(self, snapshot, config=None, stores=None, *, observed_at=None):
        config, stores = config or {}, stores or {}
        now = time.time() if observed_at is None else observed_at
        run = snapshot.get("campaign_id") or config.get("campaign_id")
        if not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run):
            raise ValueError("invalid_history_run_id")
        meta = {
            str(t["store_id"]): t
            for t in [*config.get("targets", []), *config.get("coverage_gaps", [])]
            if t.get("store_id")
        }
        items = snapshot.get("targets")
        if isinstance(items, dict):
            rows = [{"store_id": key, **item} for key, item in items.items()]
        else:
            rows = list(snapshot.get("completed", []))
            active = snapshot.get("active")
            if active and not any(row.get("store_id") == active for row in rows):
                rows.append(
                    {
                        **snapshot.get("active_attempt", {}),
                        "store_id": active,
                        "state": "interrupted_requires_review"
                        if snapshot.get("state") == "stopped"
                        else "running",
                    }
                )
        checkpoint = (
            snapshot.get("updated_at")
            or snapshot.get("completed_at")
            or snapshot.get("stopped_at")
            or snapshot.get("started_at")
            or now
        )
        inserted = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT source_checkpoint FROM runs WHERE run_id=?", (run,)
            ).fetchone()
            if previous and checkpoint < previous[0]:
                return 0
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,completed_at=excluded.completed_at,observed_at=excluded.observed_at,source_checkpoint=excluded.source_checkpoint",
                (
                    run,
                    snapshot.get("state"),
                    snapshot.get("started_at"),
                    snapshot.get("completed_at") or snapshot.get("stopped_at"),
                    now,
                    checkpoint,
                ),
            )
            for item in rows:
                identity = str(item.get("store_id") or "")
                target = meta.get(identity, {})
                store = stores.get(identity, {})
                region = _region(target, store, config)
                url = target.get("url") or item.get("url") or store.get("website")
                row = {**target, **item, "url": url, "store_id": identity or None}
                expected = (
                    config.get("original_config_sha256")
                    or hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
                )
                row["metadata_binding"] = (
                    "config_hash_verified"
                    if snapshot.get("config_sha256") == expected
                    else "run_id_only"
                    if target
                    else "current_directory_fallback"
                )
                inserted += self._record(db, run, region, row, snapshot, store, now)
        return inserted

    def _record(self, db, run, region, row, snapshot, store, now):
        state = row.get("state", "pending")
        if state == "pending" and snapshot.get("state") == "paused_budget":
            state = "deferred_budget"
        if state == "pending" and snapshot.get("state") == "waiting_host_limits":
            state = "deferred_host_limits"
        category, retry = CATEGORIES.get(state, ("unknown", "manual_review"))
        raw_url = row.get("url")
        url = safe_url(raw_url)
        try:
            host = urlsplit(url or "").hostname or row.get("host")
        except ValueError:
            host = None
        host = (
            host if isinstance(host, str) and re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host) else None
        )
        reason = _code(row.get("reason"))
        if reason == "historical_detail_unavailable":
            reason = {
                "published": "page_check_completed",
                "deferred_budget": "budget_exhausted",
                "deferred_host_limits": "daily_host_limit",
                "host_deferred": "inherited_host_hold",
                "missing_branch_url": "branch_url_missing",
                "interrupted_requires_review": "interrupted",
            }.get(state, reason)
        key = _key(row)
        event = {
            "run_id": run,
            "state": region,
            "target_key": key,
            "store_id": row.get("store_id"),
            "source_key": row.get("source_key"),
            "metadata_binding": row.get("metadata_binding"),
            "name": row.get("name") or store.get("name"),
            "banner": store.get("chain_name"),
            "url": url,
            "url_hash": row.get("history_url_hash")
            or (hashlib.sha256(raw_url.encode()).hexdigest() if raw_url else None),
            "host": host,
            "outcome": state,
            "category": category,
            "reason": reason,
            "retry_status": retry,
            "job_id": row.get("job_id"),
            "stage": row.get("stage")
            if row.get("stage")
            in {
                "identity",
                "before_fetch",
                "robots_and_branch_fetch",
                "page_review",
                "publication",
                "robots",
                "branch_page",
            }
            else "unknown",
            "error_type": row.get("error_type")
            if row.get("error_type") in ERROR_TYPES
            else row.get("reason")
            if row.get("reason") in ERROR_TYPES
            else None,
            "http_status": row.get("http_status")
            if type(row.get("http_status")) is int and 100 <= row["http_status"] <= 599
            else None,
            "field_observations": row.get("field_observations")
            if isinstance(row.get("field_observations"), dict)
            else None,
            "field_enrichment": row.get("field_enrichment")
            if isinstance(row.get("field_enrichment"), dict)
            else None,
            "redirect_candidate": safe_url(row.get("redirect_candidate")),
            "attempt_started_at": row.get("attempt_started_at"),
            "finished_at": row.get("finished_at"),
            "network_attempted": row.get("network_attempted")
            if type(row.get("network_attempted")) is bool
            else None,
            "next_check_at": snapshot.get("next_due") if category == "deferred" else None,
            "timestamp_precision": "target" if row.get("finished_at") else "snapshot_observation",
            "historical_detail_available": reason != "historical_detail_unavailable",
        }
        # Observation timestamps do not manufacture a new failure every poll.
        signature = hashlib.sha256(
            json.dumps(
                {k: v for k, v in event.items() if k not in {"name", "banner"}}, sort_keys=True
            ).encode()
        ).hexdigest()
        last = db.execute(
            "SELECT signature FROM latest WHERE run_id=? AND state=? AND target_key=?",
            (run, region, key),
        ).fetchone()
        if last and last[0] == signature:
            return 0
        event["observed_at"] = now
        raw = json.dumps(event, sort_keys=True, allow_nan=False)
        event_id = db.execute(
            "INSERT INTO events(run_id,state,target_key,signature,payload,observed_at) VALUES(?,?,?,?,?,?)",
            (run, region, key, signature, raw, now),
        ).lastrowid
        db.execute(
            "INSERT INTO latest VALUES(?,?,?,?,?) ON CONFLICT(run_id,state,target_key) DO UPDATE SET signature=excluded.signature,event_id=excluded.event_id",
            (run, region, key, signature, event_id),
        )
        if category in {"blocked", "review", "failed"} and reason not in {
            "prior_history_hold",
            "inherited_host_hold",
        }:
            hold_key = (
                "host:" + host
                if category == "blocked" and host
                else "target:" + str(row.get("store_id") or event["url_hash"] or key)
            )
            # An observer/parser upgrade may enrich an old event's metadata. A
            # review of that same physical attempt remains valid. Only a new
            # attempt/run may reopen the hold; retain every observation either way.
            reviewed = db.execute(
                "SELECT e.payload FROM reviews r JOIN events e ON e.id=r.event_id "
                "WHERE r.hold_key=? ORDER BY r.id DESC LIMIT 1",
                (hold_key,),
            ).fetchone()
            attempt_keys = (
                "run_id",
                "state",
                "target_key",
                "outcome",
                "job_id",
                "attempt_started_at",
                "finished_at",
            )
            reviewed_event = json.loads(reviewed[0]) if reviewed else None
            if reviewed and all(reviewed_event.get(k) == event.get(k) for k in attempt_keys):
                return 1
            db.execute(
                "INSERT INTO holds VALUES(?,?,?,?,?,?,1) ON CONFLICT(hold_key) DO UPDATE SET event_id=excluded.event_id,reason=excluded.reason,active=1",
                (hold_key, event_id, host, row.get("store_id"), event["url_hash"], reason),
            )
        return 1

    def blocking(self, target):
        return _blocking(self.path, target)

    def resolve(self, hold_key, evidence, *, reviewed_at=None):
        # Evidence is an operator's short reference, not a secret, source page or URL.
        if not isinstance(evidence, str) or not re.fullmatch(
            r"[A-Za-z0-9 _./:#-]{5,240}", evidence
        ):
            raise ValueError("review_evidence_reference_required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT event_id FROM holds WHERE hold_key=? AND active=1", (hold_key,)
            ).fetchone()
            if not row:
                raise ValueError("active_history_hold_not_found")
            db.execute(
                "INSERT INTO reviews(hold_key,evidence,reviewed_at,event_id) VALUES(?,?,?,?)",
                (hold_key, evidence, time.time() if reviewed_at is None else reviewed_at, row[0]),
            )
            db.execute("UPDATE holds SET active=0 WHERE hold_key=?", (hold_key,))

    def export(self):
        directory = self.directory / "reports"
        directory.mkdir(exist_ok=True)
        attention = "json_extract(payload,'$.category') IN ('failed','blocked','review','unresolved','deferred','unknown')"
        with (directory / "export.lock").open("a") as lock, self.connect() as db:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db.execute("BEGIN")
            watermarks_path = directory / "watermarks.json"
            watermarks = json.loads(watermarks_path.read_text()) if watermarks_path.exists() else {}
            regions = [r[0] for r in db.execute("SELECT DISTINCT state FROM events ORDER BY state")]
            summary = {
                "runs": [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started_at")],
                "states": {},
                "active_holds": db.execute("SELECT count(*) FROM holds WHERE active=1").fetchone()[
                    0
                ],
            }
            for region in regions:
                count, latest = db.execute(
                    "SELECT count(*),max(id) FROM events WHERE state=?", (region,)
                ).fetchone()
                wanted = "state:" + region
                path = directory / "states" / region / "attention.json"
                if watermarks.get(wanted) != latest or not path.exists():
                    _stream_array(
                        path,
                        db.execute(
                            "SELECT payload FROM events WHERE state=? AND "
                            + attention
                            + " ORDER BY id",
                            (region,),
                        ),
                    )
                    watermarks[wanted] = latest
                n = db.execute(
                    "SELECT count(*) FROM events WHERE state=? AND " + attention, (region,)
                ).fetchone()[0]
                summary["states"][region] = {"events": count, "attention_events": n}
            for run, latest in db.execute("SELECT run_id,max(id) FROM events GROUP BY run_id"):
                path = directory / "runs" / (run + ".json")
                if watermarks.get("run:" + run) != latest or not path.exists():
                    _stream_array(
                        path,
                        db.execute("SELECT payload FROM events WHERE run_id=? ORDER BY id", (run,)),
                    )
                    watermarks["run:" + run] = latest
            atomic_json(watermarks_path, watermarks)
            atomic_json(directory / "summary.json", summary)
        return summary


def _stream_array(path, cursor):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write("[\n")
            separator = ""
            for row in cursor:
                output.write(separator + row[0])
                separator = ",\n"
            output.write("\n]\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def capture_snapshot(root, snapshot, config):
    history = CrawlHistory(root)
    history.register(config)
    return history.ingest(snapshot, config)


def _blocking(path, target):
    if not path.exists():
        return []
    url = target.get("url") or target.get("website")
    host = urlsplit(url or "").hostname
    keys = ["host:" + str(host), "target:" + str(target.get("store_id") or target.get("id"))]
    if url:
        keys.append("target:" + hashlib.sha256(url.encode()).hexdigest())
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in db.execute(
                "SELECT hold_key,event_id,reason FROM holds WHERE active=1 AND hold_key IN ("
                + ",".join("?" for _ in keys)
                + ")",
                keys,
            )
        ]
    finally:
        db.close()


def prior_holds(root, target):
    return _blocking(Path(root) / "control/crawl-history/history.sqlite", target)
