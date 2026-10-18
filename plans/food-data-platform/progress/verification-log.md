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


## Separately authorized Tower release/activation — 2026-10-18

The owner authorized SSH access, API commits/pushes, image publication and environment/deployment configuration in a new request after implementation. This supersedes the earlier no-deployment/no-acquisition constraint for this core bulk activation only. See `docs/TOWER-DEPLOYMENT.md` for the sanitized full record.

- Application `67c19463ebfe567658813b37a81f5920a0c6ff36` pushed; GitHub run `39102394398` passed tests, formatting, generated OpenAPI, synthetic Docker smoke and AMD64/ARM64 publication. Local `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q`: **213 passed, 1 upstream warning in 7.58s**. `ruff check .`, `ruff format --check .`, and `python scripts/export-contracts.py --check` passed.
- First CI run (`39102041476`) passed its 209 tests but failed generated OpenAPI because the Python HTTPStatus 422 reason phrase differed between 3.12 and 3.14. Explicit native description fixed it; Python 3.12 and 3.14 contract checks passed. First local CDN-test formatter check requested one file reformat; corrected before commit and successful CI.
- Protected pre-upgrade catalog/config/environment/image backup verified by SHA-256 and SQLite quick_check; original legacy catalog still matches that backup after activation. Only the food API service was recreated through its actual productivity Compose project; API credentials/endpoint retained.
- USDA automatic bulk build succeeded: 469,046 foods, 222,191,867 job bytes. Follow-up explicit update check succeeded `no_change`, 160,418 discovery bytes, same generation, no rebuild.
- Initial ATP job safely blocked an unregistered delivery origin. Reviewed official output host registered with run/partition checks and four mocked regression cases. Redeployed/tested image and retried the job: all four selected partitions succeeded, 8,646 stores, 22 chain/banner entities; output source run 2026-10-10-13-32-41, job bytes 10,235,767. Source dates are not replaced by check time.
- Final generation `g_dde791271e1143488b60c5a59e39deb7`; `/live`, `/ready`, `/health` and native/legacy smoke requests all 200; missing-key protected requests 401. All five sampled pre-migration legacy JSON fingerprints match. Actual Bòrd container legacy/native/ready probes passed; no companion source, UI, migration or household writes.
- Worker health passed; running/healthy, zero restarts, no OOM kill, 2 CPU/2 GiB limits retained. Both required packs present; daily checks scheduled. General Tower audit VM leg unreachable; partial local inventory discarded in favor of preserved prior inventory. Tower repository validator: valid, zero violations.
- No optional-source, retailer crawler, map-byte, paid-provider or companion deployment activation. No live rollback/restore performed. Exact private host recovery paths are in Tower's operational runbook; public evidence includes no secret values.

## Separately authorized source pilot — 2026-10-18

See `docs/SOURCE-PILOT.md` for scope, measurements, source links and limitations. Owner supplied a real crawler contact and a $5 total optional-AI cap. This follow-up permits live validation, one bounded retailer crawl and the necessary food API image deployment; original offline implementation boundaries remain accurate for that earlier run.

- Local `python -m pytest -q`: **219 passed, 1 warning, 7.34s**; `ruff check .`, `ruff format --check .` (92 files), OpenAPI check and diff whitespace check passed. Six synthetic regression tests cover multilingual FoodKeeper selection, cell rows/conditions/null/zero/metadata, category integrity, immutable mocked acquisition/replay, optional ATP scope and null-location Open Prices behavior.
- Application `f177b5e` pushed. GitHub run `39156343117`: **219 passed, 1 warning, 10.75s**, lint/format/OpenAPI and Docker smoke passed; AMD64/ARM64 image published. Tower exact SHA image pulled, target service alone recreated and health verified. Pre-pilot protected catalog/config/env backup and rollback image retained; backed-up SQLite checks passed; original USDA hash unchanged.
- ATP five-partition sync: 19 changed, 8,646 unchanged. One-shot Woodman’s Altoona discovery: succeeded; persistent request count 2; one branch map link; no map/media bytes, raw HTML persistence or permissions granted. Crawler source paused and config gates closed after the run. Final generation `g_39e9f3f5bbe84bb9bf3f2aba0f8f1991`: 469,046 foods, 8,665 stores, 23 chains, one pending-rights map link.
- Open Prices: all three exports (32,596,260 compressed bytes; 351,258,598 expanded bytes) scanned; corrected full parser emitted 42,822 US observations in 19.12s; 368 locations, 11 non-USD rows, no exact branch-ID links. 14,136 distinct valid GTINs match USDA; no price pack published. Initial parser failed on one null location; correction preserves failure for broken non-null references. Human country-label undercount corrected by native country codes.
- OFF: HEAD/Range proved 13,179,356,850-byte compressed worldwide export; only 4 MiB prefix acquired, 1,124 complete rows/847 selected products parsed. Delta index 13 internally contiguous intervals; no trusted baseline extraction boundary, no live delta cursor or product publication. SNAP current page returned 403 through the documentation browser; no invented CSV or SNAP import.
- FoodKeeper: official artifact 403 from workstation and Tower, so no live import/size claim. Adapter completed and isolated Tower synthetic rehearsal passed 1,000-row import/SQLite integrity/no-change replay/immutable replacement. First pack 2,465,792 bytes, separate calibration catalog 5,670,272 bytes; never mixed with serving data.
- Jev: 2 real requests, synthetic text/image only; image/Box opt-in header present, 1,563 input tokens, estimated $0.000065646 at documented pricing; no recurring paid integration or source-fact mutation. Account invoice not independently reconciled.
- Final live/native/legacy/worker/auth/storage checks passed; actual Bord-container service probes and its health returned 200. No companion changes/deployment. Optional bulk sources remain off. No live restore, full OFF import, FoodKeeper import, SNAP import, proof-image acquisition, map rendering/rehosting or automatic identity merge performed.

## Full OFF export acquisition and status reconciliation — 2026-10-18

Owner explicitly authorized downloading the full OFF export to Unraid. This is artifact acquisition only: import, source scheduling and the serving generation remain unchanged. Preflight observed the same 13,179,356,850-byte S3 object and its explicit version ID; available cache and the existing 50 GiB data quota/5 GiB reserve were sufficient. Full transfer is pinned to that version and uses the existing bounded transport/resume/hash machinery; final receipt is recorded below after completion.

The copied, unchanged Tower audit collector ran into an isolated report directory so it could not overwrite unrelated operational inventory; its VM leg again failed `No route to host`. Direct Unraid preflight succeeded. The initial detached script launcher lacked `/app` on the Python module path and exited before any bytes were transferred; restarting with explicit `PYTHONPATH=/app` corrected the launcher, without an application-code change.

Current status documentation now distinguishes the original frozen offline task record from later API deployment, companion deployment, pilots and source activation. The task ledger has 35 V1 tasks (34 implemented offline plus the API handoff); all five later V1.1/V2 tasks remain not_started. Bòrd live health rechecked rc.14/schema 0067/current migrations; no companion source or deployment was changed. Latest local checks: `python -m pytest -q`: **219 passed, one upstream warning, 9.34s**; `ruff check .` and `ruff format --check .` passed (94 files). Package validation initially found stale checksums for the previously updated execution records; refreshing only their manifest entries restored all 13 package check groups and all 93 checksums. These are documentation consistency checks, not source import validation.

Full acquisition completed: **13,179,356,850 bytes**, SHA-256 `1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37`, explicit S3 version `VILumlWXh8J9mlPCmokEeMpO11A6lEpI`, ETag matched preflight; elapsed **475.56s**. Native download-cache metadata/source sidecars retained. Final cache free 466,350,084,096 bytes; source disabled, OFF jobs `[]`, serving generation unchanged, `/live`/`/ready`/`/health` all 200. Gzip header sanity only: full gzip CRC/schema validation, product import and live delta equivalence not performed. No source cursor advanced.


## Authorized larger Jev-reviewed crawl launch — 2026-10-18

Owner requested a larger respectful server-side run with Jev and startup-only handback. Selected all 19 reviewed/source-backed Woodman’s branches; Iowa’s 91 current three-chain rows are incomplete and lack independent retailer crawler reviews. Observed official index links were acquired on Tower with fresh robots/contact/30-second pacing and uniquely matched to source website slugs.

Added explicit `scripts/run-reviewed-crawl.py` and nine offline regression tests: concurrent paid-budget reservations, provider failure redaction/retained reservations, global cap including prior pilot, low-confidence fetch deferral, safe bounded link review, activation validation before unpause, fenced immutable publication/final source pause, robots/source-block stop, and advertisement decision withholding. Full `python -m pytest -q`: **228 passed, 1 upstream warning, 11.10s**; Ruff/format (97 files), OpenAPI and diff checks passed. Earlier fixture used a nonexistent search helper; corrected to the actual catalog records API before final passing checks. GitHub run `39161398811` passed, including Python 3.12 and Docker smoke. Source `24fbc86693afcf7488d081329b2bf45832948bc7`; serving image remains `f177b5e`.

Protected pre-run catalog/control and frontier backups completed; frontier quick_check passed. Unchanged audit collector’s VM leg again failed No route to host; partial inventory was isolated, not adopted. Separate private Compose profile/service supplies a versioned read-only script/config, protected Jev file, 1 CPU/512 MiB and restart=no. Main API/Bòrd containers and generic network activation policy unchanged.

Verified launch of `bord-food-crawl-woodmans`, campaign `woodmans-19-20261018`: running, zero restarts/OOM; network-free plan 19 targets/40 calls; actual initial Jev 1.14 pre-fetch decisions answered (503 + 508 input tokens); phase robots_and_branch_fetch. API live/ready 200. Source pacing 30–45 seconds or stricter robots; shared 50/day host cap, 512 KiB pages, two-hour campaign cap, $0.50 reservation budget within cumulative $5, no automatic network/model retries. Model review may withhold targets/publication; it cannot grant rights, invent URLs or change identity/source facts. No images/PDFs/household uploads.

Startup only was verified. No subsequent campaign progress/coverage/completion poll was performed. Results stay on Unraid for a later requested review. The worker pauses its source on completion/stop and supports operator source-pause, STOP file and SIGTERM. No unattended recurring schedule installed. A first launch shell's attached plan command consumed following stdin; the separate explicit detached Compose up corrected launch before startup verification.
