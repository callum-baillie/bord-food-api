# V1 implementation evidence — 17 October 2026

For current API, companion, live-source and later-roadmap status, see [PLAN-STATUS.md](PLAN-STATUS.md). This document preserves the original offline implementation boundary.

This is API repository implementation and offline verification, based on `main` at `13ba74e56f9d383edb2cfc57d4020d2c9943705e`, with an uncommitted worktree. Existing README/environment/setup work and the plan package were preserved. Historical live-USDA evidence in the root `VERIFICATION.md` predates this expansion and does not verify these adapters.

Subsequent operation: the owner separately authorized the 18 October release and Tower deployment. Its live core-source evidence is recorded in [Tower deployment](TOWER-DEPLOYMENT.md); the boundaries below describe the original 17 October implementation run.

## Delivered API work

- P00: legacy USDA compatibility tests, synthetic fixtures, routine-test socket/DNS egress guard.
- P01: versioned durable control/identity ledger, audited reversible aliases, generation-bound redirects and assertions, immutable SQLite packs, atomic pointer publication, pending checkpoints and recoverable outbox.
- P02: empty nonblocking HTTP, separate liveness/readiness, bulk-only policy, durable deduplicated jobs, leases/fencing, retries, conditional/resumable bounded downloads, `serve`/`worker`/supervised `run`, CLI and sanitized status.
- P03: USDA adoption/release reuse, selected/archive ATP parsing, optional SNAP resolver/CSV, semantic snapshots, versioned field groups and periodic audits, source absence candidates, stores/chains queries and generation cursors.
- P04: optional OFF JSONL and contiguous deltas, full reconciliation, revision conflict handling, products/identifiers/measures, historical Open Prices joins, FoodKeeper, and pure local shopping enrichment.
- P05: disabled crawler policy/frontier, bounded sitemap/JSON-LD extraction, synthetic Woodman's map-link pilot, rights-gated existing assets and map-version placement invalidation. No crawler was run.
- P06: generated FastAPI OpenAPI, shared identifier/response fixtures, reviewed TypeScript starter and exact Bòrd handoff.
- P07: local legacy migration, recoverable rollback, consistent backup/restore, rights controls, quiesced cleanup, Docker/Compose/Unraid role wiring.
- P08: regression, crash, schema/contract, local container and read-only Bòrd provider checks, recorded in the plan verification log.

Important files are `bord_food_api/{control,platform,domain,refresh,runtime,transport,sources,native_api,crawlers}.py`, existing compatibility/config/CLI modules, tests, `contracts/`, and `docs/platform-runtime.md`. No serving catalog was edited in place. No production data directory or household database was used as a fixture.

## Commands and observed results

Final results are recorded in `plans/food-data-platform/progress/verification-log.md`. The baseline had 34 passing tests. The final full run passed **209 tests in 15.36 seconds**, with one upstream deprecation warning. The local Python environment is 3.14.7; the synthetic container runs Python 3.12.

| Final check | Observed result |
|---|---|
| `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q` | 209 passed, one warning |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 91 files already formatted |
| `python scripts/export-contracts.py --check` | Generated OpenAPI matches FastAPI |
| Adjacent TypeScript compiler, strict standalone starter check | Exit 0 |
| Synthetic Docker smoke and network-disabled empty-image inspection | Passed |
| Existing Bòrd USDA provider against synthetic loopback service | Passed |
| Both Compose configurations and Unraid XML parse | Passed |
| Plan package validator and `git diff --check` | Passed; 13 package check groups |

The local Docker smoke builds the separate `bord-food-api:v1-offline-test` image, mounts a fully offline source policy, and exercises startup, search/details, authentication, failed import preservation, atomic replacement and persisted restart. Its containers and temporary volume are removed. A separate `--network=none` image inspection confirms empty `/data` and `/imports`, with no fixtures or plans under `/app`. This is local container verification, not an Unraid deployment or image publication.

`scripts/smoke-bord-offline.py` starts a temporary loopback API with six synthetic USDA foods and imports the adjacent Bòrd checkout's actual USDA provider read-only. Observed: two generic results, one recognized selected-detail nutrient, two branded results, exact barcode match. The first harness attempt omitted `/fdc/v1` and failed; the corrected harness passed. No Bòrd source, UI, migration or household data changed.

`scripts/benchmark-offline.py` measured 1,000 synthetic stores, one synthetic chain, concurrency one, and 50 requests per query type on this Linux host with eight visible logical CPUs. Build: 2.169 seconds; lookup p95: 6.756 ms; store-search p95: 35.212 ms; peak process RSS: 65,592 KiB; sampled peak staging: 4,575,232 bytes; final disk: 5,219,593 bytes; unchanged replay: 1,000; source bytes and retailer detail requests: zero. No national-data or 2-vCPU/4-GiB performance claim is made. RSS uses Linux process `VmHWM`; an initial `ru_maxrss` observation included an inherited high-water mark and was replaced with the explicit process measurement.

The single upstream Starlette/httpx deprecation warning is retained; it is not a test failure.

## Activation and companion boundaries

No live dataset download/import, retailer crawl, authenticated retailer call, paid call, Git push, remote deployment or Unraid deployment was performed. Runtime bulk acquisition code is implemented; operator installation and first live publication remain separate activation work. Default sources are USDA and the reviewed selected ATP outputs. Optional OFF/SNAP/Open Prices/FoodKeeper, map-byte acquisition, direct crawling and commercial sources remain independently gated.

OFF changed-product exports are not complete CDC. Incremental alignment requires a verified baseline extraction boundary. Without it the adapter publishes an explicitly labeled snapshot-only pack and never invents a delta watermark. Gaps/conflicts degrade the source or require full reconciliation. SNAP can remain `source_location_unresolved` until official current discovery or a reviewed override succeeds. ATP's actual successful output run is retained separately from fetch/check time; pinned output health, upstream revisions and nationwide coverage remain unverified live.

Automatic identity merges by name or proximity are withheld. Suspected relocation preserves former site facts and requests review. Source absence does not prove closure. Existing local USDA data remains pinned unless explicitly moved to managed refresh. Source policy can independently prevent acquisition/display/export; retention revocation requires operator cleanup with readers quiesced. Restoring an older bundle must use current operator rights policy, since a backup cannot predict a later external revocation.

Bòrd companion implementation is **not performed**. `contracts/BORD-HANDOFF.md`, generated OpenAPI and shared fixtures are delivered; the starter client typechecks. Profile migration/link/unlink, source revision confirmation UI, catalog-only egress denial, cache isolation, purchase/actor/origin guards and full companion release checks remain work for `04-BORD-COMPANION.md` in an authorized companion session. Existing provider compatibility smoke does not establish those changes.

V1.1 Overture, alternate Parquet bootstrap and OSM geometry, plus V2 household optimization/paid connectors, remain out of scope. Map rendering is not enabled; V1 discovers official links and serves only already-permitted, verified existing bytes. A PDF/image is never represented as a routing graph.
