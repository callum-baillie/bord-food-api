# 14 — Dependency-ordered roadmap

## V1 implementation phases

| Phase | Work | Exit gate |
|---|---|---|
| P00 | Reconcile actual checkout, preserve work, freeze compatibility and source/network policy | Baseline evidence and offline test boundaries recorded. |
| P01 | Control schema, stable IDs, immutable objects, manifest publication, recovery | Crash/fencing/rollback tests pass with synthetic packs. |
| P02 | Nonblocking empty start, runtime config, persistent scheduler, CLI and status | Empty/offline and automatic mocked bootstrap behave correctly. |
| P03 | USDA release updates and ATP roster ingestion, optional SNAP parser/resolver, store queries | Core catalog can be built and incrementally updated entirely from fixtures. |
| P04 | OFF bootstrap/deltas, product identity/search, measures, optional Open Prices/FoodKeeper | Gap recovery, source provenance and local enrichment tested. |
| P05 | Bounded crawler framework, Woodman’s discovery fixture adapter, maps/evidence interfaces | Crawlers remain disabled; enforcement and extraction tested offline. |
| P06 | API OpenAPI/types, Bòrd mock contract, companion handoff and optional authorized integration | Legacy provider passes; native integration contract and migration instructions complete. |
| P07 | Docker/Unraid, adoption/migration, backup/restore, resource and security checks | Available local smoke tests pass; deployment-only checks are explicitly pending. |
| P08 | Full regression, risk review, operational docs and implementation report | V1 code/test/documentation acceptance met; no fake live verification. |

P04 and P05 may run in parallel after P03 contracts are frozen. A single author owns shared schema/publication changes to avoid inconsistent implementations. Phase prompts in `prompts/phases/` provide scoped goals and tests. Task dependencies in `progress/tasks.json` are authoritative for execution order; the task list is a proposed backlog, not a report of implemented code.

## After V1 implementation

Runtime activation is a separate operation: deploy the tested build with an empty dedicated data directory or adopt an existing catalog, choose source policy, enable automatic bulk ingestion and inspect actual results. Only later enable a selected approved crawler. Completion of that step changes `live_source_verified`, not whether deterministic code was implemented. Do not silently activate paid programs to satisfy a completion checkbox.

V1.1 may add Overture Places with current release/schema handling, Parquet OFF bootstrap, additional retailer locator adapters and genuine regional OSM geometry after useful incremental coverage is shown. Every added source uses the same policy, stable ID, publication and differential update pipeline.

V2 adds Bòrd-owned purchase-to-store history, package-aware checkout versus consumed cost, leftover coupling, bounded multi-store scenarios, optional entitled live retail lookups, reviewed substitution and offline read bundles. Route-finding requires real walkable geometry. Offline write replay requires its own conflict/security design. The API must not duplicate pantry deficits or household transactions to deliver these features.

## Honest stopping rules

An unavailable live source does not justify abandoning offline adapter implementation when schema fixtures and documented input exist. Conversely, a missing permission or undocumented schema is not solved by fabricating an endpoint. Implement the known contract, show `blocked_source_resolution` or `unsupported`, record the precise operator gate, and complete the rest. Never replace a difficult required algorithm with a permanent stub while declaring V1 complete.
