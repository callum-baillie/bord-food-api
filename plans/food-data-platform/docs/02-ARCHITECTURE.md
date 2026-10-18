# 02 — Architecture and publication protocol

## Keep the deployed system small

Use the existing Python image in two roles: read API and durable worker/scheduler. Default Compose uses two containers with separate CPU/memory budgets and one local SSD-backed volume. For Unraid’s one-container preference, implement a supervised `run` command that manages these two processes, reaps children and forwards shutdown; do not start a scheduler per Uvicorn worker. `serve` alone never starts an implicit worker. Both layouts share the same code and durable job model.

SQLite handles control and catalog storage. FTS5 provides text search; an RTree candidate index plus exact distance filtering handles nearby stores. DuckDB/PyArrow is an optional ingestion dependency for Parquet, not a mandatory server. No GPU, Redis, broker, Postgres or browser is required for the core. This retains the repository’s small immutable-catalog approach [R01, R05, R06].

## Boundaries

```text
Bulk source descriptors -> bounded downloader -> staging + raw evidence
                                                |
Optional approved crawler -> normalized changes -> identity decisions
                                                |
                               validated immutable catalog objects
                                                |
                               generation manifest (atomic pointer)
                                                |
                 legacy FDC endpoints + native API + status/change feed
                                                |
                                     Bòrd server client
                                                |
                   private pantry / purchases / preferences / planning
```

The read API never downloads arbitrary user URLs or executes crawlers. It can expose the current operational state. Source enablement is a CLI/operator task in V1. Household demand must not turn normal GETs into hidden paid calls.

## Disk layout

```text
/data/
  control/control.sqlite             # mutable: jobs, source policy, identities
  objects/catalogs/<sha256>.sqlite    # immutable pack snapshots
  generations/<generation-id>.json   # immutable compatible manifest
  current.json                       # sole active-generation pointer
  downloads/<source>/<release>/      # bounded raw archives and manifests
  staging/<job-id>/                   # private writable build; never served
  assets/<sha256>/<variant>           # only permitted map/media bytes
  cache/live.sqlite                  # optional rights/TTL-bounded live cache
  backups/                           # operator recovery bundles
  foods.sqlite                       # existing legacy file, initially preserved
```

Objects referenced by more than one generation are not duplicated. Do not hard-link an old SQLite file into staging and modify it: copy/reflink-with-copy-on-write or use SQLite backup to create a private file. Never mutate an object under `objects/catalogs/`.

## Control versus published state

The control DB owns job state, adapter config, source watermarks, raw source memberships, identity assignments and merge/split decisions. It may use WAL on a local filesystem. API business queries never join a live-changing identity table to an old catalog.

Each published pack contains the identity assignments and crosswalks relevant to its records. Cross-pack references are validated against the compatible manifest. `registry_revision` records which identity ledger snapshot was used. A global monotonic identity revision alone does not prove compatibility: validate actual references and any redirects in the generation.

A job can allocate an ID before publication. That allocation remains reserved even if publication fails, but no corresponding business entity is visible until a valid pack is published. Never reuse discarded IDs.

## One publication transaction, two durable domains

There is no atomic transaction spanning SQLite plus a filesystem pointer. Use an explicit recoverable prepare/publish/finalize protocol:

1. Acquire the single writer/publisher fence. Capture the current generation and normalized config/filter version.
2. Download/parse into private staging. Persist job checkpoints and proposed next source watermarks, not active watermarks.
3. Build or copy affected packs. Apply normalized changes and targeted FTS updates; preserve unchanged packs by reference.
4. Validate schema, integrity, foreign keys, counts, source coverage, provenance and rights. Check that the base generation has not changed.
5. Close all writers; checkpoint/close any WAL sidecars; fsync object files and their directory. Calculate hashes and move to content-addressed paths.
6. Write immutable generation manifest, fsync it, record `prepared_generation` and pending source acknowledgments in control state.
7. Write a temporary pointer on the same filesystem, fsync it, atomically replace `current.json`, then fsync the parent directory. This is the publication point.
8. In a short control transaction finalize job success, acknowledge pending watermarks and append committed change notifications. Store generation ID as the idempotency key.
9. On restart, reconcile a prepared generation against the active pointer. If it is active, finalize exactly once. If not active, retry publication or abandon staging without advancing watermarks.

The actual execution is at-least-once. Unique keys, monotonic revisions and generation acknowledgments provide idempotent effects; never advertise magical exactly-once delivery.

## Readers and old generations

Each API request resolves `current.json` once and opens all needed immutable objects from that manifest. Pagination cursors include generation, filter fingerprint and last sort key. A later page can use the old generation while retained; otherwise return `409 CURSOR_EXPIRED` and a restart instruction, not silently combine generations.

Never perform GC merely by age or by assuming an open file descriptor makes path reuse safe. In V1, periodic GC runs in an explicit maintenance window with the worker idle and read-service readers quiesced, or uses a proven cross-process reader lease implementation. Retain at least two successful generations, 24 hours of cursor visibility, and any objects pinned by active jobs/readers. Asset and contractual retention rules can require stricter behavior. Under disk pressure fail/preflight an import rather than delete active objects.

## No-op and freshness-only updates

Keep `content_revision` and `last_observed_in_source_run` distinct. A recheck of an already committed source release/interval can update last-checked status in control without a new catalog generation. When a genuinely new source release or delta watermark is acknowledged, publish a lightweight new generation manifest referencing unchanged pack objects, then finalize its source checkpoint. This also applies to an interval with zero eligible changed rows: no entity/index rewrite or business change event is necessary, but the new acknowledgment is recoverable with the manifest. Canonical record content hashes stay stable. On material change publish changed pack objects and entity change-feed entries.

A response’s source-freshness layer may be read from control only if it does not change entity identity/content or imply unverified facts; label it `last_feed_check`, not `verified_at`. Generation-bound business fields remain immutable.

## Tradeoff

Snapshot copying can still incur file I/O even when only a few records change. V1 optimizes outbound requests and normalization/index work, and avoids replaying unchanged packs; it does not claim all storage writes are O(changed rows). Measure before considering a different storage architecture.
