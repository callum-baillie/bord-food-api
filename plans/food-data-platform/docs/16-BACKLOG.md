# 16 — Implementation backlog

All tasks start **not_started**. IDs are local plan identifiers, not GitHub issues. See `progress/tasks.json` for machine-readable dependencies. Source live verification is a separate field, never a substitute for coding tests.

## F01 — Audit actual checkout and preserve current behavior
Phase: **P00**. Dependencies: none. Repository: bord-food-api.
Inspect AGENTS, current diffs, API schema and Bòrd seams. Record baseline and deviations without resetting user work.
Acceptance matrix: T06
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## F02 — Install offline test boundary and compatibility fixtures
Phase: **P00**. Dependencies: F01. Repository: bord-food-api.
Inject HTTP/clock/storage; fail source-network access in routine tests; freeze legacy payloads.
Acceptance matrix: T01, T06, T28, T42
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## F03 — Define domain schemas, strict IDs and source rights
Phase: **P01**. Dependencies: F02. Repository: bord-food-api.
Implement source/transport distinction and provenance; unknown fields stay unknown; preserve legacy validator separately.
Acceptance matrix: T28, T29, T32
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## F04 — Control migrations and stable identity registry
Phase: **P01**. Dependencies: F03. Repository: bord-food-api.
Add persistent ID allocation, source aliases, reversible match decisions and migration tests.
Acceptance matrix: T13, T14, T15
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## F05 — Immutable objects and generation publication
Phase: **P01**. Dependencies: F04. Repository: bord-food-api.
Prepare immutable snapshots and generation crosswalk; atomic manifest switch with recovery protocol.
Acceptance matrix: T23, T24, T26
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## F06 — Idempotent source state and pending watermarks
Phase: **P01**. Dependencies: F05. Repository: bord-food-api.
Use fenced leases, pending/committed checkpoint states and replay-safe publication/change events.
Acceptance matrix: T17, T19, T22, T24
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## O01 — Configuration and effective-policy validation
Phase: **P02**. Dependencies: F03. Repository: bord-food-api.
Production bulk-only vs offline modes; source/crawl independent controls and legacy precedence.
Acceptance matrix: T01, T05, T33
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## O02 — Nonblocking startup and pack readiness
Phase: **P02**. Dependencies: F05, O01. Repository: bord-food-api.
API opens without data; separate liveness, legacy health and required-pack readiness.
Acceptance matrix: T01, T02, T04, T40
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## O03 — Durable scheduler and worker roles
Phase: **P02**. Dependencies: F06, O01. Repository: bord-food-api.
Single-host scheduling, deduplication, jitter, retry budgets, shutdown and source kill switches.
Acceptance matrix: T03, T22, T33
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## O04 — Safe downloader and resumable artifacts
Phase: **P02**. Dependencies: O01. Repository: bord-food-api.
Conditional requests, validator-bound partial resume, bounded redirects/bytes/decompression and source allowlists.
Acceptance matrix: T07, T25, T35
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## O05 — Operator CLI and sanitized status
Phase: **P02**. Dependencies: O02, O03. Repository: bord-food-api.
Network-free plan, source check, sync/cancel, worker/status and safe error diagnostics.
Acceptance matrix: T01, T41
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S01 — USDA adapter and legacy catalog adoption
Phase: **P03**. Dependencies: O04, F05. Repository: bord-food-api.
Reuse existing importer and discovery; per-type release identity, safe adoption and release-level no-op detection.
Acceptance matrix: T04, T05, T06, T07
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S02 — ATP pinned-output acquisition
Phase: **P03**. Dependencies: O04, F06. Repository: bord-food-api.
Resolve permitted outputs; record actual successful-run dates; no inferred freshness from retrieval. Implement selected-spider and explicitly selected published-archive U.S.-grocery modes with per-member scope and safe streaming; no retailer host auto-approval.
Acceptance matrix: T08, T16
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S03 — Roster and field-group semantic diff
Phase: **P03**. Dependencies: S02, F04. Repository: bord-food-api.
Deterministic versioned normalization/hash; minimal work scheduling and complete-scope absence rules.
Acceptance matrix: T08, T09, T10, T21
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S04 — Store lifecycle and identity reconciliation
Phase: **P03**. Dependencies: S03. Repository: bord-food-api.
Source absence is not closure; ambiguous mergers/relocations withheld with review reasons.
Acceptance matrix: T11, T12, T13, T14, T15
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S05 — Optional SNAP CSV/resolver adapter
Phase: **P03**. Dependencies: S04. Repository: bord-food-api.
Official current resource discovery or reviewed override; bounded CSV parser, qualified SNAP evidence and unresolved status on access failure.
Acceptance matrix: T11, T15, T32
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## S06 — Chain/store queries and pagination
Phase: **P03**. Dependencies: S04, O02. Repository: bord-food-api.
Nearby/state/text filters, count scope, stable cursor and field freshness; no hidden direct crawling.
Acceptance matrix: T27, T40
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## P01 — OFF JSONL baseline and filtered pack
Phase: **P04**. Dependencies: O04, F03, F05. Repository: bord-food-api.
Stream JSONL into isolated optional pack; preserve source revisions/formulation/rights; countries filter explicit.
Acceptance matrix: T20, T29, T32
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## P02 — OFF delta continuity and full reconciliation
Phase: **P04**. Dependencies: P01, F06. Repository: bord-food-api.
Validate intervals, overlap, correction and missed retention; fallback to complete compatible baseline.
Acceptance matrix: T17, T18, T19, T20
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## P03 — Canonical product search and batch resolve
Phase: **P04**. Dependencies: P01, S06. Repository: bord-food-api.
Identifier-first matches; no name-only merge; no source-network call during queries.
Acceptance matrix: T28, T29, T30
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## P04 — USDA source-backed measures
Phase: **P04**. Dependencies: S01, F03. Repository: bord-food-api.
Expose valid food portions and exact source facts; never fabricate density or package size.
Acceptance matrix: T29
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## E01 — Public retail evidence model and enrichment
Phase: **P04**. Dependencies: P03, S06. Repository: bord-food-api.
Distinct catalog/listing/price/stock/placement and pure read enrichment contract.
Acceptance matrix: T30, T31
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## E02 — Optional Open Prices adapter
Phase: **P04**. Dependencies: E01, O04. Repository: bord-food-api.
Snapshot diff; related-record joins; source revision and historical conditions; proof media off.
Acceptance matrix: T30, T31, T32
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## E03 — Optional FoodKeeper adapter
Phase: **P04**. Dependencies: O04, F03. Repository: bord-food-api.
Resolve official JSON resource, parse source guidance and conditions; no personal expiry guarantee.
Acceptance matrix: T29, T32
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## C01 — Crawler policy enforcement and frontier
Phase: **P05**. Dependencies: O03, O04, S03. Repository: bord-food-api.
Optional Scrapy or equivalent bounded layer; robots, host/contact/reuse approvals, per-host rate/queue budgets.
Acceptance matrix: T33, T35
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## C02 — Woodman’s map-link pilot offline implementation
Phase: **P05**. Dependencies: C01. Repository: bord-food-api.
Synthetic fixture distinguishes PDF layout, geographic map and advertising; no live run.
Acceptance matrix: T34
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## M01 — Map registry and permitted asset handling
Phase: **P05**. Dependencies: C02, F03. Repository: bord-food-api.
Rights pending link-only, safe existing-asset endpoints; rendering optional dependency network sandboxed.
Acceptance matrix: T32, T34, T35
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## M02 — Placement/map version invalidation
Phase: **P05**. Dependencies: M01, E01. Repository: bord-food-api.
New asset version does not silently reuse stale aisle anchors; fallback ordering remains separate.
Acceptance matrix: T30, T34
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## A01 — Native contracts, OpenAPI and client fixture export
Phase: **P06**. Dependencies: S06, P03, P04, E01, M01. Repository: bord-food-api.
Generate authoritative FastAPI schema and reviewed TS shapes; validate bounds/error/capability semantics.
Acceptance matrix: T27, T40
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## B01 — Bòrd companion specification and contract smoke
Phase: **P06**. Dependencies: A01. Repository: bord-food-api handoff / our-recipes companion.
Deliver exact configuration/migration/client handoff; companion writes only when checkout authorized.
Acceptance matrix: T06, T36, T37, T38, T39
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## D01 — Upgrade and rollback migrations
Phase: **P07**. Dependencies: S01, F05, O02. Repository: bord-food-api.
No example seeding; adopt old catalog; compatible backup restore and dry-run migration.
Acceptance matrix: T04, T05, T23, T24
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## D02 — Docker, Compose and Unraid role wiring
Phase: **P07**. Dependencies: O03, D01. Repository: bord-food-api.
Same-image API/worker roles or supervised single-container option; liveness healthcheck; no runtime data baked into image.
Acceptance matrix: T01, T02, T03, T42
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## D03 — Storage budgeting, backups and safe cleanup
Phase: **P07**. Dependencies: D01, F06. Repository: bord-food-api.
Protect identity and current-generation objects; quiesced/lease-aware GC; no expired restricted data restored.
Acceptance matrix: T25, T26, T41
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## Q01 — Full offline regression and crash tests
Phase: **P08**. Dependencies: D02, D03, E02, E03, M02, B01. Repository: bord-food-api.
Run all applicable matrix tests, explicit unavailable-environment labels and performance fixtures.
Acceptance matrix: T01, T42
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## Q02 — Final security, provenance and documentation review
Phase: **P08**. Dependencies: Q01. Repository: bord-food-api.
Inspect implementation vs claims; no stubs declared live; complete operators guide and source gates.
Acceptance matrix: T30, T31, T32, T33, T35, T41
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## X01 — Overture release/schema adapter
Phase: **V1.1**. Dependencies: Q02. Repository: bord-food-api.
Implement only in next explicitly selected milestone; country/taxonomy/STAC release and source-overlap fixtures.
Acceptance matrix: Define in the explicitly authorized later milestone.
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## X02 — OFF Parquet alternate bootstrap
Phase: **V1.1**. Dependencies: Q02. Repository: bord-food-api.
Optional alternate raw format with semantic parity and cost/bandwidth measurement.
Acceptance matrix: Define in the explicitly authorized later milestone.
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## X03 — Regional OSM/IndoorEqual geometry
Phase: **V1.1**. Dependencies: Q02. Repository: bord-food-api.
Only where actual useful map geometry and compatible license is confirmed.
Acceptance matrix: Define in the explicitly authorized later milestone.
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## I01 — Bòrd private purchase evidence and package-aware planning
Phase: **V2**. Dependencies: Q02. Repository: bord-food-api handoff / our-recipes companion.
Reuse existing transaction/deficit pipeline; checkout vs consumed cost and leftovers; no public receipt sharing.
Acceptance matrix: Define in the explicitly authorized later milestone.
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.

## I02 — Entitled live retailer and basket scenarios
Phase: **V2**. Dependencies: I01. Repository: bord-food-api handoff / our-recipes companion.
Actual permissions/costs first; demand-bound calls, comparable coverage and explicit unknown prices.
Acceptance matrix: Define in the explicitly authorized later milestone.
Completion evidence: changed paths, commands and results, contract checks, remaining source/activation gates. No status change is earned by creating an empty module.
