# Implementation decisions

Implementation decisions follow the original template table; actual checkout drift and justified choices are recorded below.

| Date | Task/ADR | Decision | Evidence | Downstream tests |
|---|---|---|---|---|

## 2026-10-17 implementation execution

- Baseline: `main` at `13ba74e56f9d383edb2cfc57d4020d2c9943705e`. Preserve existing `.env.example`, README and untracked documentation/plans. No production data file is used for tests or modified.
- Execution map: F01–F02 compatibility/network boundary; F03–F06 immutable platform/control; O01–O05 worker/transport; S01–S06 directory sources; P01–E03 optional food/evidence sources; C01–M02 disabled crawlers/maps; A01/B01 generated contract and companion handoff; D01–D03 operations; Q01–Q02 offline acceptance and review.
- The main implementation prompt explicitly permits parallel module ownership after shared contracts stabilize. Root owns control/publication; independent agents own parsers, native API/maps, and runtime/transport.
- V1 packs use a versioned SQLite entity table with FTS5 and spatial RTree plus typed kind, source namespace, content revision and JSON payload. USDA retains its exact existing SQLite schema and payload normalization. This avoids rewriting compatibility code and keeps optional licensed sources independently removable.
- Identity alias decisions are explicit and reversible. New source keys allocate permanent IDs; automatic cross-source/name/proximity merges are withheld. Substantial location changes preserve the former site facts and add review evidence.
- Bòrd is available for read-only inspection; this repository task does not authorize companion writes. Deliver generated contracts and a separate companion handoff. No claim of companion UI implementation.

- Complete source coverage is distinct from complete fields: missing values in a store feed retain prior assertions. Source absence advances only for a distinct comparable validated release, and never proves closure.
- Group-normalized store facts ignore presentation/fetch noise. OFF maintains a separate per-record source clock in its private pack, so a timestamp-only update does not rewrite facts but an older correction still cannot overwrite newer evidence.
- Reviewed canonical merges retain source assertions; transitive redirects are frozen in each generation. Identity editing shares the publisher lock. Rollback publishes a new generation with the selected generation's sources/crosswalk, and atomically recoverable checkpoint replacement.
- Rights are per action. Retention expiry/revocation blocks reads and export; display denial can retain bytes while hiding records. Backup/restore and rollback reject forbidden payloads, including embedded alias assertions. Cleanup requires actual reader quiescence.
- HTTP generation selection uses a request context snapshot. Native queries cannot mix pointers during publication/rollback; control-only feed checks and job metrics may remain fresh.
- OFF unproven extraction boundaries produce a labeled snapshot-only pack, not a fabricated baseline watermark. A verified operator/source boundary is required for native-delta alignment. SNAP retains unresolved status when official current-resource discovery cannot be established.
- Documentation's plan validator now accepts evidence-bearing implementation progress rather than requiring every task to remain not_started. Its original formatting/lint defects were fixed; the manifest is refreshed for modified plan progress artifacts, without changing reference data.
- Docker was used only for explicit local synthetic smoke/empty-image verification under an offline source policy. No remote deployment, Unraid deployment, image push or source acquisition was performed.
- Final offline evidence: 209 tests passed; Ruff, formatting, generated OpenAPI, TypeScript starter, existing Bòrd USDA provider and local synthetic container checks passed. Concurrent control initialization is serialized before WAL setup. Restore prevalidates the control schema before copying objects. OFF gaps attempt one full baseline recovery in the same job, with safe fixed status reasons and no checkpoint advance before publication.
- All 35 main V1 tasks have API implementation/handoff evidence: 34 completed offline and B01 handoff complete. Companion T36–T39, every live activation and five later-phase tasks remain explicitly unperformed. External operator configuration/secrets must be backed up separately and current rights applied during restore.
