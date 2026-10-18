# Bòrd Food API — implementation plan

**Prepared:** 17 October 2026. **Package version:** 1.0.0. **Status:** implementation specification, not implemented software.

Build an empty-start, self-updating, self-hosted food and supermarket reference service **inside the existing `callum-baillie/bord-food-api` repository**. Keep `callum-baillie/our-recipes` (Bòrd) as the owner of household recipes, pantry, purchases and decisions.

## Start here

Extract the ZIP **at the root of `bord-food-api`**. It adds only `plans/food-data-platform/`; it does not overwrite application files, `AGENTS.md`, configuration, or a database. Give Codex the contents of [prompts/01-IMPLEMENT-V1.md](prompts/01-IMPLEMENT-V1.md).

The implementation prompt authorizes code and deterministic tests, **not running retailer crawlers, importing live datasets into production, spending money, deploying, or pushing to GitHub**. Runtime acquisition is implemented now and activated later. A fresh installed service has no catalog records and no sample records; its configured runtime then discovers/downloads bulk data, validates it and publishes it. Approved crawlers run only after their independent activation gates are satisfied.

This package supersedes the earlier expansion blueprint **on implementation scope, empty startup, scheduler, incremental synchronization and activation policy**. Earlier chain research remains a dated, incomplete reference, not a verified national census.

## Recommended read order

1. [00 — Scope and decisions](docs/00-SCOPE.md), [01 — Repository audit](docs/01-REPOSITORY-AUDIT.md).
2. [02 — Architecture](docs/02-ARCHITECTURE.md), [03 — Data model](docs/03-DATA-MODEL.md).
3. [04 — Sources](docs/04-SOURCES.md), [05 — Incremental sync](docs/05-INCREMENTAL-SYNC.md), [06 — Scheduler](docs/06-SCHEDULER.md).
4. [07 — Crawlers and maps](docs/07-CRAWLERS-AND-MAPS.md), [08 — API](docs/08-API.md), [09 — Bòrd integration](docs/09-BORD-INTEGRATION.md).
5. [10 — Bootstrap and migration](docs/10-BOOTSTRAP-AND-MIGRATION.md), [11 — Security and rights](docs/11-SECURITY-AND-RIGHTS.md), [12 — Deployment](docs/12-DEPLOYMENT.md).
6. [13 — Acceptance tests](docs/13-TESTS.md), [14 — Roadmap](docs/14-ROADMAP.md), [15 — Decisions and risks](docs/15-DECISIONS-AND-RISKS.md), [16 — Backlog](docs/16-BACKLOG.md).
7. [17 — Example data](docs/17-EXAMPLES.md), [18 — Sources and verification](docs/18-SOURCE-LEDGER.md), [19 — Operations UX](docs/19-OPERATIONS-UX.md), [20 — Data dictionary](docs/20-DATA-DICTIONARY.md).

8. [21 — Nationwide discovery and coverage growth](docs/21-COVERAGE-GROWTH.md).

## Package contents

| Folder | Purpose |
|---|---|
| `docs/` | Design, acquisition, migration, tests and implementation scope |
| `prompts/` | Main Codex prompt, continuation/review, Bòrd companion and later activation prompts |
| `configs/` | Proposed production/offline policy, field schedules, source registry and Compose examples |
| `contracts/` | OpenAPI blueprint, empty relational DDL and change-event definitions |
| `schemas/` | JSON Schemas for example records, policy and fixture contracts |
| `examples/real/` | Dated Walmart chain and Coralville store examples; **not seeds** |
| `examples/reference-v0.1/` | Original example files preserved byte-for-byte |
| `examples/synthetic/` | Clearly labeled offline synchronization and empty-start scenarios |
| `reference/chain-research/` | Prior registry: 120 ranked records and 180 unverified candidates |
| `progress/` | Task status, evidence and decision-log templates, initially unimplemented |
| `tools/` | Offline package validation only; no downloader or crawler |

## Concrete defaults

Retain Python/FastAPI/SQLite/FTS5; no mandatory Redis/PostgreSQL/browser/LLM. Keep published catalog files immutable. Use a durable SQLite control database and one worker/scheduler role. Publish a generation manifest atomically. Prefer All The Places outputs to running its spiders. Use either selected ATP outputs or the optional nationwide bulk-archive discovery profile; no manually seeded chain list is required. Use scheduled release discovery, native deltas when trustworthy, normalized hash comparison otherwise, and targeted detail refreshes. Low-volatility address/coordinates are not recrawled routinely but remain correctable and periodically revalidated.

Runtime defaults after implementation: automatic **bulk-only** bootstrap and updates for the configured core sources; direct retailer crawling, paid APIs, map rehosting and optional large/copyleft data packs remain disabled until explicitly enabled. Development/CI use an offline policy. See `docs/10-BOOTSTRAP-AND-MIGRATION.md` for precedence of existing `AUTO_DOWNLOAD=false` and local imports.

## Verification boundary

Repository files and public source documentation were inspected. The food API was reviewed at `13ba74e56f9d383edb2cfc57d4020d2c9943705e`; Bòrd integration seams at `843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb`. Codex must inspect its actual checkout and reconcile drift, not reset it to these commits. No source crawler, live bulk import, entitled retailer request, production deployment or application test was run for this package. `PACKAGE-QA.json` records only the checks actually performed on these plan artifacts.

All commands/configuration described as proposed require implementation first. Do not run the proposed acquisition commands against the unmodified application.
