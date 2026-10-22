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

## Requested crawler status investigation and correction — 2026-10-18

Direct Tower inspection found the original campaign running with renewing leases, no OOM/restarts and healthy API/Bòrd, but seven processed branches all review_required and no new map publication. Gracefully stopped the campaign; its interrupted job failed with campaign_request_stopped and the source paused. Preserved 12 paid-call reservations/$0.12, 14,293 input tokens (estimated $0.000600306). Isolated unchanged Tower audit collector again failed on unreachable development VM; no partial canonical inventory adopted.

Confirmed the defect with one bounded robots/paced Appleton re-fetch: old first excerpt began with analytics JavaScript; normalized visible text included the actual branch address. Added visible-text extraction that excludes scripts/styles/navigation/hidden content and prioritizes headings/main content. Added bounded normalized request evidence/observed links/HTML hash to the separate Jev ledger, and clarified legacy URL aliases and advertised HTML-link classification versus unverified destination contents. Confidence remains >=0.8; no identity or media rights overridden. Two new synthetic regression tests cover boilerplate/hidden text, evidence persistence and off-branch review; existing advertisement withholding test still passes.

Live qualification: pre-fetch 0.94, branch consistent 0.98; original link question still uncertain (0.28), so no publication. One additional paid replay of saved normalized evidence, no retailer request: branch 0.98, advertised floor-map link 0.96, shopping-list other 0.96. No PDFs/images fetched. Correction committed as 658a9aaf9c3d1a3e279a8abf42ff0ff2a97f6c49; runner SHA256 1899818b20ac19a1c6c133c3b9751c949229240c1b2fd130f6d7960ef21d4f77. Final local python -m pytest -q: **230 passed**, one upstream warning, 8.75s; Ruff check, format (97 files), OpenAPI and diff check passed. An initial contract-check command used the wrong filename; actual scripts/export-contracts.py --check passed. Initial class-set lint findings were corrected before the final passing run.

Network-free replacement plan passed 12 targets/24 maximum calls. Recreated only separate bord-food-crawl-woodmans using the read-only versioned runner/config. Campaign woodmans-remaining-20261018-r2 selects the twelve unfinished branches, retains the seven previous review flags, and caps new reservations at $0.24/24 calls. Across original + qualification + replay + replacement: at most $0.39/39 calls, within original campaign $0.50/40 and cumulative $5. Main API/Bòrd images/configuration unchanged. Tower repository validator passed with existing informational/generated and sensitive-archive warnings. Forgejo defect creation attempted, returned HTTP 502; private ISSUES records TWR-048.

Restart verified at ~20:21 UTC: first Janesville fenced job succeeded with one published link, next Kenosha branch underway; generation g_4a254e2261d44db898821f06d97ef5b4, map count 2 (old discovered + new ambiguous). The new link remains unassociated by strict deterministic branch matching, assets empty, display/storage false and rights pending; not a validated usable store map. Live pre-fetch 0.96/branch 0.96/advertised map 0.85, shopping-list other 0.95. At snapshot, 18 total model attempts/$0.18 reserved/21,732 input tokens/~$0.000912744 input estimate plus earlier synthetic pilot; 18 shared retailer requests/day. API live/ready/health all 200, serving containers zero restarts/OOM. GitHub run 39162767745 succeeded, including Python 3.12 checks, synthetic Docker smoke and AMD64/ARM64 image publication. Later campaign progress/completion is not asserted. Background campaign remains running; seven old review flags preserved. Separate status-check receipt is retained in the replacement campaign directory.

Final plan-package validator passed all 13 groups and 93 manifest checks using system Python (the application virtualenv lacks jsonschema). Refreshed only the changed verification-log checksum. Protected operator execution scripts and the bounded restart-status snapshot were archived under the replacement campaign's operator-evidence directory. No unrelated working-tree edits were staged.

## Iowa public-branch expansion — 19 October 2026 UTC / 18 October CDT

Owner requested coverage of every Iowa supermarket chain, then explicitly instructed public branch crawling with robots.txt as the access gate. This supersedes the preceding permission-only interpretation in this session. Retailer terms findings were reviewed/reported, but no retailer permission is claimed; the explicit owner-public-robots opt-in is separate from terms_reviewed and defaults off. Fresh robots, source authorization, contact, scope/budgets and independent media rights remain enforced. No login/CAPTCHA/proxy/IP-rotation fallback.

Acquired the official published ATP archive on Unraid: run 2026-10-10-13-32-41, 2,756,702,590 bytes, SHA256 174b0a4836f88185d5c7fbe96228814da61141e65c2330b522644dc56d8665d7, strong ETag and source Last-Modified retained. 3GiB artifact/50GiB installation/5GiB reserve limits; 5,641 members, 27,992,816,145 advertised expanded bytes. No retailer crawler requests were needed for bulk discovery. The isolated unchanged audit collector again failed its development-VM leg (No route to host), with partial inventory isolated; direct Unraid checks passed. First audit attempt used the wrong key environment-variable name, corrected to TOWER_AGENT_SSH_KEY before the VM failure.

Added explicit network-free Iowa archive discovery/partial publication and multi-retailer map campaign tools. Dynamic source-spider discovery avoids a manually selected chain list. An initial scan stopped at two >2GiB foreign address scopes; corrected to scope-local skips/reporting. A second scan was gracefully interrupted using SIGINT after source inspection revealed Hy-Vee provides state in addr:full; corrected explicit Iowa postal-suffix parsing, preserving its exact source evidence. The third scan completed: 362 Iowa source stores, 14 banners. 389 empty/unusable/oversized scopes retained (350 zero-byte outputs; error types 364 IncompleteJSONError, 23 ValueError, two member limits). No absence/census completion inferred from them.

Published fourteen Iowa-only partial source scopes through fenced staged generations after consistent backup /data/backups/20261019-pre-iowa; control SQLite quick_check ok. Added 271 stores; three existing cohorts (ALDI41/Walmart28/Target22) unchanged. Directory generation g_4b23a4c23c4c41a7ae42030a27e13490, total 8,936 stores, Iowa362. Direct snapshot comparison: USDA object reference identical; all8,574 non-Iowa store IDs/revisions identical; all12 prior map assertions unchanged. All source IDs/attribution/properties preserved; complete=false and source-run regression guards retained. Existing selected-spider automatic schedule unchanged; added Iowa scopes are a one-shot operator expansion.

Public source website fields were absent for ALDI/Fresh Thyme; their @source_uri fields point to bulk APIs, not branch HTML. Two actually observed official branch URL aliases were bound to existing native source IDs/address snapshots, independently gated by model review. No invented URL or seed store: ALDI Muscatine L086 (official locator may render details in JS) and Fresh Thyme Davenport952 (official branch page shows matching address). Exact query-bearing source targets are now explicitly approvable, without enabling query-link following/variants; this supports Hy-Vee's published detail.aspx?s=... URLs. Default behavior unchanged. Operator-public authorization does not bypass live robots, model confidence, HTTP/byte/time controls, identity or media rights.

Core/source commit ed0edd4bd44377b866a26a3a74db5dfcb542a9be; observed-alias operator release bd09309719fc3dd649a258b583041ba26f5fa875. Final python -m pytest -q: **246 passed**, one upstream Starlette warning, 6.90s. Ruff check, format (102 files), OpenAPI and diff checks passed. Initial scan size/address gaps and formatting/lint findings were corrected before final gates. CI39184428905 and CI39184840128 succeeded, including Python3.12 tests, synthetic Docker smoke and AMD64/ARM64 image publication. Routine tests deny real external DNS/sockets. Tower repository validator passed with existing generated/sensitive-archive warnings.

Network-free plan validated14targets/14hosts, one representative branch per source-backed Iowa banner. Started separate profile iowa-crawl/service bord-food-iowa/container bord-food-crawl-iowa, CPU1/512MiB/read-only code/config/protected Jev secret/restart=no. Worker base image ed0edd4; mounted operator release bd09309. Serving Food API remains f177b5e and Bord was not recreated; live/ready/health all200 and both serving containers healthy/no restarts/OOM. Same protected Jev file, no key values in logs/configuration/responses. Campaign iowa-chains-20261019, status under /data/crawl-campaigns/<campaign>/status.json. SIGTERM/STOP/source pause supported; source retailer_maps pauses on exit.

Startup at ~01:20:59 UTC: running/robots_and_branch_fetch, renewing fenced Costco job. Actual pinned Jev decisions answered: ALDI pre-fetch0.74 withheld for review, Costco0.90 approved. Two calls/$0.02 reserved; all-campaign reservations$0.41 at snapshot. Fixed14target pass can attempt at most28calls; explicit campaign ledger ceiling$1/100calls and cumulative$5 remain. 30–45s/stricterrobots spacing, shared50/day/host, 512KiB HTML, two source requests/target including uncachedrobots; no retries, map/PDF/image downloads, rights grants or nutrition/identity edits. No completion or successful branch-page extraction is inferred from startup alone. Worker left on Unraid independently of workstation. Full chain census/branch coverage remains unverified: New Pioneer, Randy's, Brothers and upstream omissions remain explicit gap leads. Forgejo defect creation attempted; HTTP502; TWR-049 retained privately.

Final source-preservation report additionally retained at /data/crawl-campaigns/iowa-20261019/preservation-check.json. Both CI runs completed successfully. Public source branch aliases/evidence are private configuration, mirrored to the Tower source release without the Jev key value. Tower operational state/runbook/issue ledger updated; unrelated private repository work remains uncommitted.

Final container inspection: Iowa worker still running/zero restarts/OOM; API/Bòrd healthy. Actual worker image digest c49fabaaa84c7432aa6e81da0f7c33b05888350ed99a37a8cee99f1eecc06362, runner hash cf06da4808b31db714179d49b9f0766a09f135c109c82050436c3e45a67e1696, exact mirrored configuration hash415dcb5cea1e0dc34b59ff53f9c152b5a6da90a2b391e66be48839cd89c0dfa7. Executed operator scripts/receipts archived under iowa-20261019/operator-evidence/. Full campaign progress/completion not followed after startup verification. Final package validator passed all13groups/93checksums after refreshing only this log's manifest entry.

## National state crawl staging — 19 October 2026 UTC / 18 October CDT

Owner explicitly requested preparation only. Copied the existing pinned ATP archive from Unraid to ignored workstation storage; no new source download. Pin verified: run 2026-10-10-13-32-41, 2,756,702,590 bytes, SHA256 174b0a4836f88185d5c7fbe96228814da61141e65c2330b522644dc56d8665d7. Source manifest/receipt retained. Streamed 33,306,349 worldwide features across 5,640 GeoJSON source scopes (5,641 ZIP members), using the existing strict US grocery adapters plus explicit state/postal evidence. New offline staging module, stage/verify CLI, safe-default state runner and opt-in richer evidence sink implemented; Iowa behavior defaults retained. No USDA/import/API schema changes.

Completed 50 state plans plus separate DC, all with records: 25,003 source store assertions across 141 namespaced banner candidates (137 display labels), 89 contributing source scopes. 19,571 supplied URL candidates / 19,492 distinct URLs /112 hosts. Four duplicate URLs with multiple source identities held. 4,896 missing URLs,477 generic homepages,59 unsafe/unsupported URLs remain gaps. 375 unusable scopes:364 incomplete JSON,nine ValueError,two member limits. Format/banner filter withheld3,891 rows;17 state records unresolved/conflicting. Counts are source assertions, not reconciled physical locations or a complete supermarket census. Per-state plans, source rosters, chains, field completeness, host queue and checksums are under data/nationwide-staging/us-20261019-r2/ (ignored); docs/NATIONWIDE-DISCOVERY.md records the snapshot.

Actual final `.venv/bin/python -m pytest -q`: **263 passed, one upstream Starlette warning, 7.36s**. `.venv/bin/ruff check .`, format check (109 files), scripts/export-contracts.py --check and git diff --check passed. New fixtures cover multistate/DC scope, conflicts, archive/path/hash failures, malformed-scope rollback, query targets, disabled preparation/identity gates, a mocked NY run, rich evidence/decimal prices/GTIN/unknown stock/map rights and bounded HTML sink. Routine tests retain external DNS/socket denial. Both stage --verify and default run-us-crawl.py inspection passed with network=false; no execution flag used. Initial SQLite placeholder typo caused the first archive scan and two new tests to fail; corrected before the successful scan and final gates. Updated derived plans from the same validated staging index after adding the chain/shared-URL reports; index quick_check and count agreement passed, source scan was not rerun or published.

Read Tower instructions/state/runbook. Isolated unchanged audit collector reached Unraid but development VM returned No route to host; no partial inventory adopted. Direct API control quick_check ok; prior Iowa worker Exited(0), API healthy. A host-side Python check was unavailable; used the existing container for bounded read-only verification. Staged **files only** at /mnt/cache/appdata/bord-food-api/crawl-campaigns/us-staged-20261019/ (container /data/crawl-campaigns/us-staged-20261019/), including disabled bundle, passive code snapshot, README, source receipts and STAGED-NOT-STARTED.json. Compressed package7,611,683bytes, SHA2568d4a173f744da768ce3deb01d0c4ce00d6c95acc9c964b3fa052b6c807e1286f, expanded staging about93MiB. No Compose include/service/container/scheduler/source policy changed. No API or Bòrd serving code deployed, Docker build, Git commit/push or companion changes performed.

Remote verification corrected Python's working-directory package precedence and ownership of only the newly created staging directory (UID99/GID100). Final read-only verification under the actual service user passed **238 file hashes**, disabled marker,50states/25,003records/19,571candidateURLs and **zero national jobs**. Serving current.json SHA256 e65288cf0bb8dfb8aed6b64e790623715d2fe47dfdb46878cbb677eec501bd47 exactly matches preflight. No national retailer requests, model reservations/calls, source imports or published generations. Future activation still requires current canonical-ID resolution/import review, exact branch/robots qualification, explicit remaining shared Jev budget/key, and a single shared worker/frontier. Public source pages may not supply products, aisles or usable maps; rich evidence stays review_required and media rights stay off.

### Final scope refinement and inert replacement

Owner clarified: retain aisle/department/maps and other store information, avoid full product inventory capture. Replaced the temporary broader profile with `public-store-layout-evidence-v1`; removed offer/price/catalog/label extraction. Retain only incidental item-to-aisle identifiers and placement evidence. Every state plan explicitly disables product_catalog/product_inventory/prices/product_page_fetches. Store additional layout/department properties retain JSON source paths and unverified geometry status. Revised fixtures assert prices/offers/InStock are not captured, non-placement products are omitted, GTIN/SKU aisle references remain, and store aisle labels retain unverified status. No source or paid request was needed for this change.

Final `.venv/bin/python -m pytest -q`: **263 passed, one upstream warning, 7.17s**. Ruff,110-file format,OpenAPI and diff checks passed. Regenerated only derived plans/manifests from the same verified staging SQLite index; all counts unchanged. The final compressed revision is7,615,840bytes/SHA256d458cb5303f2339037f8f6e4d697884d711a58267420565c3946b120c74c2f0c. Latest passive Unraid directory: `/mnt/cache/appdata/bord-food-api/crawl-campaigns/us-staged-20261019-r2/`; prior first version renamed us-staged-20261019-superseded. **239 hashes** and final disabled/no-product-inventory policy across all50states+DC verified under actual service UID99. Zero national jobs and unchanged serving manifest hash matched preflight. Source roster data, live catalog/API/Bòrd and existing source schedules unchanged. Verification/package receipts and executed verification/finalization scripts retained in operator-evidence/. Tower repository validator passed with existing informational generated-output and historical sensitive-archive warnings; package validator passed13groups/93checksums. No Git commit/push, image build or deployment performed.

## Explicitly authorized larger Iowa launch — 19 October 2026 UTC / 18 October CDT

Owner requested beginning the larger Iowa crawl. Previous14-target qualification was finished:9completed page checks/allnot_found,2low-confidence holds,3blocked hosts. Added a dedicated persistent statewide controller instead of reusing the fixed14-target list. All319source-supplied URL candidates resolved to current canonical Iowa IDs/address snapshots with no identity holds. Original362store roster retains43missing-URL/review gaps. Seeded Costco/Target/TraderJoe host holds cover28targets;291eligible candidates remain. No guessed branch URLs, IP rotation or retry of blocked pilot hosts. Other states remain staged/disabled.

The controller checks every original branch/scope/media/transport gate in25-target validation chunks, rotates hosts serially, waits across shared50/day host limits, honors45s/stricterrobots spacing and releases the heavy worker lock while waiting. Renewing120s/20s job leases fence per-page publication. STOP/SIGTERM/source pause stop it; seven-day deadline and existing shared$5 ledger remain. Budget exhaustion is paused_budget with pending work retained; crash-interrupted branches require review on explicit resume. Full catalog/prices/inventory/product-page capture disabled; map/store/aisle evidence remains review_required with source paths/text, no assets or media rights.

Actual `.venv/bin/python -m pytest -q`: **269 passed, one upstream warning,8.27s**. Ruff,112-file format,OpenAPI/diff checks passed. Six new offline fixture tests cover blocked-host withholding, daily capacity/no paid calls while waiting, worker-lock release, uncachedrobots needing two slots/stricterdelay, shared budget pause/explicitresume, interrupted-target non-retry and invalid scope rejection. No test source traffic. No Git commit/push, serving API/Bòrd deployment or new image build.

Isolated unchanged Tower audit again reached Unraid but failed development VM No route to host; partial inventory not adopted. Pre-run protected snapshot /data/backups/20261019-pre-iowa-statewide contains current generation g_8560354fbef74025bfee1d0775ebff46,control/frontier/Jev SQLite backups/quick_checkok,manifest/current generation JSON and separate referenced pack copies. USDA pack0624d53e2f1a15e64e55f3fcfa16bf9b7adbab0d2899c392f08cb1c576e37d0f and stores777f110f75aed5053733189c796707a23186311895108ab8c53a63da2d98be64. Backup is a current-generation snapshot, not a complete historical-generation archive. Existing ledger62calls/$0.62reserved; this campaign caps new reservations$4.37/437calls, conservatively inside cumulative$5 with prior pilot allowance. It may pause before all eligible branches are visited; no additional spend assumed.

Versioned read-only working-tree release32769a0dbda79cbf0f4e7c0e6ecf11d03998cc74db77469dc11d01c0d31f85b7 contains23pinned files/config. Archive118,945bytes/SHA25694d63cb917816d10b06dccb6131e09f7ad0c3d4f7b6692da333e76b7a274a5f7. Separate profile iowa-statewide/servicebord-food-iowa-statewide/containerbord-food-crawl-iowa-statewide uses existing tested ed0edd4 base image; actual local image2bed62be6d533db8bacc7637861e7d4cfc9b90cbc6a4eae932ff3db255d446ec. CPU1/512MiB/UID99:100/read-only code/root/capsdropped/nnp/no ports/no restart; only existing protected Jev key mount. No key values in code/config/logs. Compose quiet validation and default network-free worker plan passed319targets/can_start=true/$4.37remaining. Unrelated/orphan containers were not removed; host lacks swap limit support but memory limit applies.

Started detached at~02:24:12UTC. Startup verified running/zero restarts/OOM; parentstate running with28hostheld,290pending/1active. Actual first Jev pre-fetch answered0.88; local.jewelosco.com job renewing heartbeat/lease, robots/page phase. Subsequently first page/evidence publication verified; immutable USDA/store pack references unchanged. First rich evidence has correct profile, all product/price/inventory capture flags false and review_required; exact structured-address match unresolved, so no accepted store enrichment inferred. Serving API healthy. Status/evidence under /data/crawl-campaigns/iowa-statewide-20261019/. Worker left running independently; entire campaign not followed or claimed complete. Docs/IOWA-STATEWIDE-CRAWL.md describes status, stop/resume, holds and limits.

## Durable per-state/per-run target history — 19 October 2026 UTC

Owner requested persistent notes of failed targets across every run/state/future runs. Implemented bord_food_api/crawl_history.py, offline backfill/watch/explicit-review CLI scripts/crawl-history.py, future runner checkpoint/reason/HTTP/stage/attempt timestamp hooks and historical hold checks in statewide/generic state workers and state preparation. Append-only SQLite events retain earlier failures after success; latest pointers, active holds and operator reviews are separate. Reports group observations by state and run, stream JSON and skip unchanged exports with watermarks. Repeated unchanged snapshots are idempotent; old snapshots cannot overwrite newer outcomes. URL userinfo/non-store query values redacted; registered configs omit decisions/keys and bind original config fingerprints. Historical exact HTTP/timing absent from old status remains unknown. Events/metadata enrichment are observations, not request/attempt counts. Deferred budgets/daily limits/missing URLs/non-attempted holds are not mislabeled network failures. No holds cleared.

Actual final `.venv/bin/python -m pytest -q`: **279 passed, one upstream Starlette warning,10.21s**. Ruff,117-file format,OpenAPI and diff checks passed. Ten new tests cover IA/NY history and later success retention,idempotency/metadata enrichment,manual review,new failure holds,budget/daily/gap categorization,stale snapshot rejection,UNKNOWNstate,legacy interruption and string addresses,HTTP reasons/secret redaction,read-only observer replay,no jobs/catalog changes,registered config fingerprints and future-state hold propagation. Initial HTTP-details expected dict was updated after adding the error_type field; final suites passed. No source traffic in routine tests. Plan validator passed after refreshing only progress log/decision checksums.

Isolated normal Tower audit again failed unreachable development VM,partial inventory isolated. Added private/live Compose overlay compose.crawl-history.yaml/profilecrawl-history/servicebord-food-crawl-history. Existing tested ed0edd4base image with final read-only source release33002ee9c21263acb5f7b3bb39c5c9c654cde76c93d7393786fb395c9067700f;25file hashes verified. Archive106,549bytes/SHA2561fdacd0ade4e45a800f3eb6d1e47f648dc11d79455da476bfa3a041f420a6abb. Network_mode:none,UID99:100,no API-key mount,code/data read-only,only history writable,512MiB/0.25CPU,readonlyroot/capsdropped/nnp/logrotation/healthcheck/restartunless-stopped. No Git push,newimage build,serving API/Bòrd recreation or national state activation. Existing Iowa worker remains on its original pinned release; observer captures it without changing its behavior.

First backfill reached five runs but private config parent permissions prevented metadata traversal. Corrected by whitelisted sanitized metadata registration (no permission loosening), then a legacy Woodman's source_address string exposed an object-only assumption and transient observer restarts. Stopped only observer, fixed string/postal/current-directory fallback/per-run isolation and regression fixtures, then deployed final release. No source worker interruption or history deletion. Final observer healthy/running,zero restarts/OOM; Iowa start2026-10-19T02:24:13.111988345Z unchanged/zero restarts; API start2026-10-18T19:00:08.187752953Z unchanged/healthy. Metadata319targets matches Iowa config fingerprint and has no decisions/credentials.

Final read-only verification: history quick_checkok,5runs acrossIA/IL/WI,43individual missing-URL records,0review overrides,empty error list/fresh heartbeat. At bounded snapshot768observations/21activehost-or-targetholds (counts can advance with live Iowa work). USDA and store immutable pack references unchanged; only existing Iowa map publications advance serving generations. HistoryDB/reports at /mnt/cache/appdata/bord-food-api/control/crawl-history/; state reports reports/states/IA/attention.json and run reports reports/runs/<id>.json. A consistent initial history SQLite+sanitizedmetadata checkpoint passed quick_check at /history/backups/1792378333; runtime-release.json identifies the future history-enabled code. Catalog-only backups do not include this independent operational ledger. Live ongoing observer paid/source calls0/networknone; active Iowa continues its already authorized work. Documentation docs/CRAWL-HISTORY.md and Tower runbook/state updated. Operator receipts/scripts archived with history. Remaining historical unknowns are explicit, not invented status detail.

Final Tower repository validation passed with existing generated-output information and historical sensitive-archive warnings. Resolved compatibility defect recorded privately as TWR-051; Forgejo issue creation attempted and returned HTTP502. Final receipts and executed metadata/observer deployment scripts retained under history/operator-evidence/. No history hold was cleared, no other state crawler enabled, and no Iowa/API service restart performed.

## Iowa daily limit and randomized pacing — 19 October 2026 UTC

Owner explicitly requested500requests/day/host and immediate crawl resumption, with suitable random spacing. Added validated optional spacing_jitter_seconds (0–300s; default0), sampled once per request and added to effective configured/robots spacing. Iowa scopes set45s minimum plus0–45s uniform jitter and500/day. Generic reviewed operator scope upper bound now500, matching existing transport maximum; unchanged scope configs retain their own lower limits. Existing two-request/branch,512KiB,robots,serialworker,publicDNS/redirect/access/model/media gates remain. Added offline --amend-pacing-from guarded by the exclusive controller lock, exact previous fingerprint, idle targets, and equality of every non-pacing configuration field; records config_revisions and preserves all outcomes/counters/spend/deadline before separate explicit resume.

Actual `.venv/bin/python -m pytest -q`: **289 passed, one upstream Starlette warning,13.27s**. Ruff,117-fileformat,OpenAPI/diffchecks passed. New synthetic/mock tests cover one random sample per actual request, repeated cache-backed invocations, additive stricter robots delay, invalid jitter before transport,500/day acceptance/501rejection, offline amendment invariants, unchanged frontier/campaign budget, wrong fingerprint, locked active worker, and no replay of completed/interrupted targets. The initial bare system python/ruff invocation lacked pytest/ruff; all recorded passing checks use the existing repository virtualenv. No test fetched live retailer/source data or called paid APIs.

Tower AGENTS/state/summary/runbook read. Unchanged audit collector run in isolated /tmp tree again reached Unraid but VM192.168.0.30 returned No route to host; partial inventory not adopted. Gracefully stopped only the idle Iowa worker; status stopped/exit1 is its expected explicit-stop CLI result. Checkpoint `/data/backups/20261019-iowa-pacing` retains status/currentmanifest, previousCompose, consistent control/frontier/Jev/history SQLite (allquick_checkok) and sanitized metadata. Original98pending/84published/91review/46hostheld preserved; frontier and model reservation rows exactly unchanged by amendment, as were all serving pack references.

Versioned read-only source/config release376d94ea2cf37c08e6468272cee61fbb4a3bec680247d652b77521290da40279,25filehashesverified; archive146,506bytes/SHA256680b6e59781d1018bc07627c2fed5b5f0107fbef2e14241e4b371a57bd82e0d4. Actual existing ed0baseimage network-free plan validated319targets and remaining$1.75campaign reservation room, unchanged cumulative$5cap. Amendment fingerprint08e8d463ae2ae2a6f634dda5bc409310b9c2a5bdbd05c93af4118fbcb17e4c04→fa22f462e5b1f7398125ada5f99e8182088b84b33578e332e8d72ab8f93e778e. Updated only compose.iowa-statewide.yaml (source/live), command --run --resume; detached worker recreated06:15:54UTC,zero restarts/OOM. API and history observer retained exact previous start timestamps/healthy. Jev's first new before_fetch call answered; Fareway robots request advanced retained49counterto50, with renewing fenced job and randomized waiting before branch HTML. History quick_checkok, metadatafingerprintmatches,errors[],no operator hold overrides. USDA/store packs unchanged; all other states remain disabled. No Docker build, Git commit/push, API/Bòrd recreation, source bootstrap or extra source activation. Detailed execution/verification receipts retained under campaign operator-evidence/pacing-20261019/.

Startup follow-through at 06:17:54 UTC confirmed one further completed page check (85 total), 91 review holds, 46 blocked targets, 96 pending and one active. Fareway's counter advanced from 49 to 51, directly confirming operation beyond the old daily cap. The robots/page request-start gap was 63.81 seconds. Both the new pre-fetch and post-page Jev decisions were answered; the next branch's pre-fetch decision also completed. USDA/store pack references remain unchanged. The plan-package validator uses system Python's existing jsonschema (the app virtualenv lacks that optional tool dependency); final validation passed all 13 groups and 93 checksums.

## Iowa source expansion and live coverage repair — 20 October 2026 UTC

Owner authorized live source discovery/publication and chose all grocery stores including independents. Added `store_discovery.py`, `expand-iowa-directory.py` and deterministic tests; extended ATP quality checks in `sources.py`. Preserved all prior dirty work. **Actual final `.venv/bin/python -m pytest -q`:314 passed, one upstream Starlette warning,15.32s**. Ruff check,125-file format check,generated OpenAPI and `git diff --check` passed. Tests use fixtures/mocks; no external source sockets. Coverage includes frozen-ID pagination, URL bounds, schema/source-clock/truncation/duplicate rejection, formats/pharmacies, coordinate/address validation, native rename/move holds, cross-source dedup and exact-payload-bound format reviews, existing-source preservation/idempotence, OSM incomplete-query rejection and ATP timeout/queue/count-drop/raw-export mismatch guards. Initial larger fixture GET hit URL-length404 live; reduced batches100/requestbudget50. Initial lint/test failures during iteration were fixed before final checks.

Read actual API/Tower AGENTS, plans, state/summary/runbook. Normal Tower audit ran isolated; Unraid collection succeeded, VM unreachable, partial inventory not adopted. Two consistent current-generation backups on Unraid preserve independent current packs plus SQLite control/frontier/Jev/history snapshots; all quick_checkok. Public acquisition: official FNS ArcGIS item owner/schema/data clock verified, all2,882 IA native IDs/pages accounted for;666 OSM candidates from one state-area query.35 bounded API requests with2second per-host minimum; zero retailer/paid requests. Source files retained under `/data/discovery/iowa-20261020-r2`; failed first attempt retained separately. SNAP native Record_ID is not labeled a license/FNS authorization number. OSM ODbL/SNAP attribution retained.

New immutable source release efd49ed7f4f18ef9887397d237eeca537029b4c26ddb6012b379eed53db88794 (22 files; archive101,229bytes/SHA256209f66228164cc743a2bf2aa70deee892285f837f86d95c988bfbe585ee2158f) installed via read-only Compose overlay using existing ed0 image. Network-disabled actual-image rehearsal373 additions/735 Iowa, replay0 additions/735, stable IDs. Live fenced publication g_06c5c35bb5174eab98572bb872b95436 added373 (333 SNAP-primary/40 OSM-primary), Iowa362→735,total directory8,936→9,309. Direct comparison proves all8,936 previous store payloads byte-identical; USDA/maps object references unchanged. Store pack grew43,212,800→44,830,720bytes. All3 NewPioneer stores,2 Benders locations and Ames Walmart#4256 return via authenticated native API. /live,/ready,/health and compatible USDA FDC food search return200.

Serving f177b5e image now mounts the release's guarded sources.py read-only (SHA256ed6605ef77d378ebb1d58df61c1018be121e5ec16719513d0c9582f29680e6fc); actual-image network-disabled import/timeout test and live module check passed. Only API recreated2026-10-20T13:31:18.919107922Z,zero restarts/OOM. Bòrd/history retained prior exact start times and health. Source/live base Compose edited by one mount only; source acquisition overlay defaults to offline preparation. No new periodic Iowa scheduler enabled, Gitpush, imagebuild or companion codechange. Cumulative Jev347 reservations/3,470,000,000nanousd unchanged from backup. Other49states+DC remain staged. Old Iowa crawl finished_with_holds; no target holds retried/cleared.

First pass reconciled3,548 assertions into373 new/525 matched/501 review/2,149 excluded. Review assertions are not distinct missing stores. All99SNAP counties are represented in raw discovery, not proof of complete active groceries. DIAL is moving licensing to SAFHER on20October; no complete active grocery-license denominator obtained. Public SAFHER documentation fetch returned only JS shell; browser inventory had no providers for interactive inspection. No account creation or records request submitted. Full inventory and new maps/aisle enrichment remain out of this acquisition. Coverage/known-gap plan and source/native provenance are durable; `census_complete=false`. See docs/IOWA-DISCOVERY.md and bounded evidence in docs/investigations/iowa-expansion-20261020.

Tower repository validator passed with existing informational generated-output and historical sensitive-archive warnings. No controller/plugin changes, so their app builds were not applicable. Plan package checksum validation and final health receipt recorded below.

Final compatibility review scoped the ATP marker to ATP only, preserving historical USDA/OFF/FoodKeeper cache identities; added three persisted-fingerprint regression cases. **Final317 tests passed, one warning,28.57s**; Ruff/126-file format/OpenAPI/diff checks passed. The final guard is SHA25637f542fbe0075c862636c2ce20b83c51ad726cefa3ab885e64af2f921173aee0 under a separate versioned discovery-guards directory (operator acquisition release unchanged). Actual-serving-image network-disabled preflight and live historical-fingerprint checks passed. API final restart13:41:24.679556118UTC; Bòrd/history start times unchanged. Catalog generation/counts unchanged, no active source jobs, final health/ready/FDC/native200. All22 operator release hashes verified directly. Plan validator passed13groups/93checksums; Tower validator passed existing warnings. TWR-052 recorded; Forgejo issue-create attempt returned502. Bounded evidence and full executed operator scripts retained; no unperformed companion/live steps represented as completed.

## 2026-10-20 UTC — Store field enrichment, product/guidance packs and local dashboard

Implemented source-backed field assertions, normalization, independent-lineage corroboration,
conflict retention, audited reviews, verification expiry, local schedules/dated exceptions,
IANA zones and explicit permanent-closure uncertainty. JSON-LD plus bounded Schema.org microdata
and page-only contacts are extracted without extra source/model requests. Corporate/footer
contacts cannot silently become branch contacts. OSM lifecycle/source fields and retained
Overture/Foursquare extract adapters added; real Overture/Foursquare acquisition not performed.
Future generic/statewide runners reconcile evidence after approved page publication. Entrances
and aisle mappings remain review-gated, and no inventory or source rights are inferred.

Retained evidence capture was 5,681,606 compressed bytes. Local all-store rehearsal published
9,309 metadata updates and replay changed zero, preserving IDs/raw source records. The initial
reader's Iowa-only default was kept for existing discovery callers while enrichment gained an
explicit all-state option. Live field publication g_1d4fbfdf7a5644d1aee9c5ccdef23faf preserved all
9,309 store IDs, 34 chain payloads, original store source records/references and USDA/maps objects.
Stores pack 44,830,720→86,790,144 bytes. Iowa stays735 stores,610 coordinate-bearing stores:
735 derived timezones;103 corroborated phones,17 websites,10 normalized weekly schedules;
61 field conflicts across46stores;621 SNAP and277 OSM evidence links. Phone presence remains287,
website presence331, raw hours357; corroboration is not a count of newly filled contacts.
Emails, holiday exceptions, service links, entrances and reviewed aisle mappings remain missing
where adequate evidence was not retained. No permanent closures were invented; status is unknown.

Owner selected US-labelled OFF products. Consistent pre-change backup is
/data/backups/20261020-before-products-enrichment. A network-disabled isolated worker published
455,458 USDA branded product projections (3,696,787,456-byte products pack) and49 guidance rows
(184,320-byte pack) from the reviewed official FoodSafety.gov Cold Food Storage Chart. The chart
is separately attributed, source reviewed2023-09-19, with original ranges/conditions; it is not
full FoodKeeper. Official FoodKeeper JSON still403; no mirror/bypass imported. Original USDA
469,046-food pack and108map records unchanged. All five native/legacy/readiness routes checked
returned200; legacy apple FDC response bytes match the pre-field-support fingerprint.

Execution failures were retained: the first product worker was stopped for per-record identity
fsync overhead; the second OOMed before publication on full-payload snapshot materialization.
Bounded identity batching and streamed membership checks fixed these; the third published USDA/
guidance then was deliberately stopped before the OFF scan to prioritize field publication.
One field launch and one OFF launch correctly failed fast on the shared worker lock. The final
OFF-only worker uses the same exclusive flock with a bounded operator wait, networking disabled,
2GiB/1.5CPU, retained SHA/size validation and US-label filtering. It is a separate background run,
not reported complete here; no delta boundary/watermark is proven and automatic OFF stays disabled.
A receipt key collision (state filter overwrote publication outcome) was fixed and regression-tested;
original live receipt preserved alongside a corrected outcome after generation/worker-success checks.

API serves the same pinned f177b5e image with versioned read-only module overrides. Final override
release e06058bad8e1e446b6efdf4e59fef13d4d3c7681808622881b961de630a80d73 includes a bounded
immutable-object validation cache: first check/full metadata change hashes/checks SQLite; unchanged
inode/size/mtime/ctime avoids multi-GB idle polling. Corruption/write detection regression passes.
API recreated alone; Bòrd/history exact earlier start times preserved. Future crawler code staged
as crawl-field-releases/95d704cf3849ab4a6428880becd58cd6173ac391426b879ab2de41a2c6f155e0;
604,160-byte package, actual-image network-disabled imports/microdata preflight passed, zero jobs.
Historical Iowa worker scripts/holds and all other state activation flags were not changed.

Local viewer now has state/country/world boundary maps, zoom clusters, field presence/current
verification/derived/conflict layers, completeness and geographic bars, inspection, URL filters,
mobile map/table tabs and stale-refresh retention. Source/verification/holiday/closure/related
evidence is inspectable. Products/guidance pages now read the published packs; a regression prevents
stale unavailable capability metadata hiding a successful catalog response. No external tiles or
geolocation. Viewer remains loopback-only on localhost4173, not a public/Unraid deployment.

Actual final checks: **344 API tests passed, one upstream Starlette warning,11.43s**; Ruff check,
159-file format check, OpenAPI export check and diff whitespace check passed. Viewer **6 Node+8
Python tests**, build, formatting/Ruff and **13 browser tests/11.1s** passed. Explicit live browser
read check passed product search/retail evidence,49guidance rows,state/country/world maps,mobile
controls/no overflow, existing USDA/reference/Jev/history views, with no console/page errors.
Generated dashboard concept and latest real desktop/mobile captures were inspected together;
product/guidance drawers inspected too. Evidence/receipts in docs/investigations/store-enrichment-20261020
and sibling viewer docs/live-enrichment-check.json. The retained Open Prices exact OSM-ID join
against277reviewed Iowa keys found0matching locations out of368USlocations/42,822observations;
no branch stock inferred. Kroger/Instacart/Walmart/supplier API discovery documented, no connectors.

No paid calls, new source downloads, retailer crawl, Git commit/push or new image publication.
Jev remains347answered/$3.47reserved (not billing). Bòrd companion code/features were not changed.
Tower preflight audit was isolated because the VM leg remained unreachable (exit255); canonical
inventory preserved. Tower repository validator passed with pre-existing archive/generated-output
findings. TWR-053 bulk import defect recorded; Forgejo issue creation returned HTTP502.

## 2026-10-20 UTC — Iowa field pilots and statewide launch

Actual final `.venv/bin/python -m pytest`: **374 passed, one upstream Starlette warning, 14.51s**.
Ruff check, 179-file format check, generated OpenAPI and diff checks passed. Tests use synthetic
fixtures/mocked transports. The actual pinned Python 3.12 image passed network-disabled provisional
field publication/retention; offline campaign plans passed on Unraid before launches.

Published six exact SNAP-plus-Overture additions: 735 → 741 Iowa stores, 9,309 → 9,315 total.
The public Overture 2026-09-23.1 Iowa extract retains 1,758 rows/2,856,938 bytes, SHA256
55a9f0dbc6cc4bb280218f7193b06b407ea44e3991b587ad6c933df8b93e2ea6. Of 1,258 grocery-classified
assertions, 425 matched 410 prior stores; 833 unmatched assertions need review, not 833 distinct
missing stores. Provider licenses/property lineage/clocks retained. No complete active-license
census denominator or 100% coverage is proven; existence confidence is not field accuracy.

Before statewide execution, phone presence increased 287 → 503, websites 331 → 480, normalized
weekly schedules 10 → 314; all 741 have derived America/Chicago zones. For the unchanged 735-store
cohort, phones are 497/websites 476. Corroborated phones increased 103 → 252, websites 17 → 116;
corroborated hours remain 10. There are 84 provisional emails, 11 department lists and 10 accessibility
records. Eighty-six corporate/shared provider email fields were withdrawn with assertions retained.
Pickup/delivery link one each remains unverified. Holiday exceptions/reviewed entrances/aisle
mappings remain zero without suitable evidence; no closure invented. There are 217 conflicts
across 182 stores, 616 stores with coordinates/125 without. Provisional fields have null verification dates.

Pilots drove full-address, visible/Yext/hydration, nullable HTML and department parsing corrections.
Pilot1: one publication/two reviews/old ALDI policy block. Pilot2: two publications, invalid Sam's
robots, TypeError pause; first repair incomplete and retained. Pilot3: **3/3 published**, Hy-Vee
Dollar Fresh, Wheatsfield and Whole Foods. Pilot4/redirect diagnostics recorded three HTTP301 routes,
no Jev calls. Corrected pilot5: Valley Fresh published, Graziano review, ALDI inherited hold.
After metadata repair, current ALDI robots denied the request; no branch fetch or Jev call. Seven
saved approved pages were replayed offline with original dates/hashes; v6 changed Jewel/Hy-Vee,
zero HTTP/model calls. Old failures remain. The history repair reviewed 94 metadata-only/inherited
holds; no new actual access denial cleared. Inherited holds cannot create new host failures and
metadata refreshes cannot reopen a reviewed physical attempt.

Iowa-only background worker `bord-food-iowa-fields-statewide-20261020` started at
19:31:55.705212779 UTC: 481 unique URLs/111 hosts plus 260 explicit URL gaps account for all 741
records. Primary requests observed, queue continued after a network failure and branch review.
Primary plus at most one observed canonical follow-up, seven-day deadline, 500 daily attempts/host,
45–90 second randomized or stricter robots spacing, 2 MiB HTML/three bounded requests, conditional
cache/backoff. STOP/source pause/renewing leases gate requests, decisions and publication.
Jev 1.14.0 selective, $15 cumulative cap/$5 maximum per pass; startup 357 answered/$3.57 reserved,
not measured billing. Other states off; no inventory/pricing/assets/images or paid source APIs.

Frozen worker release 28d60800261366ea5d2f3ac025a84dafd7e3589e95dca6da2d59f5eb630b3b89 on the
existing f177b5e image, image ID 169264bb538c8add672750b01d0124489237e1cc7379c24975915466a8e3ded3.
API store-field module v3 SHA256 efc76d66a40f597fc9a188bbd8c65d0fccaac7539844643938e25aeb19164aa2
healthy after scoped activation; history-only network-none update healthy. Bòrd's separate rc.18
update by its own thread preserved. Direct proof: all 9,343 old entity IDs retained, 8,574 non-Iowa
store payloads/34 chain payloads identical, 735 original Iowa source records preserved, all non-store
pack references unchanged. Legacy apple search hash identical; live/ready/health/native stores/
products/guidance/FDC returned200, missing key401; zero restarts/OOM. Consistent backup at
/data/backups/20261020-before-iowa-fields; about422.5GB free at check.

Correction to earlier OFF observation: retained US-labelled worker failed `Duplicate source key`
after597,000 selected, before publication. Existing455,458 USDA products/49 chart guidance rows/
469,046 USDA foods unchanged; no OFF delta boundary/watermark proven. No OFF repair in this task.
Full FoodKeeper official403 remains unresolved. No Git commit/push, new image publication,
frontend deployment, companion implementation or national activation. Full Iowa run in progress,
not completed. Product GTIN/generic-client changes and full OFF/FoodKeeper activation remain separate.

Evidence: docs/IOWA-FIELD-CRAWL.md and docs/investigations/iowa-fields-20261020/RESULTS.md.
Tower audit ran isolated because VM unreachable(exit255), canonical inventory preserved. Tower
validator passed existing archive/generated warnings. TWR-054 recorded; Forgejo creation returned
HTTP502, not created. Companion/viewer work from earlier turns was not changed/deployed here.

## 2026-10-20 UTC — Iowa quality publication, continuation and $2 OpenAI pilot

Actual final `.venv/bin/python -m pytest`: **388 passed, one upstream Starlette warning, 16.31s**.
Ruff check/195-file format check, generated OpenAPI and diff checks passed. Network-disabled actual
pinned Python 3.12 image publication/alias preflight passed. Viewer collector scope-denominator fix:
6 Node/8 Python tests, build, Prettier and 13 browser tests (21.6s) passed; Ruff passed with 100-column
format. No frontend deployment/key edit. Fixtures/mocked transports remain routine test inputs.

Published four reviewed aliases and two format exclusions, 741 raw → 735 canonical Iowa stores;
9,315 raw IDs retained / 9,309 canonical nationwide. All 735 structured addresses; 695 coordinates
(94.6%), 40 gaps held. Same surviving-cohort phone/website/hours counts remain 498/474/311, not
increased by this pass; 336 independent/unmapped stores have 140 phones/107 websites/16 schedules.
218 conflicts across 183 stores retained. Known chain phone scope annotated; original values
retained. No closure invented.

Old worker stopped gracefully with history/counters/holds intact. New Iowa-only continuation
started 20:16:59 UTC with 197 pending/deferred URLs/64 hosts, 258 URL gaps, 280 prior outcomes
accounting for 735. Independent-first; first requests/Jev/publication verified, run still in
progress. 500 daily attempts/host, 45–90s jitter/stricter robots, selective Jev $15 cumulative ceiling
unchanged; no inventory/prices/images. Profiles reusable across US states; other states staged/off.
Latest/replay parser v7 and active earlier frozen profile runtime distinguished by release hash.
Eight retained approved pages replayed offline, three changed/three unchanged/two ambiguous,
zero HTTP/model calls.

One owner-authorized OpenAI Batch completed 9/9 requests covering 195 stores; 16 deferred/524
without eligible evidence. Conservative reservation $0.586806 within $2, not actual billed spend.
Network-none importer accepted 26 evidence proposals (13 phone/12 website/1 hours), updated 26 stores;
19 held (10 quotes, three invalid values, three unbound fields/docs, two incomplete hours, one stale).
Mostly evidence updates, not higher missing-field coverage. Exact quotes/unchanged source-bound
records required; no AI independent vote. Post-pass hook prepares without another paid submission.
Key stayed workstation-side.

Backups/activation/live receipts: docs/investigations/iowa-quality-repair-20261020/RESULTS.md.
All 9,315 raw IDs/source_records/source_refs retained, 8,574 non-Iowa payloads identical, non-store
refs unchanged; redirects/exclusions tested. Live/ready/health/stores/products/storage-guidance/FDC
returned 200, missing key 401. API/Bòrd/history healthy, zero restarts/OOM, only API recreated;
existing image retained. No Git commit/push/new image, companion changes, national crawl, live
geocoder, pricing connector, OFF repair or full FoodKeeper activation. State licensing/WIC/address
research recorded; complete Iowa census remains unproven. Previous OFF Duplicate source key failure
and FoodKeeper 403 remain separate. Tower audit isolated (VM unreachable exit255/canonical inventory
preserved); Tower/plan validators passed. Forgejo issue creation returned HTTP502, not created.
Receipts are in checks.json; TWR-055 recorded locally.

### 2026-10-20 — Repeatable phone/hours repair and contact discovery

Implemented shared compatible-week reconciliation, explicit schema meridiem, OSM daily semantics,
source-clock-preserving reparse, non-direct/department contact scopes, exact retained OSM joins,
reviewed contact footers/nested panels, full state-name matching and official-directory URL leads.
Source/version/provenance and actual conflicts retained; partial sources do not verify unseen days.
Generic discovery/NE fixtures preserve carryover while execution remains Iowa-only.

Two atomic retained-source publications improved the same735 Iowa records from502 phones/474 sites/
312 hours to508/479/365 (351 full weeks), zero source/paid requests for those publications.
Independent/unmapped336 has142 phones/108 sites/18 hours; data remains incomplete. Fifty selected
legacy contacts marked non-direct. All9,315 raw IDs/source refs/source records,8,574 non-Iowa payloads,
unrelated packs/four redirects/two exclusions retained. API/auth/legacy/products/guidance checks pass;
only API recreated on pinned image, Bòrd/history starts unchanged and healthy.

Live directory discovery fetched four documents and retained four NCG website leads. Five-page
pilot completed: one existing control published, four held. Fixed empty footer Jev review context;
three explicit retained-page re-reviews still below confidence threshold, no source requests or
hold deletion. Eight new Jev calls reserve$0.08, cumulative ledger$3.89 plus prior$0.0001 under$15,
not billing. No new OpenAI calls. Second15-target/six-target wider phases staged and offline-validated;
gain controller held them, zero new accepted missing fields. Prior continuation stopped, history/
STOP/counters and actual failures retained. No national crawl, companion/viewer changes or Git push.

403 tests passed74.83s (one existing Starlette warning), latest retained-state fixture2/2, Ruff and
207-file format passed. Final checks/receipts and incomplete steps:
docs/investigations/iowa-contact-improvements-20261020/RESULTS.md. Tower audit isolated: VM unreachable
exit255, canonical inventory preserved. Forgejo returned HTTP502; TWR-056 retained locally.

### 2026-10-21 UTC / October20 CDT — Owner-authorized smaller-state scans

Owner explicitly authorized scans beyond Iowa. Five bounded FNS metadata/aggregate requests verified
publisher/schema, stable data clock,360 unique state/type groups and248,622 records across50 states.
Grocery-format counts are a planning proxy, not a complete physical-store census; full50-state CSV/
JSON and an executed two-cell notebook retained. First12 states grouped serially: WY/AK/VT377,
ND/DE/SD603, MT/RI501, NH/HI539, ID/WV587 reference records.947 retained ATP assertions seed the scan;
no new full archive/SNAP/OSM location download or source-coverage completeness claim.

Shared field runners now accept explicit source-bound states. New serial controller preserves
existing/native identities, adds only new ATP keys with partial provenance, holds co-located/format/
address/URL/history conflicts, then qualifies <=5 pages/state before <=25-page chunks. Failed
qualification holds that state's remainder and continues other planned states; global paid-cap
exhaustion pauses the plan. Same500 attempts/day/host,45–90s jitter/stricter robots and$15 cumulative
Jev cap, selective after pilot. No prices/inventory/images/PDFs or new OpenAI request.

Unraid worker bord-food-small-states-20261020 started00:29:23UTC using pinned existing image and frozen
sourcea1a566ed...; latest staged resume guard separately validates backup completeness, no running
immutable source overwritten. Consistent backup plus frontier/history/Jev snapshots verified.
Wyoming27 new native records/42 canonical stores published,30 eligible URLs/12 gaps. First live
Jev/page/field publication succeeded, next target underway; other states remain queued, not completed.
At checkpoint one new$0.01 reservation, totalledger$3.90 plusprior$0.0001, not measured billing.

412 offline tests passed72.35s (one existing Starlette warning), actual-image network-none preflight
all12 states and backup validation passed; zero source/model calls/publication during preflight.
Ruff/OpenAPI/diff/format/plan/Tower checks recorded in checks.json. All original9,315 raw IDs/source
records/refs retained,9,039 nonselected payloads including735 Iowa identical, unrelated packs unchanged.
API/Bòrd/history starts unchanged/healthy, worker running/no OOM. Audit isolated,VM unreachable255,
canonical inventory unchanged. Forgejo TWR-057 returnedHTTP502, not created. No Git push/new image,
companion/viewer changes or activation beyond the twelve. API docs/investigations/small-states-20261020/
RESULTS.md records source limits, phases, snapshots and unperformed work.
