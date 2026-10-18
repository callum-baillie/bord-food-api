# 13 — Acceptance tests and evidence

## Evidence levels

Report `planned`, `implemented_offline`, `tested_offline`, `live_source_verified`, and `deployment_verified` independently. An HTTP mock cannot establish live source health or permission; an installed key cannot establish entitlement. This planning package has only artifact validation. Codex must create its own implementation evidence after running real local tests.

Routine tests must refuse source-network traffic. Use dependency-injected clocks, HTTP clients, filesystem roots and policy. Never use the real `/data`, existing household DB or local import directory as a fixture. Tests and Docker smoke images contain only synthetic data. A localhost test server is allowed; any non-loopback HTTP/DNS/SDK access to source providers fails the test. Tests should not rely solely on environment flags that a request library can ignore.

## Required scenario matrix

| ID | Scenario | Required assertion |
|---|---|---|
| T01 | Empty install, offline policy | API starts without data; `/live` works; status says empty; business routes report pack unavailable; zero source requests and zero sample records. |
| T02 | Empty install, automatic bulk policy with mocked network | Core jobs enqueue once, progress is visible and published data appears only after validation; crawling stays disabled. |
| T03 | Restart during bootstrap | Durable job resumes or retries safely; no duplicated catalog entities, task fan-out, or concurrent heavy importer. |
| T04 | Existing `foods.sqlite` | Adoption preserves food IDs, nutrients, source metadata and legacy search; original is not deleted; optional packs do not block it. |
| T05 | `AUTO_DOWNLOAD=false`, local import | No automatic download; local source remains pinned until explicitly switched. New configuration precedence is visible. |
| T06 | USDA compatibility | Existing GET/POST/detail/auth/error fixtures pass; zero versus missing preserved; 16 KiB legacy request limit remains. |
| T07 | Duplicate or malformed USDA record | Import fails before publication; previous generation remains usable; original null placeholders are counted separately. |
| T08 | Snapshot no-op | Same artifact/parser version skips normalization; changed artifact with equal canonical facts skips entity version/index and detail crawl work. |
| T09 | One new, one changed, one unchanged store | Expected new/changed counts match; only missing/due/changed fields enqueue detail work; unchanged address never causes geocoding. |
| T10 | Hours change on existing store | Hours update; unchanged address/coordinates retained; same page fetch may satisfy both groups without claiming field-only bandwidth. |
| T11 | Missing store in incomplete run | No absence counters advance; no store closes; source is degraded/quarantined. |
| T12 | Missing across three valid runs >=21 days | Record becomes source-missing candidate, not confirmed closed; other sources and Bòrd profile links remain valid. |
| T13 | Store relocation/reused branch number | Suspicious change queues review; site history/aliases survive; no proximity-only merge. |
| T14 | Banner rename/acquisition | Existing physical-store identity survives when justified; parent/banner counts remain separate. |
| T15 | Fuel/pharmacy child records | Do not inflate supermarket branch count or merge nearby but distinct shops. |
| T16 | Old ATP latest-success redirect | Old run stays old; new fetch time does not make data fresh; no source cursor regression. |
| T17 | OFF continuous delta | Apply `(from,to]` in order, deduplicate overlap, commit cursor only after publication. |
| T18 | OFF delta gap/expired index | Pause delta advancement and request a baseline; no silent skip; source reports stale last-good data. |
| T19 | OFF filtered delta contains no eligible records | Successfully processed interval advances cursor after compatible publication/state checkpoint; never use max retained product time as source watermark. |
| T20 | OFF missing tombstones/obsolete records | Periodic complete reconciliation handles current/obsolete evidence without interpreting missing delta rows as deletion. |
| T21 | Same source revision, newer transformation | Explicit parser/hash version forces reprocessing even when bytes did not change; prior algorithm output is not silently mixed. |
| T22 | Two workers/expired lease | Lease fencing prevents stale publisher; duplicate execution cannot duplicate public effects. |
| T23 | Crash before manifest switch | No pending data visible; old manifest/cursors remain committed. |
| T24 | Crash after manifest switch before control commit | Recovery identifies prepared generation, finalizes matching cursor/events exactly once, never replays a conflicting publish. |
| T25 | Disk full or corrupt object | Failed job preserves previous object/manifest; no emergency deletion of active files; status gives bounded actionable reason. |
| T26 | Reader during publication and GC | One response binds one generation; old readers/cursors remain valid until retention contract expires; safe GC waits for quiescence/leases. |
| T27 | Query cursors/changes | Stable pagination; changed parameters rejected; expired cursor returns explicit restart error; no missing/duplicate published change events after recovery. |
| T28 | Identifiers | Python and Bòrd fixtures agree for GTIN8/12/13/14; invalid check digit/retailer SKU not global GTIN; legacy padded lookup not used as identity validator. |
| T29 | Nutrition and measures | Unit/source/form/basis preserved; missing never zero; no mass-volume conversion without evidence; package versus drained amount distinct. |
| T30 | Retail evidence | Catalog match, banner tag, branch listing, stock, price and aisle remain separate; a purchase or price does not manufacture stock. |
| T31 | Price comparison | Exact decimal, currency/channel/loyalty/package terms; expired price not current; missing lines never treated as free. |
| T32 | Source license/policy | Unknown map rights stay link-only; restricted payload cannot enter unrestricted export; policy revocation removes future use and handles retention. |
| T33 | Crawler disabled/robots blocked | No page request, even if job accidentally exists; kill switch enforced in worker transport, not just enqueue UI. |
| T34 | Crawler extraction | Synthetic map link selected; geographic map and weekly-ad PDF rejected; branch association ambiguity preserved. |
| T35 | Untrusted URLs/media | Private IP, redirect to metadata, DNS rebinding attempt, cross-origin credential forwarding, ZIP traversal, decompression bomb, XML entities, active SVG and networked PDF render blocked. |
| T36 | Bòrd profile integration | Original UUID/aisles/order/notes survive link, unlink, rename and source refresh. Existing custom stores still work. |
| T37 | Bòrd selected revision | Confirmation reloads same revision or asks review; dataset refresh does not overwrite durable nutrition/pantry selections. |
| T38 | Bòrd catalog-only | External egress prohibited, including images/fallback; cache generation/transport change invalidates incompatible responses. |
| T39 | Bòrd user action | Enrichment does not add stock or cart entries; existing purchase idempotency and actor/origin checks survive. |
| T40 | App outage/partial packs | Manual workflows and existing USDA route remain useful; source failure does not masquerade as “no stores exist.” |
| T41 | Secrets/privacy | Logs/status/backups omit tokens, raw barcodes/queries/receipts, full response bodies and sensitive local paths. |
| T42 | Empty production artifact | Container excludes references/fixtures/live DBs; production boot does not import package examples or registry research. |

## Test layers

Unit tests cover normalization, strict identifiers, hashes, schedules, source resolvers, permissions and comparison rules. Integration tests use temporary SQLite files and HTTP fixtures with deterministic time. Crash tests kill worker subprocesses at publication hooks and verify disk/control state after restart. API tests use FastAPI’s test client and explicit body/latency budgets. Docker smoke tests use a synthetic local artifact server or mounted synthetic import, not a public provider. Bòrd tests cover the existing real provider with the compatibility shim and the new native contract.

A source fixture is versioned, minimal, synthetic unless explicitly permitted and sanitized. Mark its source schema version and which cases it represents; do not call it a live sample. Deltas and baseline boundaries need fixtures with equal timestamps, out-of-order intervals, zero matched rows, corrections and missing intervals.

## Commands and reporting

Start with the repository’s actual `python -m pytest`, `ruff check .`, and formatter checks. Extend tests in the existing layout. Preserve `scripts/smoke-docker.py` and `scripts/verify-bord.mts`, updating their expectations only for intentional startup semantics. Determine Bòrd’s actual package scripts from its current checkout rather than an old plan. Do not claim an unavailable Docker daemon or missing companion checkout passed.

Create `progress/verification-log.md` entries with task ID, commit, command, exit status, corpus/fixture identity, timestamp and limitation. Never substitute a screenshot or README claim for a test result. Do not record credentials or paid response bodies.

## Performance and coverage gate

Initial benchmark targets, not promises: local exact lookup p95 <150 ms, bounded store search p95 <300 ms on a named 2-vCPU/4-GiB test host and a declared corpus/concurrency. Measure import peak RSS, staging/free disk, transferred bytes, normalization count and detail requests avoided. Profile before changing the database engine.

Live coverage measurement happens later under operator activation. A 200-store/100-product stratified pilot is proposed for finding problems, not estimating all-U.S. completeness. Report per-chain/state/format/source coverage and false merges. Never turn the 120+180 research list into a measured census.
