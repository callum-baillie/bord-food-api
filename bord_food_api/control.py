"""Durable single-host control plane; serving catalog objects are never written here."""

import fcntl
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_actions(source TEXT,action TEXT,allowed INTEGER NOT NULL,
 PRIMARY KEY(source,action));
CREATE TABLE IF NOT EXISTS rights(source TEXT PRIMARY KEY, denied INTEGER NOT NULL DEFAULT 0,
 retention_until REAL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS installation(id TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS installation_singleton ON installation((1));
CREATE TABLE IF NOT EXISTS identities(source TEXT, kind TEXT, source_key TEXT, id TEXT NOT NULL,
 PRIMARY KEY(source,kind,source_key));
CREATE TABLE IF NOT EXISTS identity_decisions(id INTEGER PRIMARY KEY, action TEXT, payload TEXT,
 created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS source_state(source TEXT, partition TEXT, release TEXT, cursor TEXT,
 parser_version TEXT, checked_at REAL, enabled INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(source,partition));
CREATE TABLE IF NOT EXISTS source_policy(source TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, source TEXT NOT NULL, partition TEXT NOT NULL,
 operation TEXT NOT NULL, version TEXT NOT NULL, dedupe TEXT NOT NULL, state TEXT NOT NULL,
 due REAL NOT NULL, owner TEXT, token INTEGER NOT NULL DEFAULT 0, expires REAL,
 heartbeat REAL, attempt INTEGER NOT NULL DEFAULT 0, reason TEXT, checkpoint TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(dedupe) WHERE state IN
 ('queued','leased','running','validating','publishing','retry_wait');
CREATE TABLE IF NOT EXISTS preparations(generation TEXT PRIMARY KEY, base TEXT, manifest TEXT,
 acknowledgments TEXT, events TEXT, finalized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, generation TEXT,
 entity_id TEXT, kind TEXT, operation TEXT, revision TEXT,
 UNIQUE(generation,entity_id,kind,operation));
CREATE TABLE IF NOT EXISTS memberships(source TEXT, partition TEXT, source_key TEXT, entity_id TEXT,
 kind TEXT, hash TEXT, payload TEXT, last_run TEXT, missing_runs INTEGER DEFAULT 0,
 missing_since REAL, last_absence_run TEXT, parser_version TEXT,
 PRIMARY KEY(source,partition,kind,source_key));
"""


class Control:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.path = self.root / "control" / "control.sqlite"
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / "migration.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.connect() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise ValueError("Unsupported control schema; restore a matching backup")
                db.execute("PRAGMA journal_mode=WAL")
                db.executescript(SCHEMA)
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                if not db.execute("SELECT 1 FROM installation").fetchone():
                    db.execute("INSERT OR IGNORE INTO installation VALUES (?)", (uuid.uuid4().hex,))

    def identity(self, source, kind, source_key):
        prefixes = {"chain": "chn", "store": "sto", "product": "prd"}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                (source, kind, str(source_key)),
            ).fetchone()
            if row:
                return row[0]
            entity_id = f"{prefixes.get(kind, kind)}_{uuid.uuid4().hex}"
            db.execute(
                "INSERT INTO identities VALUES (?,?,?,?)",
                (source, kind, str(source_key), entity_id),
            )
            return entity_id

    def identity_batch(self, source, keys):
        """Reserve a bounded streamed batch in one durable transaction.

        Identity edits hold the publisher lock; sync callers already own it.
        Previously reserved IDs survive retries and are never regenerated.
        """
        keys = list(dict.fromkeys((kind, str(key)) for kind, key in keys))
        if len(keys) > 1024:
            raise ValueError("Identity batch exceeds bounded size")
        prefixes = {"chain": "chn", "store": "sto", "product": "prd"}
        result = {}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for kind, key in keys:
                row = db.execute(
                    "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                    (source, kind, key),
                ).fetchone()
                if row:
                    result[kind, key] = row[0]
                else:
                    identity = f"{prefixes.get(kind, kind)}_{uuid.uuid4().hex}"
                    db.execute(
                        "INSERT INTO identities VALUES (?,?,?,?)", (source, kind, key, identity)
                    )
                    result[kind, key] = identity
        return result

    @contextmanager
    def identity_edit(self):
        with (self.root / "control/publisher.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def alias(self, source, kind, source_key, target, reason):
        if not reason.strip():
            raise ValueError("Identity correction requires a reason")
        with self.identity_edit(), self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM identities WHERE kind=? AND id=?", (kind, target)
            ).fetchone():
                raise ValueError("Unknown identity")
            old = db.execute(
                "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                (source, kind, source_key),
            ).fetchone()
            payload = {
                "source": source,
                "kind": kind,
                "source_key": source_key,
                "target": target,
                "previous": old[0] if old else None,
                "reason": reason,
            }
            db.execute(
                "INSERT OR REPLACE INTO identities VALUES (?,?,?,?)",
                (source, kind, source_key, target),
            )
            db.execute(
                "INSERT INTO identity_decisions(action,payload,created_at) VALUES (?,?,?)",
                ("alias", json.dumps(payload), time.time()),
            )

    def undo_alias(self, decision_id):
        with self.identity_edit(), self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM identity_decisions WHERE id=?", (decision_id,)
            ).fetchone()
            if not row or row["action"] != "alias":
                raise ValueError("Unknown alias decision")
            p = json.loads(row["payload"])
            key = (p["source"], p["kind"], p["source_key"])
            current = db.execute(
                "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?", key
            ).fetchone()
            if not current or current[0] != p["target"]:
                raise ValueError("Identity has a newer decision")
            if p["previous"]:
                db.execute(
                    "UPDATE identities SET id=? WHERE source=? AND kind=? AND source_key=?",
                    (p["previous"], *key),
                )
            else:
                db.execute("DELETE FROM identities WHERE source=? AND kind=? AND source_key=?", key)
            db.execute(
                "INSERT INTO identity_decisions(action,payload,created_at) VALUES (?,?,?)",
                ("undo", json.dumps({"decision_id": decision_id}), time.time()),
            )

    def set_source(self, source, enabled):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO source_policy VALUES (?,?)", (source, int(enabled)))
            if not enabled:
                db.execute(
                    "UPDATE jobs SET state='blocked_by_policy', reason='source_paused', token=token+1, expires=NULL WHERE source=? AND state IN ('queued','retry_wait','leased','running','validating','publishing')",
                    (source,),
                )

    def enabled(self, source):
        with self.connect() as db:
            row = db.execute(
                "SELECT enabled FROM source_policy WHERE source=?", (source,)
            ).fetchone()
            return row is None or bool(row[0])

    def enqueue(self, source, partition, operation="sync", version="1", due=None):
        due = time.time() if due is None else due
        dedupe = json.dumps([source, partition, operation, version])
        with self.connect() as db:
            job_id = "job_" + uuid.uuid4().hex
            db.execute(
                "INSERT OR IGNORE INTO jobs(id,source,partition,operation,version,dedupe,state,due) VALUES (?,?,?,?,?,?,'queued',?)",
                (job_id, source, partition, operation, version, dedupe, due),
            )
            return db.execute(
                "SELECT id FROM jobs WHERE dedupe=? AND state IN ('queued','leased','running','validating','publishing','retry_wait')",
                (dedupe,),
            ).fetchone()[0]

    def claim(self, owner, now=None, ttl=120, job_id=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE jobs SET state='blocked_by_policy',reason='source_paused',token=token+1 WHERE source IN (SELECT source FROM source_policy WHERE enabled=0) AND state IN ('queued','retry_wait','leased','running','validating','publishing')"
            )
            row = db.execute(
                """SELECT * FROM jobs WHERE
                ((state IN ('queued','retry_wait') AND due<=?) OR
                (state IN ('leased','running','validating','publishing') AND expires<=?))
                AND (? IS NULL OR id=?)
                ORDER BY due,id LIMIT 1""",
                (now, now, job_id, job_id),
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE jobs SET state='running',owner=?,token=token+1,expires=?,heartbeat=?,attempt=attempt+1 WHERE id=?",
                (owner, now + ttl, now, row["id"]),
            )
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def check_fence(self, job, connection=None):
        if connection is None:
            with self.connect() as db:
                return self.check_fence(job, db)
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if (
            not row
            or row["token"] != job["token"]
            or row["owner"] != job["owner"]
            or row["state"] not in ("running", "leased", "validating", "publishing")
            or row["expires"] <= time.time()
        ):
            raise ValueError("Worker fence expired")
        policy = connection.execute(
            "SELECT enabled FROM source_policy WHERE source=?", (row["source"],)
        ).fetchone()
        if policy and not policy[0]:
            raise ValueError("Source paused")
        restricted = connection.execute(
            "SELECT 1 FROM rights WHERE source=? AND (denied=1 OR (retention_until IS NOT NULL AND retention_until<=?))",
            (row["source"], time.time()),
        ).fetchone()
        if restricted:
            raise ValueError("Source rights revoked")

    def heartbeat(self, job, ttl=120):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_fence(job, db)
            db.execute(
                "UPDATE jobs SET heartbeat=?,expires=? WHERE id=?",
                (time.time(), time.time() + ttl, job["id"]),
            )

    def finish(self, job, state="succeeded", reason=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_fence(job, db)
            db.execute(
                "UPDATE jobs SET state=?,reason=?,expires=NULL WHERE id=?",
                (state, reason, job["id"]),
            )

    def denied_sources(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            denied = {
                row[0]
                for row in db.execute(
                    "SELECT source FROM rights WHERE denied=1 OR (retention_until IS NOT NULL AND retention_until<=?)",
                    (now,),
                )
            }
            if denied & {"usda_fdc", "local_usda"}:
                denied.add("usda_products")
            if "retailer_maps" in denied:
                denied.add("retailer_page")
            if "usda_snap" in denied:
                denied.add("usda_snap_arcgis")
            return denied

    def restrict_source(
        self, source, *, retention_until=None, denied=True, reason="operator_rights_revocation"
    ):
        if not reason.strip():
            raise ValueError("Rights review requires a reason")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO rights VALUES (?,?,?,?)",
                (source, int(denied), retention_until, reason),
            )
        if denied:
            self.set_source(source, False)

    def set_action(self, source, action, allowed):
        if action not in {
            "can_display",
            "can_redistribute",
            "can_fetch",
            "can_store_raw",
            "can_store_normalized",
        }:
            raise ValueError("Unsupported policy action")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO policy_actions VALUES (?,?,?)",
                (source, action, int(allowed)),
            )

    def hidden_sources(self, action="can_display"):
        with self.connect() as db:
            hidden = self.denied_sources() | {
                row[0]
                for row in db.execute(
                    "SELECT source FROM policy_actions WHERE action=? AND allowed=0", (action,)
                )
            }
            if hidden & {"usda_fdc", "local_usda"}:
                hidden.add("usda_products")
            if "retailer_maps" in hidden:
                hidden.add("retailer_page")
            if "usda_snap" in hidden:
                hidden.add("usda_snap_arcgis")
            return hidden
