# 01 — Repository-aware implementation map

## Reviewed baseline

Primary repository: `callum-baillie/bord-food-api`, main at `13ba74e56f9d383edb2cfc57d4020d2c9943705e`.
Consumer: `callum-baillie/our-recipes`, main at `843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb`.

These are reference points, not a request to check out old code. Before editing, inspect current branch, working-tree changes, applicable `AGENTS.md`, dependency files, migrations and tests. Preserve unrelated work and avoid mass refactors. Static review is not a runtime bug report.

## What directly changes the design

| Existing file | Observed behavior | Required treatment |
|---|---|---|
| `AGENTS.md` | Small Python/FastAPI/SQLite service; immutable published catalog; mocked routine tests | Preserve these constraints. Mutable scheduling/identity state is a separate control plane, not the serving catalog. |
| `bord_food_api/__main__.py` | `serve` imports local files or downloads before `uvicorn.run`; no source files can abort startup | Move bootstrap into a resumable worker. Serving and status must work with no catalog. Preserve explicit `import`/`refresh` commands. |
| `settings.py` | Four USDA dataset names; `AUTO_DOWNLOAD` defaults true; DB path `/data/foods.sqlite` | Add versioned runtime config with clear legacy precedence. Do not repurpose `DATASETS` for store providers. |
| `api.py` | Health and status depend on a USDA DB connection; X-Api-Key; 16 KiB body bound; 5s SQL budget | Add `/live`, `/ready` and `/v1/system/status` independent of USDA. Preserve `/health`’s legacy catalog-readiness behavior. |
| `catalog.py` | `fdc_id` primary key, compressed payload, SQLite FTS5 and read-only connections | Retain compatibility module. New source records have typed identities, not fabricated FDC IDs. |
| `catalog.py::barcode_key` | Accepts 8–14 numeric characters then pads | Keep permissive legacy search separate from checksum-validated identity joins. |
| `importer.py` | Stages new DB; validation; fsync and atomic replace | Extend generation publishing; update only a private copy/build. Do not edit a file serving queries. |
| `download.py` | Official release discovery; cached URLs plus SHA256; whole ZIP download | Add centralized network policy, conditional requests, resource ceilings, checkpointing and no-op release detection. |
| `Dockerfile` | Python 3.12, UID/GID 10001, healthcheck uses `/health` with long startup grace | Healthcheck must use liveness once bootstrap is async. Retain nonroot operation and multiarchitecture compatibility. |
| `tests/test_api.py`, `test_cli.py`, `test_download.py`, `test_importer.py` | Existing regression test structure | Extend fixtures; intentional empty-start behavior change gets new tests, not deletion of unrelated tests. |
| `scripts/smoke-docker.py` and `scripts/verify-bord.mts` | Container and real Bòrd-provider verification entry points | Inspect/update to exercise explicit fixture bootstrap and compatibility with no live egress. |

The complete existing importer/catalog source was available in the earlier reviewed plan; the baseline tree remains the same SHA. This review rechecked CLI, settings, API, download, Docker and root guidance directly. See [R01–R07].

## Bòrd seams rechecked

`src/lib/domain/food-data.ts` validates GTIN-8/12/13/14 and checksum, and defines providers `local`, `open_food_facts`, `usda_fdc`. Its selection schema retains source and expected GTIN. `src/lib/services/food-data-service.ts` currently has a fixed two-provider registry and hashes provider/operation/key for cache identity. `src/lib/domain/list-settings.ts` contains supermarket profiles with editable names, notes and aisle sections, without a canonical external store field in that input schema. [R08–R10]

Use these seams. Do not assume that old architecture prose about auth or profile permissions still describes the current app: inspect current authorization code when implementing the companion change. Respect the current actor, origin, idempotency and route guards rather than rebuilding authentication.

## Proposed module destination

```text
bord_food_api/
  api.py, catalog.py, importer.py, download.py, settings.py, __main__.py
  domain/       # typed IDs, chains/stores, source records, evidence, quantities
  control/      # migrations, jobs, leases, policy, stable identity assignments
  ingestion/    # transport, manifests, stage/diff, validation, publication
  sources/      # usda, alltheplaces, snap, openfoodfacts, open_prices, foodkeeper
  scheduler/    # due planner, single-worker loop, retries, checkpoint recovery
  queries/      # generation-bound read-only repositories
  routes/       # native v1, operational read views, legacy adapter
  crawlers/     # explicit allowlisted adapters; isolated optional dependencies
  maps/         # discovery records, rights, asset verification/render boundary
```

Create modules when a vertical slice needs them. No placeholder tree is evidence of completed functionality. Pin new dependencies using the project’s existing conventions; do not adopt an unrelated framework or full upstream application.

## Repository completion boundaries

API-only work must provide everything necessary for Bòrd to connect, plus a contract smoke test or companion handoff. Actual Bòrd code is a separate task set and needs a writable authorized checkout. No plan promises that editing one repository changes a running container in the other.

`AGENTS.additions.md` is a proposed concise addition, not a replacement for the current file. The `plans/` tree should remain documentation-only and must not be mounted into `/imports`.
