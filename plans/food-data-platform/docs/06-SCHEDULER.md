# 06 — Durable scheduler, job model and recovery

## Process model

Use one worker with a scheduler loop and a persistent SQLite job queue. API workers are read-only business-query processes. A host/Docker restart must not erase next-due times or create a stampede. Optional external cron runs `sync --due --once` instead of the resident worker; the lease enforces a single owner in either mode.

Implement `serve`, `worker`, and supervised `run` roles. `worker --once` processes one bounded due batch and exits with machine-readable status. No runtime dependency on Codex, an LLM, a desktop app, or an external scheduler service. Codex builds the scheduler; it is not the scheduler.

## Job types

`discover_release`, `download_artifact`, `parse_snapshot`, `apply_delta`, `reconcile_source`, `resolve_identity`, `build_pack`, `validate_generation`, `publish_generation`, `refresh_store_fields`, `discover_map`, `fetch_map_asset`, `maintenance_backup`, `maintenance_gc`.

A source acquisition run can use phases inside one job initially rather than create a complex DAG engine. Persist a checkpoint at every expensive boundary. Publish as a serialized critical section; do not hold SQLite transactions during network I/O.

## States

```text
queued -> leased -> running -> validating -> publishing -> succeeded
                \-> retry_wait -> queued
                \-> blocked_by_policy / blocked_by_credentials / quarantined
                \-> failed / cancelled
```

`no_change` is a successful outcome with zero business changes, not a failure. `partial` applies to source coverage/job reports, not silently to a supposedly complete published snapshot. Each state transition has a timestamp, attempt, reason code and safe evidence summary.

## Lease and fencing

Store `lease_owner`, `lease_token` (monotonic fencing token), `lease_expires_at`, `heartbeat_at`, attempt and checkpoint. Proposed lease 120 seconds, heartbeat every 20 seconds. Work checks its fence before side effects/publication. Reacquiring an expired lease issues a new token, so an old delayed worker cannot publish after losing ownership. Clock comparisons use UTC; duration measurement uses monotonic clocks inside a process.

A unique active-job dedupe key prevents duplicate bootstrap jobs. A global publisher lock plus generation compare-and-swap prevents two pack writers from replacing each other. Initially permit one heavy ingest at a time, with at most two total downloads and one request per retailer host. These are configurable bounds, not performance promises.

## Retry, rate and budget rules

- Retry transient transport/timeouts/429/5xx with exponential backoff plus full jitter; honor Retry-After and stricter source rules. Proposed max 5 attempts and 24h maximum automatic delay before showing intervention status.
- Do not retry 401/403/CAPTCHA loops as transport errors. Mark credential/policy/access failure, pause the source and retain existing data. Do not rotate proxies or identities to evade a refusal.
- Cache verified response validators and negative discovery results. Bounded retries count toward byte/request budgets.
- Enforce source, host, installation and optional account limits centrally across workers; rate configuration in a crawler library alone is insufficient.
- Unknown paid-call price/billing scope -> connector cannot auto-enable. Default spend budget is zero for commercial providers.
- Preflight disk space and recheck streaming byte/expanded byte ceilings. Unknown content length is not unlimited permission. Cancel and delete incomplete safe staging on ceiling breach.

## Scheduling and restarts

The due planner emits at most one acquisition job for each source partition’s effective version/due interval. On restart requeue eligible abandoned jobs after lease expiration and recover prepared generations. Preserve policy and checkpoint state. Stagger first roster checks and long field audits deterministically from installation/source/entity IDs; this avoids synchronized crawls across households.

A missed daily run is coalesced into one current check. For verified delta feeds, replay necessary contiguous intervals; do not submit one duplicate full snapshot job for each missed day. For a source changed while a previous job runs, complete/reconcile one version then enqueue the next, rather than race both.

A paused source prevents **new** network work and cancels queued network steps. In-flight transfer cancellation is cooperative and bounded. Policy revocation is rechecked at step boundaries; data retention revocation additionally queues restricted-data cleanup according to the rights policy.

## Incremental cursors and job durability

Store candidate cursors separately from published cursors. An interrupted parse cannot acknowledge an entire source release. Resume downloads only if URL, entity validator and expected range align; if an HTTP server ignores Range, start over safely rather than appending a whole file.

Parser resume needs stable source framing. For gzip snapshots, a decompressed line offset is not random-access by itself; either rescan efficiently with idempotent staging or checkpoint normalized chunks. Never seek an arbitrary compressed byte offset and claim to resume valid JSONL.

## Operations visibility

Expose safe job ID, type, source, state, phase, completed/total units when known, transferred bytes, changed/unchanged/quarantined counts, last success and next due. Unknown totals produce indeterminate progress—not a fabricated percentage or completion time. Report old-source timestamps separately from recent download time.

CLI operator actions: list/status, explain-due, pause/resume, retry a failed job, cancel, inspect a safe change report, activate source policy and run a dry plan. V1 uses no browser-based write administration. Bòrd can display a sanitized read-only status summary.
