# Verification log

The original package contained no application-test evidence. The implementation evidence below records this run separately from the package's historical `PACKAGE-QA.json`.

| Task | Commit | Command | Result | Fixture/source | Limitation |
|---|---|---|---|---|---|

## Implementation run — 2026-10-17, baseline HEAD 13ba74e

| Task | Command | Actual result | Corpus / limitation |
|---|---|---|---|
| F01/F02 | `.venv/bin/python -m pytest -q` | 34 passed, one Starlette deprecation warning | Existing synthetic fixtures and mocked downloads; baseline before edits |
| F01 | `.venv/bin/ruff check .` | failed: 3 pre-existing validator issues | EXE001, I001, FURB167 in plan validator; no application lint issues |
| F04–F06 | `.venv/bin/python -m pytest tests/test_platform.py tests/test_api.py -q` | 35 passed, 1 failed | New actual process-crash tests pass; native global validation handler broke one legacy validation response, assigned for correction |

All runtime acquisition in this run uses temporary fixtures and mocked transports. No live dataset download, crawler, paid request, deployment or Git push was run.

## Final API implementation verification — 2026-10-17

Baseline remains `main@13ba74e56f9d383edb2cfc57d4020d2c9943705e`; implementation is an uncommitted worktree. Commands ran from the API repository. Python checks use `.venv` (Python 3.14.7); Docker uses Python 3.12. No real serving catalog or companion household database was changed.

| Tasks | Actual command | Actual result | Boundary |
|---|---|---|---|
| F01–Q02 API scope | `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q` | **209 passed, 1 warning in 15.36s** | Synthetic fixtures/mocked transports; routine external DNS/socket guard enabled |
| Q02 | `PATH="$PWD/.venv/bin:$PATH" ruff check .` | All checks passed | Includes repaired pre-existing plan-validator lint defects |
| Q02 | `PATH="$PWD/.venv/bin:$PATH" ruff format --check .` | 91 files already formatted | Repository Python formatting |
| A01 | `PATH="$PWD/.venv/bin:$PATH" python scripts/export-contracts.py --check` | OpenAPI contract matches FastAPI | Temporary empty offline installation |
| A01/B01 | `../our-recipes/node_modules/.bin/tsc --noEmit --strict --target ES2022 --module nodenext --moduleResolution nodenext --skipLibCheck --lib ES2022,DOM contracts/bord-catalog-client.ts` | Exit 0 | Starter client only; not a companion application typecheck |
| B01/T06 | `BORD_SOURCE_DIR="$PWD/../our-recipes" .venv/bin/python scripts/smoke-bord-offline.py` | `genericResults=2`, `detailNutrients=1`, `brandedResults=2`, `barcodeMatched=true` | Actual existing USDA provider, six synthetic foods, loopback HTTP; companion checkout read-only |
| D02/Q01 | `BORD_SMOKE_IMAGE=bord-food-api:v1-offline-test .venv/bin/python scripts/smoke-docker.py` | PASS: boot, search, details, auth, failed import, atomic replacement, persisted restart | Local temporary containers/volume, explicit offline source policy; cleanup completed; no remote deployment or image push |
| D02/T42 | `docker run --rm --network=none --entrypoint python bord-food-api:v1-offline-test -c 'from pathlib import Path; assert not list(Path("/data").iterdir()); assert not list(Path("/imports").iterdir()); assert not Path("/app/tests").exists(); assert not Path("/app/plans").exists(); print("PASS: empty image data/imports; no fixtures/plans")'` | PASS | Final built image, no runtime catalog or seeds |
| D02 | `docker compose -f compose.yaml config --quiet` and `docker compose -f compose.unraid.yaml config --quiet` | Both exit 0 | Configuration parsing, not deployment |
| D02 | `python -c 'import xml.etree.ElementTree as E; E.parse("unraid/bord-food-api.xml"); print("Unraid XML parses")'` | Unraid XML parses | No Unraid installation tested |
| Q01 | `.venv/bin/python scripts/benchmark-offline.py` | 1,000 unchanged on replay; source bytes 0; retailer detail requests 0 | 1,000 synthetic stores/one chain; concurrency 1; 50 requests/query; Linux, 8 visible logical CPUs |
| Q02 | `python plans/food-data-platform/tools/validate_package.py` | 13 check groups passed | Plan schemas/examples/task DAG/links/reference and 93 manifest checksums; separate from application testing |
| Q02 | `git diff --check` | Exit 0 | No whitespace errors |

Benchmark observations: build 2.169 s; lookup p95 6.756 ms; store-search p95 35.212 ms; process peak `VmHWM` 65,592 KiB; sampled staging peak 4,575,232 bytes; final disk 5,219,593 bytes. Initial/after-build/after-replay/after-query RSS: 50,076/57,804/57,884/65,592 KiB. This is not the proposed 2-vCPU/4-GiB or national-data performance benchmark. An earlier inherited `ru_maxrss` measurement was discarded in favor of process `/proc/self/status` measurements.

Coverage includes actual subprocess termination on either side of publication and rollback, checkpoint/outbox recovery, fencing and cancellation, concurrent empty initialization and cursor-secret creation, immutable prior-generation reads, reversible identities/source assertions, current rights/retention during reads/backup/restore, future-control-schema rejection before copying, download resume/redirect/DNS/archive limits, OFF delta gaps and one-attempt full recovery, source parser/filter replay, independent store audits, historical price versus scoped stock, bounded evidence, asset integrity and map placement invalidation. Crawler tests inject transport and prove the activation/robots/contact/host/branch/budget gates; no retailer transport ran.

Intermediate failures were corrected and covered in the final full run: legacy validation response regression; concurrent control startup's `PRAGMA journal_mode` lock race (now serialized by migration lock); first Bòrd smoke harness missing `/fdc/v1` (fixed harness URL). Intermediate 138/156/172/205-test passing runs preceded later tests; they are not the final count. The remaining warning is the upstream Starlette/httpx TestClient deprecation.

Completion boundary: 34 API tasks completed offline, B01 API handoff complete with companion T36–T39 pending, five V1.1/V2 tasks not started. No claim that every cross-repository acceptance scenario was executed. No live-source activation, retailer crawl, paid/authenticated retail call, remote/Unraid deployment, production mutation or Git push occurred. OFF without a proven extraction boundary stays snapshot-only; SNAP current resource resolution and live ATP/source coverage remain unverified. External operator policy/secrets and any permitted media require separate backup/activation handling.
