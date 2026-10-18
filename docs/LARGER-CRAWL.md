# Reviewed larger crawl campaign

Owner request on 18 October 2026: start a larger respectful crawl on Unraid, use Jev for decisions, and hand back after startup rather than following the run to completion.

## Selected scope

Run the 19 source-backed Woodman’s branches in the current catalog, across Wisconsin and Illinois. This is the larger cohort supported by the already reviewed site adapter and successful single-branch pilot. Current Iowa coverage has only 91 imported stores (41 ALDI, 28 Walmart, 22 Target); it is not every Iowa supermarket, and those retailer sites need independent adapters/terms/path reviews. An Iowa-wide crawl is not being claimed or launched by this campaign.

The 19 branch URLs were matched to observed links on the official store-location index, using their existing source website slugs; only unique matches were accepted. The index was acquired on Tower after a fresh robots check, with identifying contact and at least 30-second pacing through the durable frontier. No invented branch URLs, manual catalog seeds, or source-name-only identity merges.

## Run behavior

`scripts/run-reviewed-crawl.py` is an explicit operator tool, mounted read-only into a separate one-shot Compose container using the existing pinned API image. It does not run during API startup, change the serving API image or enable the API’s generic crawler/paid-source gates. Its private operator configuration supplies reviewed activation gates and fixed branch targets. It holds the existing heavy-job lock, creates/claims a fenced job per branch, and publishes through the immutable map-link path with `complete=false`. The last catalog stays usable if later requests fail.

- Sequential requests to the exact official HTTPS host/path; no redirects, browser automation, authenticated shopping pages, proxies or IP rotation.
- Deterministic 30–45 second target pacing, plus stricter robots delay/request-rate rules; persistent host budget at most 50 requests/day, shared with the pilot/preparation. At most two retailer requests per branch, including robots when uncached. Cache robots at most one hour and obey shorter/no-store directives.
- 512 KiB branch limit, existing public-address DNS/TLS pinning and byte/time limits; at most 19 branches, 40 Jev calls and two hours overall. Stop on robots, transport, access, source pause, model/budget or malformed-response errors. No automatic network/paid-call retries.
- Public branch HTML is transient. The small robots cache may persist; map/PDF/image bytes are never fetched, rendered, uploaded or rehosted. Rights remain pending and source facts are not model-generated.
- Completion, stop or SIGTERM pauses the crawler source. An operator `STOP` file or source pause also halts it. No recurring crawler schedule is installed.

## Jev’s role and budget

Before each branch request, pinned `jev-1.14.0` reviews the source-backed target and may defer it. After HTML acquisition it reviews branch consistency and classifies bounded observed link candidates as floor map, advertisement, geographic or other. Low-confidence/mismatched pages and uncertain/ad/geographic map candidates are withheld for review. Jev cannot invent targets, override robots/access gates, grant media rights, change identity, infer aisles or overwrite nutrition/storage guidance.

Requests contain public branch metadata, a bounded text excerpt and observed same-host link labels/URLs. Model answers/usage stay in a separate durable decision ledger, with target/stage references; source extraction remains deterministic. No household data or map/receipt images are sent. Image opt-in is unnecessary because this campaign sends no images/Box questions.

The owner’s earlier **$5 total cap** remains in effect. This campaign additionally caps reservations at **$0.50 / 40 calls**, reserves $0.01 atomically before each attempt, and retains the reservation on failure. A shared SQLite ledger enforces the overall $5 ceiling, rounding prior pilot usage up to $0.0001. At the reviewed $0.042/M input price and default 64k request context, a call’s maximum input charge is below its reservation. No long-context opt-in, retries or unattended unlimited spending. The key is supplied through a protected read-only file available only to this worker; never in API responses, logs, source or Compose environment.

## Operations and evidence

The private Tower runbook records actual Compose invocation, release SHA/file digest, campaign ID, mounted configuration/secret paths and stop/status commands. Status JSON is under `/data/crawl-campaigns/<campaign_id>/status.json`; decisions are in `/data/control/jev-crawl-budget.sqlite`; source jobs and request counts remain in the existing control/frontier databases. The configured profile is `crawl`, service `bord-food-crawl`, restart policy `no`.

Startup verification checked that the worker was running, its status existed and actual initial Jev decisions succeeded. Campaign completion/quality/coverage remain unverified until a later review. The workstation is not required after launch. Runtime results must not be inferred from mocked tests.


## Verified launch

Runner source commit: `24fbc86693afcf7488d081329b2bf45832948bc7`; runner SHA-256: `59f696551e220e7c52dd82c2806bb6265d4cde929015c964ffb5d9ef52a5a526`. Local `python -m pytest -q`: **228 passed**, one upstream warning, 11.10s; Ruff, formatting and OpenAPI passed. GitHub run `39161398811` succeeded, including Python 3.12 verification and Docker smoke. The production API/Bòrd images were not replaced.

The network-free campaign plan validated 19 targets and 40 maximum model calls. The separate Compose container `bord-food-crawl-woodmans` started running with zero restarts/OOM at inspection. Initial campaign state was `running`, phase `robots_and_branch_fetch`; two pre-fetch decisions from `jev-1.14.0` were answered (503 and 508 input tokens). These are startup observations, not completion/coverage results. API `/live` and `/ready` both returned 200. No further progress/completion polling was performed after startup verification.

Pre-run consistent catalog/control backup and frontier backup completed; frontier quick_check passed. The general audit collector’s development-VM leg was unreachable; direct Unraid/service checks supplied launch evidence. Startup/configuration/decision/status records remain on Unraid. No claim that all targets were fetched, all maps found, Jev accuracy established, or an Iowa-wide crawl completed.

## Status review and correction — 18 October 2026

A later owner-requested status check found the initial process alive with renewing leases and healthy APIs, but all seven processed targets withheld for review and no new map publication. The operator gracefully stopped it; the interrupted eighth job was fenced/failed and the source paused. Twelve Jev calls had reserved $0.12 (14,293 input tokens, estimated input charge $0.000600306). This supersedes any assumption that a running process established useful extraction.

The initial excerpt included analytics JavaScript before branch information. The runner now excludes scripts/styles/navigation/hidden elements, prioritizes visible headings/main content, and stores bounded normalized request evidence plus observed link URLs and the HTML hash in the separate decision ledger. Public HTML is still transient. Pre-fetch instructions distinguish the reviewed current location URL from the source's legacy URL. Link review classifies its **advertised purpose**; it does not verify a destination PDF's contents. Confidence remains at least 0.8; source identity, robots, rights and immutable publication gates are unchanged.

One paced, robots-checked Appleton re-fetch confirmed the old excerpt began with analytics JavaScript. Clean visible text identified the branch at 0.98 confidence, but the original link question remained uncertain. A single Jev replay of that saved normalized evidence, without another retailer fetch, classified the advertised store-map link at 0.96 and the shopping-list link as other at 0.96. These are model decisions on observed source text, not map-content accuracy or rights validation.

Correction source: `658a9aaf9c3d1a3e279a8abf42ff0ff2a97f6c49`; runner SHA-256 `1899818b20ac19a1c6c133c3b9751c949229240c1b2fd130f6d7960ef21d4f77`. Final offline verification: **230 passed**, one upstream warning, 8.75s; Ruff, format (97 files), OpenAPI and diff checks passed. Only the separate crawl worker was recreated. The API/Bòrd images and general source activation gates were unchanged.

Replacement campaign `woodmans-remaining-20261018-r2` contains exactly the twelve unfinished targets, including the interrupted target. The seven earlier review outcomes remain recorded; they are not silently retried or reported as completed coverage. Replacement limit: 24 calls/$0.24 reserved, so original run + two-call qualification + one-call evidence replay + replacement maximum is **39 calls/$0.39 reserved**, below the original 40-call/$0.50 campaign allowance. Prior pilot and cumulative $5 enforcement remain in the shared ledger. Same host pacing, robots and daily request limits apply across all runs.

Bounded restart verification at approximately **20:21 UTC**: campaign running; Janesville job succeeded and published one link record, Kenosha underway with a renewing fenced lease. Jev: Janesville pre-fetch 0.96, branch 0.96, advertised map 0.85; shopping-list other 0.95. Catalog generation advanced to `g_4a254e2261d44db898821f06d97ef5b4`; map records increased from one to two, with the new record **ambiguous** under deterministic branch matching. This is a discovered link pending association/rights review, not a verified usable map. All map assets empty and storage/display false. API live/ready/health returned 200; both serving containers remained running with zero restarts/OOM. At that snapshot: 18 model attempts, $0.18 reserved, 21,732 input tokens, estimated input charge $0.000912744 plus the earlier synthetic pilot; invoice not reconciled. Shared retailer counter 18/day. Later campaign completion and coverage are not asserted. GitHub run [39162767745](https://github.com/callum-baillie/bord-food-api/actions/runs/39162767745) passed Python 3.12 checks, synthetic Docker smoke and image publication; serving images were not changed.
