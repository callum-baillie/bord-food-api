# 19 — Operator experience and Bòrd-facing status

No separate frontend application is required in the food API. V1 supplies CLI operations, OpenAPI, sanitized status and structured progress that Bòrd can display through its server. Avoid implementing a public anonymous administration console.

## First-run states

Show `Empty → Queued → Downloading → Validating → Building → Publishing → Ready`. Source failures produce `Retry scheduled`, `Needs source resolution`, `Needs policy approval`, `Disk budget exceeded` or `Paused`, not a generic spinner forever. Report source, transfer bytes and row counts where measured. Do not invent an ETA from bytes when remaining transform time is unknown.

Core packs progress independently; existing USDA food lookup can be ready while stores are still bootstrapping. In offline mode show “No data loaded; acquisition disabled by policy” and a pointer to CLI documentation. This is expected, not a crash or a populated empty census.

## Regular operation

Status includes current generation, last successful source run, actual source dates, next scheduled check, recent change summary, last error class and whether a crawler/live source is disabled by choice. Important numbers: new/changed/unchanged entities, detail requests avoided, deferred/withheld records, missing-from-source candidates, source bytes and disk usage. Counts must declare source/entity/scope to avoid mixing pharmacies with branches.

Offer views for source-level freshness and field-level status: address last verified, hours unknown/stale, no map found, map rights pending, prices historical. “Store verified” is not one blanket boolean. An old address can remain displayed with its date while stale hours are not used for an unqualified open-now assertion.

## CLI actions

The proposed commands are specified in Deployment and Bootstrap. Required actions include source list/check, sync plan/run/cancel, scheduler pause/resume, status, reviewed identity correction, source policy validation, import local artifact, generation inspect/rollback and backup/restore. Dry-run planning must not fetch metadata: use local state and clearly report what a later network check would determine. A networked metadata check is a separate explicit operation.

Show effective policy precedence, registered versus imported sources, selected geography, required packs, source/crawl allowlists and current execution role. Secrets and signed URLs are redacted. Changes to policy are auditable and require operator access; a read key never enables a source.

## Bòrd integration UX

Store selection searches the local API, displays source date and permits a manual custom store when unavailable. Linking does not rename a user’s profile or reorder aisles. A brief source-status panel explains unavailable optional enrichment. The reviewed food picker shows actual USDA/OFF authority and distinguishes pack versus portion facts.

A new map version should request review of pinned placements. Missing maps do not disable shopping. Provide accessible textual department/aisle ordering rather than a map-only workflow. Offline bundle reading is a later feature; do not silently replay writes in the existing PWA.
