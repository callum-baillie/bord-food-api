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

Startup verification will check only that the worker is running, its status exists and an actual initial Jev decision succeeded; campaign completion/quality/coverage will remain unverified until a later review. The workstation is not required after launch. Runtime results must not be inferred from mocked tests.
