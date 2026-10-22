"""Immutable, content-addressed catalog packs and recoverable generation publication."""

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from .assistance import ASSISTANCE_KINDS
from .control import SCHEMA_VERSION as CONTROL_SCHEMA_VERSION
from .control import Control
from .domain import US_STATES, business_payload, content_hash, encoded
from .refresh import GROUP_FIELDS, field_groups, plan_store_refresh

# Sealed objects are immutable. Avoid rereading multi-GB packs on every idle
# scheduler tick, while detecting replacement, writes or permission changes.
_VALIDATED_OBJECTS = OrderedDict()
_VALIDATION_LOCK = Lock()


def _object_signature(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


PACKS = {
    **ASSISTANCE_KINDS,
    "chain": "stores",
    "store": "stores",
    "product": "products",
    "food": "products",
    "price": "prices",
    "listing": "prices",
    "stock": "prices",
    "placement": "maps",
    "map": "maps",
    "guidance": "guidance",
}
SEARCH_FIELDS = (
    "id",
    "name",
    "description",
    "brand",
    "brands",
    "category",
    "categories",
    "address",
    "gtin14",
    "gtin",
    "code",
    "phone",
    "email",
    "website",
    "source_id",
)

PACK_SCHEMA = """
CREATE TABLE entities(kind TEXT, id TEXT, source TEXT, partition TEXT, source_key TEXT,
 revision TEXT, payload TEXT, PRIMARY KEY(kind,id));
CREATE INDEX entity_source ON entities(source,partition,kind,source_key);
CREATE INDEX entity_key ON entities(source,kind,source_key);
CREATE VIRTUAL TABLE search USING fts5(kind UNINDEXED,id UNINDEXED,text);
CREATE VIRTUAL TABLE spatial USING rtree(rowid,min_lat,max_lat,min_lon,max_lon);
PRAGMA user_version=1;
"""


@contextmanager
def _sqlite(*args, **kwargs):
    """SQLite's built-in context manager commits but does not close its handle."""
    connection = sqlite3.connect(*args, **kwargs)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def fsync_dir(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(encoded(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def _identity_records(records, control, source):
    """Bound RAM and fsync frequency without materializing a source export."""

    def batch_ids(batch):
        keys = [(r["kind"], str(r["source_key"])) for r in batch]
        keys.extend(
            ("chain", str(r["payload"]["chain_key"]))
            for r in batch
            if r["kind"] == "store" and r["payload"].get("chain_key")
        )
        for record in batch:
            if record["kind"] in ASSISTANCE_KINDS:
                for relation in ("site", "service"):
                    if record["payload"].get(relation + "_key"):
                        prefix = (
                            "osm_assistance_"
                            if record["kind"].startswith("osm_")
                            else "assistance_"
                        )
                        keys.append((prefix + relation, str(record["payload"][relation + "_key"])))
        return control.identity_batch(source, keys)

    batch, size = [], 0
    for record in records:
        if record.get("kind") not in PACKS or not str(record.get("source_key", "")):
            raise ValueError("Invalid source record")
        weight = len(encoded(record).encode())
        if batch and (len(batch) >= 256 or size + weight > 8 * 1024**2):
            identities = batch_ids(batch)
            for item in batch:
                yield item, identities
            batch, size = [], 0
        batch.append(record)
        size += weight
    if batch:
        identities = batch_ids(batch)
        for item in batch:
            yield item, identities


class Platform:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.control = Control(self.root)
        self.initialize()

    def initialize(self):
        for directory in ("objects/catalogs", "generations", "staging", "backups"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    @contextmanager
    def writer(self):
        with (self.root / "control" / "publisher.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def current(self):
        pointer = self.root / "current.json"
        return json.loads(pointer.read_text()) if pointer.exists() else None

    def manifest(self, generation=None):
        if generation is None:
            return self.current()
        if (
            not isinstance(generation, str)
            or not generation.startswith("g_")
            or not generation[2:].isalnum()
        ):
            raise ValueError("Invalid generation")
        path = self.root / "generations" / f"{generation}.json"
        if not path.exists():
            raise ValueError("Generation expired")
        return json.loads(path.read_text())

    def object_path(self, relative):
        path = (self.root / relative).resolve()
        if (
            path.parent != (self.root / "objects" / "catalogs").resolve()
            or path.suffix != ".sqlite"
        ):
            raise ValueError("Invalid catalog object")
        return path

    def legacy_path(self):
        manifest = self.current()
        if manifest and "usda" in manifest["packs"]:
            return self.object_path(manifest["packs"]["usda"])
        return self.root / "foods.sqlite"

    def _seal(self, path):
        with _sqlite(path) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Catalog integrity failed")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            os.fsync(handle.fileno())
        target = self.root / "objects" / "catalogs" / f"{digest}.sqlite"
        if not target.exists():
            os.replace(path, target)
            target.chmod(0o444)
            fsync_dir(target.parent)
        return target.relative_to(self.root).as_posix()

    def _finalize(self, db, manifest):
        row = db.execute(
            "SELECT * FROM preparations WHERE generation=?", (manifest["generation"],)
        ).fetchone()
        if not row or row["finalized"]:
            return
        acknowledgments = json.loads(row["acknowledgments"])
        if isinstance(acknowledgments, dict):
            db.execute("DELETE FROM source_state")
            acknowledgments = list(acknowledgments["replace_sources"].values())
        for ack in acknowledgments:
            db.execute(
                "INSERT OR REPLACE INTO source_state(source,partition,release,cursor,parser_version,checked_at) VALUES (?,?,?,?,?,?)",
                (
                    ack["source"],
                    ack["partition"],
                    ack["release"],
                    json.dumps(ack.get("cursor")),
                    ack["parser_version"],
                    time.time(),
                ),
            )
        for event in json.loads(row["events"]):
            db.execute(
                "INSERT OR IGNORE INTO changes(generation,entity_id,kind,operation,revision) VALUES (?,?,?,?,?)",
                (
                    manifest["generation"],
                    event["id"],
                    event["kind"],
                    event["operation"],
                    event.get("revision"),
                ),
            )
        db.execute(
            "UPDATE preparations SET finalized=1 WHERE generation=?", (manifest["generation"],)
        )

    def _recover(self):
        manifest = self.current()
        if manifest:
            self.validate_manifest(manifest)
            with self.control.connect() as db:
                self._finalize(db, manifest)

    def recover(self):
        with self.writer():
            self._recover()

    def validate_manifest(self, manifest, *, force=False):
        if manifest.get("schema_version") != "1.0.0":
            raise ValueError("Unsupported generation schema")
        for relative in manifest["packs"].values():
            path = self.object_path(relative)
            signature = _object_signature(path)
            with _VALIDATION_LOCK:
                validated = not force and _VALIDATED_OBJECTS.get(path) == signature
            if validated:
                continue
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != path.stem:
                    raise ValueError("Catalog object checksum mismatch")
            with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Catalog object corrupt")
            if _object_signature(path) != signature:
                raise ValueError("Catalog changed during integrity validation")
            with _VALIDATION_LOCK:
                _VALIDATED_OBJECTS[path] = signature
                _VALIDATED_OBJECTS.move_to_end(path)
                while len(_VALIDATED_OBJECTS) > 128:
                    _VALIDATED_OBJECTS.popitem(last=False)

    def _publish(
        self,
        packs,
        source,
        partition,
        release,
        cursor,
        parser_version,
        events,
        fence=None,
        hook=None,
        source_snapshot=None,
        identity_snapshot=None,
    ):
        previous = self.current()
        generation = "g_" + uuid.uuid4().hex
        ack = {
            "source": source,
            "partition": partition,
            "release": release,
            "cursor": cursor,
            "parser_version": parser_version,
        }
        manifest = {
            "schema_version": "1.0.0",
            "generation": generation,
            "created_at": datetime.now(UTC).isoformat(),
            "packs": {**(previous or {}).get("packs", {}), **packs},
            "sources": {**(previous or {}).get("sources", {}), f"{source}:{partition}": ack},
            "registry_revision": self._registry_revision(),
        }
        if source_snapshot is not None:
            manifest["sources"] = source_snapshot
            manifest["packs"] = packs
        manifest["redirects"] = self._redirects(manifest["packs"])
        if identity_snapshot is not None:
            manifest["registry_revision"] = identity_snapshot["registry_revision"]
            manifest["redirects"] = identity_snapshot.get("redirects", {})
        self.validate_manifest(manifest)
        atomic_json(self.root / "generations" / f"{generation}.json", manifest)
        with self.control.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if fence:
                self.control.check_fence(fence, db)
            db.execute(
                "INSERT INTO preparations(generation,base,manifest,acknowledgments,events) VALUES (?,?,?,?,?)",
                (
                    generation,
                    (previous or {}).get("generation"),
                    encoded(manifest),
                    encoded(
                        [ack] if source_snapshot is None else {"replace_sources": source_snapshot}
                    ),
                    encoded(events),
                ),
            )
        if hook:
            hook("before_switch")
        # Fence and pointer switch share a control write lock: lease takeover cannot race this section.
        with self.control.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if fence:
                self.control.check_fence(fence, db)
            restricted = db.execute(
                "SELECT 1 FROM rights WHERE source=? AND (denied=1 OR (retention_until IS NOT NULL AND retention_until<=?))",
                (source, time.time()),
            ).fetchone()
            if restricted:
                raise ValueError("Source rights revoked")
            if (self.current() or {}).get("generation") != (previous or {}).get("generation"):
                raise ValueError("Base generation changed")
            atomic_json(self.root / "current.json", manifest)
        if hook:
            hook("after_switch")
        with self.control.connect() as db:
            self._finalize(db, manifest)
        return manifest

    def _registry_revision(self):
        with self.control.connect() as db:
            return (
                db.execute("SELECT count(*) FROM identities").fetchone()[0]
                + db.execute("SELECT count(*) FROM identity_decisions").fetchone()[0]
            )

    def publish_usda(
        self,
        path,
        source="usda_fdc",
        partition="all",
        release="",
        cursor=None,
        fence=None,
        hook=None,
        parser_version="1",
    ):
        from .catalog import connect, metadata

        if {source, "usda_fdc", "local_usda"} & self.control.denied_sources():
            raise ValueError("Source rights revoked")
        with connect(Path(path)) as db:
            if not metadata(db).get("totalFoods"):
                raise ValueError("Empty USDA catalog")
        with self.writer():
            self._recover()
            with tempfile.TemporaryDirectory(dir=self.root / "staging") as directory:
                private = Path(directory) / "usda.sqlite"
                # SQLite backup copies a private snapshot, including any committed WAL data.
                with (
                    _sqlite(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as src,
                    _sqlite(private) as dst,
                ):
                    src.backup(dst)
                relative = self._seal(private)
                return self._publish(
                    {"usda": relative},
                    source,
                    partition,
                    release,
                    cursor,
                    parser_version,
                    [],
                    fence,
                    hook,
                )

    def adopt_legacy(self):
        path = self.root / "foods.sqlite"
        if path.exists() and not (self.current() or {}).get("packs", {}).get("usda"):
            return self.publish_usda(
                path, source="local_usda", release="adopted", cursor={"manual": True}
            )
        return self.current()

    def records(self, kind, generation=None):
        manifest = self.manifest(generation)
        pack = PACKS.get(kind)
        if not manifest or pack not in manifest["packs"]:
            return []
        path = self.object_path(manifest["packs"][pack])
        denied = self.control.hidden_sources()
        redirects = manifest.get("redirects", {})
        with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            return [
                self._visible_payload(json.loads(row[0]), denied)
                for row in db.execute(
                    "SELECT payload,source,id FROM entities WHERE kind=? ORDER BY id", (kind,)
                )
                if row[1] not in denied
                and row[2] not in redirects
                and (
                    kind != "store"
                    or json.loads(row[0]).get("directory_scope", {}).get("status") != "excluded"
                )
            ]

    def get(self, kind, entity_id, generation=None):
        manifest = self.manifest(generation)
        pack = PACKS.get(kind)
        if not manifest or pack not in manifest["packs"]:
            return None
        path = self.object_path(manifest["packs"][pack])
        with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            target = manifest.get("redirects", {}).get(entity_id, entity_id)
            row = db.execute(
                "SELECT payload,source FROM entities WHERE kind=? AND id=?", (kind, target)
            ).fetchone()
            if not row or row[1] in self.control.hidden_sources():
                return None
            result = self._visible_payload(json.loads(row[0]), self.control.hidden_sources())
            if target != entity_id:
                result["redirected_from"] = entity_id
            return result

    def get_by_source(self, kind, source, source_key, generation=None):
        manifest = self.manifest(generation)
        pack = PACKS.get(kind)
        if not manifest or pack not in manifest["packs"] or source in self.control.hidden_sources():
            return None
        path = self.object_path(manifest["packs"][pack])
        with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute(
                "SELECT payload,id FROM entities WHERE source=? AND kind=? AND source_key=?",
                (source, kind, str(source_key)),
            ).fetchone()
            if not row:
                return None
            # A source-food route returns this exact assertion, even after canonical merges.
            result = self._visible_payload(json.loads(row[0]), self.control.hidden_sources())
            result["canonical_product_id"] = (
                manifest.get("redirects", {}).get(row[1], row[1]) if kind == "product" else None
            )
            return result

    def changes(self, after=0, limit=100):
        with self.control.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM changes WHERE seq>? ORDER BY seq LIMIT ?", (after, limit)
                )
            ]

    def status(self, manifest=None):
        manifest = self.current() if manifest is None else manifest
        with self.control.connect() as db:
            jobs = [
                dict(row)
                for row in db.execute(
                    "SELECT id,source,partition,operation,state,attempt,reason,due,heartbeat,checkpoint FROM jobs ORDER BY due DESC LIMIT 100"
                )
            ]
            sources = [
                dict(row)
                for row in db.execute(
                    "SELECT source,partition,release,parser_version,checked_at FROM source_state"
                )
            ]
        checked = {(row["source"], row["partition"]): row["checked_at"] for row in sources}
        sources = [
            {
                "source": state["source"],
                "partition": state["partition"],
                "release": state["release"],
                "parser_version": state["parser_version"],
                "checked_at": checked.get((state["source"], state["partition"])),
            }
            for state in (manifest or {}).get("sources", {}).values()
        ]
        for job in jobs:
            job["checkpoint"] = json.loads(job["checkpoint"]) if job["checkpoint"] else None
        worker_path = self.root / "control/worker-heartbeat.json"
        try:
            last_seen = json.loads(worker_path.read_text()).get("at")
        except (OSError, ValueError):
            last_seen = None
        return {
            "state": ("ready" if {"usda", "stores"}.issubset(manifest["packs"]) else "partial")
            if manifest
            else ("queued" if jobs else "empty"),
            "worker": {
                "last_seen_at": last_seen,
                "alive": isinstance(last_seen, (int, float)) and time.time() - last_seen < 300,
            },
            "catalog_generation": (manifest or {}).get("generation"),
            "packs": list((manifest or {}).get("packs", {})),
            "jobs": jobs,
            "sources": sources,
        }

    def sync(
        self,
        source,
        partition,
        release,
        records,
        complete=True,
        parser_version="1",
        cursor=None,
        fence=None,
        hook=None,
    ):
        """Stream a source partition into private pack copies; publish before acknowledging it."""
        with self.writer():
            self._recover()
            if source in self.control.denied_sources():
                raise ValueError("Source rights revoked")
            previous = self.current() or {"packs": {}, "sources": {}}
            checkpoint = previous["sources"].get(f"{source}:{partition}")
            if source == "all_the_places" and checkpoint:
                prior_run = (checkpoint.get("cursor") or {}).get("source_run")
                next_run = (cursor or {}).get("source_run")
                if prior_run and next_run and str(next_run) < str(prior_run):
                    raise ValueError("Source run regression requires review")
            if (
                checkpoint
                and checkpoint["release"] == release
                and checkpoint["parser_version"] == parser_version
                and checkpoint.get("cursor") == cursor
                and previous.get("registry_revision") == self._registry_revision()
            ):
                return {"manifest": previous, "changed": 0, "unchanged": 0, "no_change": True}
            private_copy_bytes = sum(
                self.object_path(path).stat().st_size
                for name, path in previous["packs"].items()
                if name != "usda"
            )
            if shutil.disk_usage(self.root).free < private_copy_bytes + 64 * 1024 * 1024:
                raise ValueError("Disk budget exceeded")
            with tempfile.TemporaryDirectory(dir=self.root / "staging") as directory:
                staging = Path(directory)
                connections = {}
                seen = set()
                events = []
                unchanged = 0
                counts = {}
                chain_names = {}
                metadata_dirty = set()
                field_metrics = {
                    "changed_groups": {},
                    "detail_candidates": {},
                    "detail_jobs_queued": 0,
                }

                def pack_db(pack):
                    if pack not in connections:
                        path = staging / f"{pack}.sqlite"
                        if pack in previous["packs"]:
                            shutil.copyfile(self.object_path(previous["packs"][pack]), path)
                        db = sqlite3.connect(path)
                        if pack not in previous["packs"]:
                            db.executescript(PACK_SCHEMA)
                        db.execute(
                            "CREATE INDEX IF NOT EXISTS entity_key ON entities(source,kind,source_key)"
                        )
                        db.execute(
                            "CREATE TABLE IF NOT EXISTS observations(kind TEXT,id TEXT,source_revision INTEGER,raw_hash TEXT,PRIMARY KEY(kind,id))"
                        )
                        connections[pack] = db
                    return connections[pack]

                try:
                    for record, reserved_identities in _identity_records(
                        records, self.control, source
                    ):
                        kind = record["kind"]
                        if kind not in PACKS or not str(record["source_key"]):
                            raise ValueError("Invalid source record")
                        source_key = str(record["source_key"])
                        if (kind, source_key) in seen:
                            raise ValueError("Duplicate source key")
                        seen.add((kind, source_key))
                        counts[kind] = counts.get(kind, 0) + 1
                        if len(seen) % 1000 == 0:
                            staging_size = sum(
                                p.stat().st_size for p in staging.iterdir() if p.is_file()
                            )
                            if (
                                staging_size > 50 * 1024**3
                                or shutil.disk_usage(self.root).free < 64 * 1024**2
                            ):
                                raise ValueError("Disk budget exceeded")
                        payload = dict(record["payload"])
                        entity_id = reserved_identities[kind, source_key]
                        # Source assertions retain their own row even after a reviewed canonical merge.
                        existing_assertion = (
                            pack_db(PACKS[kind])
                            .execute(
                                "SELECT id FROM entities WHERE source=? AND kind=? AND source_key=?",
                                (source, kind, source_key),
                            )
                            .fetchone()
                        )
                        if existing_assertion:
                            entity_id = existing_assertion[0]
                        if kind in ASSISTANCE_KINDS:
                            payload["kind"] = kind
                            prefix = "osm_assistance_" if kind.startswith("osm_") else "assistance_"
                            for relation in ("site", "service"):
                                if payload.get(relation + "_key"):
                                    payload[relation + "_id"] = reserved_identities[
                                        prefix + relation, str(payload[relation + "_key"])
                                    ]
                        if kind == "store" and payload.get("chain_key"):
                            chain_id = reserved_identities["chain", str(payload["chain_key"])]
                            payload["chain_id"] = chain_id
                            chain_names[chain_id] = (
                                payload.get("chain_name") or payload["chain_key"]
                            )
                            chain = {
                                "id": chain_id,
                                "name": payload.get("chain_name") or payload["chain_key"],
                                "country": "US",
                                "source_refs": [
                                    {"source_id": source, "record_id": str(payload["chain_key"])}
                                ],
                            }
                            chain["content_revision"] = content_hash(chain)
                            db = pack_db("stores")
                            db.execute(
                                "INSERT OR IGNORE INTO entities VALUES (?,?,?,?,?,?,?)",
                                (
                                    "chain",
                                    chain_id,
                                    source,
                                    partition,
                                    str(payload["chain_key"]),
                                    chain["content_revision"],
                                    encoded(chain),
                                ),
                            )
                        db = pack_db(PACKS[kind])
                        old = db.execute(
                            "SELECT payload FROM entities WHERE kind=? AND id=?", (kind, entity_id)
                        ).fetchone()
                        old_payload = json.loads(old[0]) if old else None
                        if (
                            kind
                            in {
                                "assistance_site",
                                "osm_assistance_site",
                                "assistance_service",
                                "osm_assistance_service",
                            }
                            and old_payload
                        ):
                            from .assistance import retain_source_update

                            payload = retain_source_update(old_payload, payload)
                        source_snapshot_payload = dict(payload)
                        if source == "open_food_facts":
                            observed = db.execute(
                                "SELECT source_revision,raw_hash FROM observations WHERE kind=? AND id=?",
                                (kind, entity_id),
                            ).fetchone()
                            old_time = (
                                observed[0]
                                if observed
                                else (old_payload or {}).get("last_modified_t")
                            )
                            old_source_hash = (
                                observed[1]
                                if observed
                                else content_hash(
                                    (old_payload or {}).get(
                                        "source_record", business_payload(old_payload or {})
                                    )
                                )
                            )
                            new_time = payload.get("last_modified_t")
                            source_hash = content_hash(
                                payload.get("source_record", business_payload(payload))
                            )
                            if old_time is not None and new_time is not None:
                                if new_time < old_time:
                                    unchanged += 1
                                    continue
                                if new_time == old_time and old_source_hash != source_hash:
                                    raise ValueError(
                                        "Equal source revision has conflicting content"
                                    )
                            if new_time is not None and (not observed or new_time != old_time):
                                db.execute(
                                    "INSERT OR REPLACE INTO observations VALUES (?,?,?,?)",
                                    (kind, entity_id, new_time, source_hash),
                                )
                                metadata_dirty.add(PACKS[kind])
                        # Missing source fields are not explicit deletions of known assertions.
                        if kind == "store" and old_payload:
                            for field, value in business_payload(old_payload).items():
                                if (
                                    payload.get(field) is None
                                    and value is not None
                                    and field not in {"source_membership", "identity_review"}
                                ):
                                    payload[field] = value
                            if isinstance(payload.get("address"), dict) and isinstance(
                                old_payload.get("address"), dict
                            ):
                                payload["address"] = {
                                    **old_payload["address"],
                                    **{
                                        k: v for k, v in payload["address"].items() if v is not None
                                    },
                                }
                            old_address = old_payload.get("address")
                            location_changed = (
                                field_groups(old_payload)["location"]["hash"]
                                != field_groups(payload)["location"]["hash"]
                            )
                            moved = False
                            if all(
                                isinstance(row.get(key), (int, float))
                                for row in (payload, old_payload)
                                for key in ("latitude", "longitude")
                            ):
                                moved = (
                                    max(
                                        abs(payload[key] - old_payload[key])
                                        for key in ("latitude", "longitude")
                                    )
                                    > 0.01
                                )
                            if location_changed and (
                                (
                                    old_address
                                    and payload.get("address")
                                    and old_address != payload["address"]
                                )
                                or moved
                            ):
                                payload["identity_review"] = {
                                    "reason": "location_changed",
                                    "candidate_address": payload.get("address"),
                                    "candidate_coordinates": payload.get("coordinates")
                                    or {
                                        "latitude": payload.get("latitude"),
                                        "longitude": payload.get("longitude"),
                                    },
                                }
                                payload["address"] = old_address
                                for location_field in (
                                    "coordinates",
                                    "latitude",
                                    "longitude",
                                    "location",
                                ):
                                    if location_field in old_payload:
                                        payload[location_field] = old_payload[location_field]
                                    else:
                                        payload.pop(location_field, None)
                            if not complete:
                                payload = {
                                    **business_payload(old_payload),
                                    **{k: v for k, v in payload.items() if v is not None},
                                }
                        if (
                            kind == "store"
                            and old_payload
                            and old_payload.get("field_enrichment_version")
                        ):
                            from .store_enrichment import retain_verified_update

                            payload = retain_verified_update(
                                old_payload,
                                payload,
                                source,
                                checked_at=time.time(),
                                source_snapshot=source_snapshot_payload,
                            )
                        if kind == "store":
                            from .store_quality import clean_store

                            payload = clean_store(payload)
                            refresh = plan_store_refresh(
                                old_payload, payload, time.time(), crawl_authorized=False
                            )
                            payload["field_refresh"] = {
                                "normalizer_version": refresh["normalizer_version"],
                                "groups": refresh["groups"],
                            }
                            for name in ("changed_groups", "detail_candidates"):
                                for group in refresh[name]:
                                    field_metrics[name][group] = (
                                        field_metrics[name].get(group, 0) + 1
                                    )
                            # Store group hashing ignores superficial source formatting and fetch clocks.
                            grouped_fields = {
                                field for fields in GROUP_FIELDS.values() for field in fields
                            }
                            semantic = {
                                k: v
                                for k, v in business_payload(payload).items()
                                if k not in grouped_fields
                            }
                            semantic["field_group_hashes"] = {
                                k: v["hash"] for k, v in refresh["groups"].items()
                            }
                            revision = content_hash(semantic)
                        else:
                            revision = self._revision(kind, payload)
                        if old_payload and old_payload["content_revision"] == revision:
                            unchanged += 1
                            continue
                        payload.update(id=entity_id, content_revision=revision)
                        payload.setdefault(
                            "source_refs",
                            [
                                {
                                    "source_id": source,
                                    "record_id": source_key,
                                    "release_id": release,
                                    "parser_version": parser_version,
                                }
                            ],
                        )
                        db.execute(
                            "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?)",
                            (
                                kind,
                                entity_id,
                                source,
                                partition,
                                source_key,
                                revision,
                                encoded(payload),
                            ),
                        )
                        events.append(
                            {
                                "id": entity_id,
                                "kind": kind,
                                "operation": "updated" if old else "created",
                                "revision": revision,
                            }
                        )
                    if not seen and not (cursor is not None and not complete):
                        raise ValueError("Empty snapshot cannot establish complete source coverage")
                    if complete:
                        for pack in set(connections):
                            db = connections[pack]
                            # Do not materialize complete product payloads here: a
                            # retained bulk export can contain millions of rows.
                            total = absent_count = 0
                            for kind, key in db.execute(
                                "SELECT kind,source_key FROM entities WHERE source=? AND partition=?",
                                (source, partition),
                            ):
                                total += 1
                                absent_count += kind != "chain" and (kind, key) not in seen
                            if absent_count >= 10 and absent_count > total * 0.2:
                                raise ValueError("Snapshot coverage drop requires review")
                            for kind, entity_id, key, raw in db.execute(
                                "SELECT kind,id,source_key,payload FROM entities WHERE source=? AND partition=?",
                                (source, partition),
                            ):
                                if kind == "chain" or (kind, key) in seen:
                                    continue
                                # Missing source membership never proves physical closure.
                                payload = json.loads(raw)
                                state = payload.get("source_membership", {})
                                if state.get("last_absence_run") == release:
                                    continue
                                since = state.get("missing_since", time.time())
                                n = state.get("missing_runs", 0) + 1
                                payload["source_membership"] = {
                                    "missing_runs": n,
                                    "missing_since": since,
                                    "last_absence_run": release,
                                    "status": "missing_from_source"
                                    if n >= 3 and time.time() - since >= 21 * 86400
                                    else "not_observed",
                                }
                                if kind == "product":
                                    payload["source_membership"]["status"] = (
                                        "withdrawn_from_complete_snapshot"
                                    )
                                revision = self._revision(kind, payload)
                                payload["content_revision"] = revision
                                db.execute(
                                    "UPDATE entities SET payload=?,revision=? WHERE kind=? AND id=?",
                                    (encoded(payload), revision, kind, entity_id),
                                )
                                events.append(
                                    {
                                        "id": entity_id,
                                        "kind": kind,
                                        "operation": "source_missing",
                                        "revision": revision,
                                    }
                                )
                    if "stores" in connections:
                        db = connections["stores"]
                        store_counts = {}
                        state_counts = {}
                        with self.control.connect() as control_db:
                            identity_map = {
                                (r[0], r[1]): r[2]
                                for r in control_db.execute(
                                    "SELECT source,source_key,id FROM identities WHERE kind='store'"
                                )
                            }
                        for (raw,) in db.execute("SELECT payload FROM entities WHERE kind='store'"):
                            row = json.loads(raw)
                            chain_id = row.get("chain_id")
                            redirected = False
                            for ref in row.get("source_refs", []):
                                identity = identity_map.get(
                                    (ref.get("source_id", source), str(ref.get("record_id", ""))),
                                    row["id"],
                                )
                                if identity != row["id"]:
                                    redirected = True
                            if redirected:
                                continue
                            if (
                                not chain_id
                                or row.get("lifecycle") == "closed"
                                or row.get("source_membership", {}).get("status")
                                == "missing_from_source"
                            ):
                                continue
                            store_counts[chain_id] = store_counts.get(chain_id, 0) + 1
                            address = row.get("address") or {}
                            region = row.get("state") or (
                                address.get("region") or address.get("state")
                                if isinstance(address, dict)
                                else None
                            )
                            scope = (
                                "DC"
                                if region == "DC"
                                else "states_50"
                                if region in US_STATES
                                else "unknown_or_territory"
                            )
                            state_counts.setdefault(chain_id, {})[scope] = (
                                state_counts.setdefault(chain_id, {}).get(scope, 0) + 1
                            )
                        for chain_id, raw in db.execute(
                            "SELECT id,payload FROM entities WHERE kind='chain'"
                        ).fetchall():
                            chain = json.loads(raw)
                            old_revision = chain["content_revision"]
                            chain["name"] = chain_names.get(chain_id, chain["name"])
                            chain["observed_store_count"] = store_counts.get(chain_id, 0)
                            chain["observed_count_scope"] = state_counts.get(chain_id, {})
                            chain["count_basis"] = "distinct_imported_sites_not_national_census"
                            chain["qualification"] = (
                                "qualifying_chain"
                                if store_counts.get(chain_id, 0) >= 2
                                else "candidate"
                            )
                            chain["content_revision"] = content_hash(business_payload(chain))
                            if old_revision != chain["content_revision"]:
                                db.execute(
                                    "UPDATE entities SET revision=?,payload=? WHERE kind='chain' AND id=?",
                                    (chain["content_revision"], encoded(chain), chain_id),
                                )
                                # Initial derived chains are introduced in this publication.
                                was_public = (
                                    self.get("chain", chain_id, previous.get("generation"))
                                    is not None
                                    if previous.get("generation")
                                    else False
                                )
                                events.append(
                                    {
                                        "id": chain_id,
                                        "kind": "chain",
                                        "operation": "updated" if was_public else "created",
                                        "revision": chain["content_revision"],
                                    }
                                )
                    for db in connections.values():
                        self._project_aliases(db, events)
                    packs = {}
                    for pack, db in connections.items():
                        if not any(PACKS[e["kind"]] == pack for e in events):
                            if pack in metadata_dirty:
                                db.commit()
                                db.close()
                                packs[pack] = self._seal(staging / f"{pack}.sqlite")
                            else:
                                db.close()
                            continue
                        db.execute("DELETE FROM search")
                        db.execute("DELETE FROM spatial")
                        for rowid, kind, entity_id, raw in db.execute(
                            "SELECT rowid,kind,id,payload FROM entities"
                        ):
                            payload = json.loads(raw)
                            db.execute(
                                "INSERT INTO search VALUES (?,?,?)",
                                (
                                    kind,
                                    entity_id,
                                    " ".join(str(payload.get(k, "")) for k in SEARCH_FIELDS),
                                ),
                            )
                            coordinates = (
                                payload.get("coordinates")
                                or payload.get("location")
                                or {
                                    "latitude": payload.get("latitude"),
                                    "longitude": payload.get("longitude"),
                                }
                            )
                            if (kind == "store" or kind in ASSISTANCE_KINDS) and isinstance(
                                coordinates, dict
                            ):
                                lat, lon = (
                                    coordinates.get("latitude", coordinates.get("lat")),
                                    coordinates.get("longitude", coordinates.get("lon")),
                                )
                                if (
                                    lat is not None
                                    and lon is not None
                                    and -90 <= lat <= 90
                                    and -180 <= lon <= 180
                                ):
                                    db.execute(
                                        "INSERT INTO spatial VALUES (?,?,?,?,?)",
                                        (rowid, lat, lat, lon, lon),
                                    )
                        db.commit()
                        db.close()
                        packs[pack] = self._seal(staging / f"{pack}.sqlite")
                    manifest = self._publish(
                        packs,
                        source,
                        partition,
                        release,
                        cursor,
                        parser_version,
                        events,
                        fence,
                        hook,
                    )
                    return {
                        "manifest": manifest,
                        "field_refresh": field_metrics,
                        "changed": sum(event["kind"] != "chain" for event in events),
                        "derived_changed": sum(event["kind"] == "chain" for event in events),
                        "unchanged": unchanged,
                        "no_change": not events,
                    }
                finally:
                    for db in connections.values():
                        db.close()

    @staticmethod
    def _revision(kind, payload):
        semantic = business_payload(payload)
        if kind == "store":
            grouped_fields = {field for fields in GROUP_FIELDS.values() for field in fields}
            semantic = {k: v for k, v in semantic.items() if k not in grouped_fields}
            semantic["field_group_hashes"] = {
                k: v["hash"] for k, v in field_groups(payload).items()
            }
        return content_hash(semantic)

    @staticmethod
    def _visible_payload(payload, denied):
        if not denied:
            return payload
        if "source_alternatives" in payload:
            payload["source_alternatives"] = [
                item
                for item in payload["source_alternatives"]
                if item.get("source_id") not in denied
            ]
        if "dataset_links" in payload:
            payload["dataset_links"] = [
                r
                for r in payload["dataset_links"]
                if r.get("source_id") not in denied
                and not (r.get("source_id") == "usda_snap_arcgis" and "usda_snap" in denied)
            ]
        if "field_evidence" in payload:
            evidence = payload["field_evidence"]
            hidden_ids = {r["id"] for r in evidence if r.get("source_id") in denied}
            payload["field_evidence"] = [r for r in evidence if r.get("source_id") not in denied]
            for field, state in payload.get("field_provenance", {}).items():
                state["assertion_ids"] = [
                    i for i in state.get("assertion_ids", []) if i not in hidden_ids
                ]
                if hidden_ids.intersection(state.get("supporting_ids", [])):
                    baseline = payload.get("field_baselines", {}).get(field, {})
                    if baseline.get("present") and baseline.get("source_id") not in denied:
                        payload[field] = baseline.get("value")
                    else:
                        payload.pop(field, None)
                    state.update(status="rights_restricted", supporting_ids=[], verified_at=None)
            payload["field_conflicts"] = [
                {**r, "assertion_ids": [i for i in r["assertion_ids"] if i not in hidden_ids]}
                for r in payload.get("field_conflicts", [])
            ]
            payload["field_baselines"] = {
                k: v
                for k, v in payload.get("field_baselines", {}).items()
                if v.get("source_id") not in denied
            }
            if (
                payload.get("field_provenance", {}).get("operating_status", {}).get("status")
                == "rights_restricted"
            ):
                payload.update(
                    permanently_closed=None,
                    operating_status="unknown",
                    lifecycle="unknown",
                    closure_reported_at=None,
                )
            payload["last_verified_at"] = max(
                (
                    r.get("verified_at")
                    for r in payload.get("field_provenance", {}).values()
                    if r.get("verified_at")
                ),
                default=None,
            )
        if "source_refs" in payload:
            payload["source_refs"] = [
                item for item in payload["source_refs"] if item.get("source_id") not in denied
            ]
        return payload

    def _alias_rows(self, catalog_db):
        # Reviewed corrections are small; never materialize a multi-million-product pack.
        rows = {}
        with self.control.connect() as db:
            for (raw,) in db.execute("SELECT payload FROM identity_decisions WHERE action='alias'"):
                decision = json.loads(raw)
                row = catalog_db.execute(
                    "SELECT kind,id,source,source_key,payload FROM entities WHERE source=? AND kind=? AND source_key=?",
                    (decision["source"], decision["kind"], decision["source_key"]),
                ).fetchone()
                if row:
                    rows[(row[0], row[1])] = row
                for identifier in (decision.get("previous"), decision["target"]):
                    if identifier:
                        target = catalog_db.execute(
                            "SELECT kind,id,source,source_key,payload FROM entities WHERE kind=? AND id=?",
                            (decision["kind"], identifier),
                        ).fetchone()
                        if target:
                            rows[(target[0], target[1])] = target
        return list(rows.values())

    def _project_aliases(self, catalog_db, events):
        rows = self._alias_rows(catalog_db)
        by_id = {(row[0], row[1]): row for row in rows}
        alternatives = {}
        denied = self.control.denied_sources()
        with self.control.connect() as control_db:
            mapping_rows = {
                (kind, old_id): control_db.execute(
                    "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                    (source, kind, key),
                ).fetchone()
                for kind, old_id, source, key, raw in rows
            }
            for kind, old_id, source, key, raw in rows:
                mapping = control_db.execute(
                    "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                    (source, kind, key),
                ).fetchone()
                if (
                    mapping
                    and mapping[0] != old_id
                    and (kind, mapping[0]) in by_id
                    and source not in denied
                ):
                    target = mapping[0]
                    visited = {old_id}
                    while (
                        mapping_rows.get((kind, target))
                        and mapping_rows[(kind, target)][0] != target
                    ):
                        if target in visited:
                            raise ValueError("Identity redirect cycle requires review")
                        visited.add(target)
                        target = mapping_rows[(kind, target)][0]
                    assertion = json.loads(raw)
                    assertion.pop("source_alternatives", None)
                    alternatives.setdefault((kind, target), []).append(
                        {"source_id": source, "record_id": key, "assertion": assertion}
                    )
            for kind, entity_id, source, key, raw in rows:
                payload = json.loads(raw)
                before = payload.get("source_alternatives")
                after = alternatives.get((kind, entity_id))
                if before == after:
                    continue
                if after:
                    payload["source_alternatives"] = after
                else:
                    payload.pop("source_alternatives", None)
                revision = self._revision(kind, payload)
                payload["content_revision"] = revision
                catalog_db.execute(
                    "UPDATE entities SET payload=?,revision=? WHERE kind=? AND id=?",
                    (encoded(payload), revision, kind, entity_id),
                )
                # Consolidate same-entity changes so change feeds have one final revision.
                matching = next(
                    (e for e in events if e["kind"] == kind and e["id"] == entity_id), None
                )
                if matching:
                    matching["revision"] = revision
                else:
                    events.append(
                        {
                            "id": entity_id,
                            "kind": kind,
                            "operation": "identity_review_applied",
                            "revision": revision,
                        }
                    )

    def _redirects(self, packs):
        redirects = {}
        with self.control.connect() as db:
            if not db.execute("SELECT 1 FROM identity_decisions LIMIT 1").fetchone():
                return redirects
            for pack, relative in packs.items():
                if pack == "usda":
                    continue
                with _sqlite(
                    self.object_path(relative).resolve().as_uri() + "?mode=ro", uri=True
                ) as catalog_db:
                    for kind, old_id, source, key, raw in self._alias_rows(catalog_db):
                        row = db.execute(
                            "SELECT id FROM identities WHERE source=? AND kind=? AND source_key=?",
                            (source, kind, key),
                        ).fetchone()
                        if (
                            row
                            and row[0] != old_id
                            and catalog_db.execute(
                                "SELECT 1 FROM entities WHERE kind=? AND id=?", (kind, row[0])
                            ).fetchone()
                        ):
                            redirects[old_id] = row[0]
        for origin in list(redirects):
            target = redirects[origin]
            visited = {origin}
            while target in redirects:
                if target in visited:
                    raise ValueError("Identity redirect cycle requires review")
                visited.add(target)
                target = redirects[target]
            redirects[origin] = target
        return redirects

    def assert_permitted(self, manifest, action=None):
        denied = self.control.hidden_sources(action) if action else self.control.denied_sources()
        if not denied:
            return
        for pack, relative in manifest["packs"].items():
            if pack == "usda":
                if denied & {"usda_fdc", "local_usda"}:
                    raise ValueError("Catalog includes rights-restricted data")
                continue
            with _sqlite(
                self.object_path(relative).resolve().as_uri() + "?mode=ro", uri=True
            ) as db:
                sources = {row[0] for row in db.execute("SELECT DISTINCT source FROM entities")}
                if sources & denied:
                    raise ValueError("Catalog includes rights-restricted data")
                for (raw,) in db.execute("SELECT payload FROM entities"):
                    payload = json.loads(raw)
                    if any(
                        item.get("source_id") in denied
                        for item in payload.get("source_alternatives", [])
                        + payload.get("field_evidence", [])
                        + payload.get("dataset_links", [])
                        + list(payload.get("field_baselines", {}).values())
                    ):
                        raise ValueError("Catalog includes rights-restricted source alternatives")

    def purge_revoked(self, *, quiesced=False):
        if not quiesced:
            raise ValueError("Restricted-data purge requires quiesced readers and idle worker")
        with self.writer():
            self._recover()
            denied = self.control.denied_sources()
            previous = self.current()
            if not previous or not denied:
                return previous
            packs = dict(previous["packs"])
            events = []
            with tempfile.TemporaryDirectory(dir=self.root / "staging") as directory:
                for pack, relative in list(packs.items()):
                    if pack == "usda":
                        if denied & {"usda_fdc", "local_usda"}:
                            del packs[pack]
                        continue
                    path = Path(directory) / f"{pack}.sqlite"
                    shutil.copyfile(self.object_path(relative), path)
                    with _sqlite(path) as db:
                        for source in denied:
                            for kind, key, revision in db.execute(
                                "SELECT kind,id,revision FROM entities WHERE source=?", (source,)
                            ).fetchall():
                                events.append(
                                    {
                                        "kind": kind,
                                        "id": key,
                                        "operation": "rights_removed",
                                        "revision": revision,
                                    }
                                )
                            db.execute(
                                "DELETE FROM search WHERE id IN (SELECT id FROM entities WHERE source=?)",
                                (source,),
                            )
                            db.execute(
                                "DELETE FROM spatial WHERE rowid IN (SELECT rowid FROM entities WHERE source=?)",
                                (source,),
                            )
                            db.execute("DELETE FROM entities WHERE source=?", (source,))
                    with _sqlite(path) as db:
                        self._project_aliases(db, events)
                        for kind, identity, raw in db.execute(
                            "SELECT kind,id,payload FROM entities"
                        ).fetchall():
                            old = json.loads(raw)
                            payload = self._visible_payload(json.loads(raw), denied)
                            if payload == old:
                                continue
                            revision = self._revision(kind, payload)
                            payload["content_revision"] = revision
                            db.execute(
                                "UPDATE entities SET payload=?,revision=? WHERE kind=? AND id=?",
                                (encoded(payload), revision, kind, identity),
                            )
                            db.execute("DELETE FROM search WHERE kind=? AND id=?", (kind, identity))
                            db.execute(
                                "INSERT INTO search VALUES (?,?,?)",
                                (
                                    kind,
                                    identity,
                                    " ".join(str(payload.get(k, "")) for k in SEARCH_FIELDS),
                                ),
                            )
                            events.append(
                                {
                                    "id": identity,
                                    "kind": kind,
                                    "operation": "rights_removed",
                                    "revision": revision,
                                }
                            )
                    packs[pack] = self._seal(path)
                sources = {
                    key: ack
                    for key, ack in previous["sources"].items()
                    if ack["source"] not in denied
                }
                published = self._publish(
                    packs,
                    "operator",
                    "rights",
                    "revoked",
                    None,
                    "1",
                    events,
                    source_snapshot=sources,
                )
            # Explicit quiescence authorizes removing incompatible historical payloads.
            self.assert_permitted(published)
            allowed = {published["generation"]}
            referenced = set(published["packs"].values())
            for path in (self.root / "generations").glob("*.json"):
                candidate = json.loads(path.read_text())
                try:
                    self.assert_permitted(candidate)
                except ValueError:
                    path.unlink()
                    continue
                allowed.add(candidate["generation"])
                referenced.update(candidate["packs"].values())
            for path in (self.root / "objects/catalogs").glob("*.sqlite"):
                if path.relative_to(self.root).as_posix() not in referenced:
                    path.unlink()
            for source in denied:
                if source and all(
                    character.islower() or character.isdigit() or character == "_"
                    for character in source
                ):
                    path = self.root / "downloads" / source
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
            if denied & {"usda_fdc", "local_usda"}:
                (self.root / "foods.sqlite").unlink(missing_ok=True)
            return published

    def rollback(self, generation, apply=False, hook=None):
        with self.writer():
            self._recover()
            manifest = self.manifest(generation)
            self.validate_manifest(manifest)
            self.assert_permitted(manifest)
            result = {"generation": generation, "apply": apply, "packs": list(manifest["packs"])}
            if apply:
                current = self.current() or {"packs": {}}
                events = []
                for kind in PACKS:
                    before = {r["id"]: r for r in self.records(kind, current.get("generation"))}
                    after = {r["id"]: r for r in self.records(kind, generation)}
                    for key in before.keys() | after.keys():
                        if before.get(key) != after.get(key):
                            events.append(
                                {
                                    "id": key,
                                    "kind": kind,
                                    "operation": "rollback" if key in after else "removed",
                                    "revision": after.get(key, {}).get("content_revision"),
                                }
                            )
                published = self._publish(
                    manifest["packs"],
                    "operator",
                    "rollback",
                    generation,
                    None,
                    "1",
                    events,
                    hook=hook,
                    source_snapshot=manifest["sources"],
                    identity_snapshot=manifest,
                )
                # _publish normally preserves untouched packs; rollback must remove absent packs too.
                result["published_generation"] = published["generation"]
            return result

    def backup(self, destination):
        destination = Path(destination)
        with self.writer():
            self._recover()
            if destination.exists():
                raise ValueError("Backup destination must be new")
            destination.mkdir(parents=True)
            try:
                with (
                    self.control.connect() as src,
                    _sqlite(destination / "control.sqlite") as dst,
                ):
                    src.backup(dst)
                current = self.current()
                if current:
                    self.assert_permitted(current, action="can_redistribute")
                (destination / "generations").mkdir()
                (destination / "objects/catalogs").mkdir(parents=True)
                referenced = set()
                for path in (self.root / "generations").glob("*.json"):
                    manifest = json.loads(path.read_text())
                    try:
                        self.assert_permitted(manifest, action="can_redistribute")
                    except ValueError:
                        continue
                    shutil.copyfile(path, destination / "generations" / path.name)
                    referenced.update(manifest["packs"].values())
                for relative in referenced:
                    shutil.copyfile(self.object_path(relative), destination / relative)
                if self.current():
                    atomic_json(destination / "current.json", self.current())
                return {
                    "status": "complete",
                    "generation": (self.current() or {}).get("generation"),
                }
            except BaseException:
                shutil.rmtree(destination)
                raise

    def restore(self, backup):
        backup = Path(backup)
        if self.current():
            raise ValueError("Restore requires an empty installation")
        with self.writer():
            manifest = json.loads((backup / "current.json").read_text())
            existing_denied = self.control.denied_sources()
            with _sqlite(
                (backup / "control.sqlite").resolve().as_uri() + "?mode=ro", uri=True
            ) as restored_control:
                if (
                    restored_control.execute("PRAGMA user_version").fetchone()[0]
                    != CONTROL_SCHEMA_VERSION
                ):
                    raise ValueError("Unsupported backup control schema")
                if restored_control.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Backup control integrity failed")
                backup_denied = {
                    row[0]
                    for row in restored_control.execute(
                        "SELECT source FROM rights WHERE denied=1 OR (retention_until IS NOT NULL AND retention_until<=?)",
                        (time.time(),),
                    )
                }
            for source in backup_denied:
                self.control.restrict_source(source)
            # Validate the bundle read-only before copying any business payloads to the target.
            bundle = object.__new__(Platform)
            bundle.root = backup
            bundle.control = self.control
            bundle.validate_manifest(manifest)
            bundle.assert_permitted(manifest)
            for path in (backup / "generations").glob("*.json"):
                historical = json.loads(path.read_text())
                bundle.validate_manifest(historical)
                bundle.assert_permitted(historical)
            for name in ("generations", "objects"):
                shutil.copytree(backup / name, self.root / name, dirs_exist_ok=True)
            self.validate_manifest(manifest)
            with (
                _sqlite(
                    (backup / "control.sqlite").resolve().as_uri() + "?mode=ro", uri=True
                ) as src,
                self.control.connect() as dst,
            ):
                src.backup(dst)
                dst.execute(
                    "UPDATE jobs SET state='cancelled',reason='restored_offline' WHERE state NOT IN ('succeeded','failed','cancelled')"
                )
            for source in existing_denied:
                self.control.restrict_source(source)
            atomic_json(self.root / "current.json", manifest)
            return {"status": "restored", "generation": manifest["generation"]}

    def gc(self, quiesced=False, now=None):
        if not quiesced:
            raise ValueError("GC requires quiesced API readers and idle worker")
        with self.writer():
            self._recover()
            now = time.time() if now is None else now
            with self.control.connect() as db:
                if db.execute(
                    "SELECT 1 FROM jobs WHERE state IN ('running','leased','validating','publishing') AND expires>?",
                    (now,),
                ).fetchone():
                    raise ValueError("Worker must be idle")
            manifests = sorted(
                (self.root / "generations").glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            current = (self.current() or {}).get("generation")
            retained = [
                p
                for i, p in enumerate(manifests)
                if i < 2 or now - p.stat().st_mtime < 86400 or p.stem == current
            ]
            referenced = {v for p in retained for v in json.loads(p.read_text())["packs"].values()}
            removed = 0
            for path in manifests:
                if path not in retained:
                    path.unlink()
            for path in (self.root / "objects/catalogs").glob("*.sqlite"):
                if path.relative_to(self.root).as_posix() not in referenced:
                    path.unlink()
                    removed += 1
            return {"removed_objects": removed}

    def iter_records(
        self, kind, generation=None, last="", query=None, lat=None, lon=None, radius_km=10
    ):
        """Bounded-memory, deadline-limited native scan with FTS/spatial candidates."""
        import math
        import re

        manifest = self.manifest(generation)
        pack = PACKS.get(kind)
        if not manifest or pack not in manifest["packs"]:
            return
        path = self.object_path(manifest["packs"][pack])
        with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            deadline = time.monotonic() + 5
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            joins = []
            where = ["e.kind=?", "e.id>?"]
            if kind == "store":
                where.append(
                    "coalesce(json_extract(e.payload, '$.directory_scope.status'),'included') != 'excluded'"
                )
            params = [kind, last]
            redirects = manifest.get("redirects", {})
            if redirects:
                where.append("e.id NOT IN (" + ",".join("?" for _ in redirects) + ")")
                params.extend(redirects)
            denied = self.control.hidden_sources()
            if denied:
                where.append("e.source NOT IN (" + ",".join("?" for _ in denied) + ")")
                params.extend(sorted(denied))
            if query:
                terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
                if not terms:
                    return
                if len(terms) > 20:
                    raise ValueError("Too many search terms")
                joins.append("JOIN search ON search.id=e.id AND search.kind=e.kind")
                where.append("search MATCH ?")
                params.append(" AND ".join(f'"{term}"*' for term in terms))
            if lat is not None and lon is not None:
                delta_lat = radius_km / 110.5
                delta_lon = min(
                    180, radius_km / (111.32 * max(0.00001, math.cos(math.radians(lat))))
                )
                joins.append("JOIN spatial s ON s.rowid=e.rowid")
                where.extend(["s.max_lat>=?", "s.min_lat<=?"])
                params.extend([lat - delta_lat, lat + delta_lat])
                # Crossing the antimeridian needs two ranges; exact geodesic filter follows.
                if lon - delta_lon >= -180 and lon + delta_lon <= 180:
                    where.extend(["s.max_lon>=?", "s.min_lon<=?"])
                    params.extend([lon - delta_lon, lon + delta_lon])
            sql = (
                "SELECT e.payload FROM entities e "
                + " ".join(joins)
                + " WHERE "
                + " AND ".join(where)
                + " ORDER BY e.id"
            )
            for row in db.execute(sql, params):
                yield self._visible_payload(json.loads(row[0]), denied)
