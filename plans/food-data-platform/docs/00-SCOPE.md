# 00 — Scope, outcomes and resolved choices

## Outcome

Evolve the existing USDA mirror into a reusable catalog for foods, products, U.S. grocery banners, individual stores, public retail evidence and optional map assets. After runtime bootstrap it answers local queries while independently checking for updates. Bòrd remains useful when an upstream source or optional integration fails.

The delivery target is **V1 of this expansion**, not “all previous roadmap ideas fully implemented.” V1 includes the acquisition framework, durable scheduler, sources listed below, store/product APIs, maps/retail-evidence substrate, migration, status tooling, offline tests and a precise companion integration handoff. V2 contains household optimization and advanced indoor routing. Optional-source activation is distinct from implementation completeness.

## Required V1 implementation

- Preserve the existing USDA search/detail contract, data provenance and deployment compatibility; introduce nonblocking empty startup and per-pack readiness.
- Implement stable identities, source policies, immutable catalog generations, snapshot diffing, changed-record processing, rollback and resumable jobs.
- Implement USDA and All The Places as the default runtime bulk sources, including selected-spider and explicitly selected nationwide bulk-archive discovery modes. Implement SNAP current-CSV ingestion/resolution as an optional supplement because its live download URL/schema must be resolved from official resources; a blocked SNAP source never blocks other packs.
- Implement optional Open Food Facts JSONL bootstrap plus delta-capable synchronization with gap recovery; Parquet bootstrap is an optional alternate parser, not a requirement to download both formats.
- Implement optional Open Prices JSONL and FoodKeeper JSON adapters; these activate only under explicit source policy. Retain Overture/OSM adapter specifications and extension interfaces; they are V1.1 additions, not empty “working” stubs.
- Add chain/store/food/product queries, provenance/capabilities, public dated retail-evidence models, source-backed measures and stateless shopping enrichment. No universal stock promise.
- Implement a crawler framework and an offline-tested, bounded **Woodman’s map-link discovery pilot**. Add a Walmart locator-adapter specification, not an anti-bot bypass. No crawler is activated during development or CI.
- Provide operational CLI commands, durable source/job status, safe configuration, automatic updates, Unraid/Compose templates, legacy migration and tests.
- Provide a generated client contract, mock fixtures and exact Bòrd integration instructions. When Bòrd is not an authorized writable checkout, stop at the handoff for its changes while completing the API.

## Out of V1

Nationwide census guarantees; whole-chain product × branch crawls; automated checkout; community sharing of receipts; a new household database in the API; mandatory AI; phone indoor positioning; routing from an unverified floor-plan image; automatic deployment. Live Kroger/Walmart/Instacart activation is gated research, not required for the open-data core. Existing Instacart functionality stays in Bòrd.

## Geography and chain eligibility

U.S. 50 states by default; D.C. included but counted separately. Territories are an explicit configuration choice, never inferred from a corporation’s global count. Include supermarket banners, substantial grocery superstores and warehouse clubs with separate format tags. Exclude convenience-only, fuel-only, pharmacy-only and dollar stores from the default grocery directory.

The chain browse view defaults to at least two observed active grocery locations. Single-store organizations may remain as unresolved source candidates during reconciliation, but must not be promoted as qualifying chains without evidence. A user-created custom store in Bòrd is always allowed. Store search can separately expose approved independent stores when configured; default chain ranking excludes singletons.

Banner, parent corporation, buying group and franchise operator are not interchangeable. Report a source’s corporate count separately from the number of verified branch records imported. Never add parent and child totals together or treat the 300-entry research inventory as a census.

## Empty means empty business catalog, not missing software metadata

Schema definitions, source descriptors, adapters, migration history and policy metadata can ship. Chain/store/product facts, map files, downloaded source archives and example rows cannot be automatically inserted into production. Counts are zero before publication. The documentation examples and candidate chain registry are excluded from runtime seed paths and production images.

## Acceptance rather than prediction

Success is established by explicit fixture and migration tests, source provenance, recoverable publication, stable IDs, source-specific freshness and honest unavailable states. Mark an adapter `implemented_offline_tested` separately from `live_verified`. No credential, source freshness or coverage claim is inferred from a passing mocked test.

Schedules and resource limits in this pack are engineering defaults, not vendor contracts or measured performance. Source terms and operator budgets can only tighten them. See the current repository constraints [R01–R07] and source evidence [S01–S16] in `18-SOURCE-LEDGER.md`.
