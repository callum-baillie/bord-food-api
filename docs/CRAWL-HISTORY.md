# Crawl outcome history

Every supported crawl run records target outcomes in a shared SQLite ledger at `/data/control/crawl-history/history.sqlite` (host `/mnt/cache/appdata/bord-food-api/control/crawl-history/history.sqlite`). It is separate from the serving catalog and the API's control schema. Append-only observations retain earlier failures when later runs succeed. Current target pointers and explicit operator reviews are stored separately; no automatic failure-history deletion or retry.

Records include run ID, state/DC (or explicit UNKNOWN), canonical store/native source identity, name/banner when available, sanitized URL/host, outcome/category, reason code, known HTTP status, job/stage, source-request attempt flag, available target timestamps, observation timestamp, retry status and configuration binding. URL credentials and non-store query values are redacted; model credentials/headers/full exceptions are never copied. Registered run metadata contains only whitelisted public target fields and the original config fingerprint. Historical records with only run-ID or current-directory context are labeled accordingly; exact historical failure times/HTTP details remain unknown when not recorded.

A terminal target hold is different from a failed source request. Pre-fetch model uncertainty, inherited host blocks and missing URLs may involve no retailer request. Daily host/budget deferrals are separate categories, not network failures. A published page check can mean no map link was found; it is not proof of a usable map, current inventory, aisle geometry or rights.

Reports are automatically refreshed under:

- `reports/summary.json`: runs, state observation counts and active holds.
- `reports/states/IA/attention.json`: Iowa failure, block, review, gap and deferred observations across runs. Other states have their own directories after actual observations.
- `reports/runs/<campaign_id>.json`: the complete observation history for that run.
- `observer-status.json`: scan heartbeat, errors, observed states and zero-network/paid-call markers.

Observation counts are not HTTP attempt counts: state transitions and newly recovered metadata can create additional observations for one target. Repeated identical snapshots are idempotent. Streaming report exports use watermarks so unchanged historical reports are not rewritten each poll. SQLite is the durable source of truth; JSON reports are derived and rebuildable. Retain the ledger, its run-metadata and review history in operational backups alongside run status/evidence files; catalog-only backups do not include this separate operational ledger.

## Existing and ongoing runs

The Tower `bord-food-crawl-history` observer scans saved run status every15seconds. Its network mode is **none**, it mounts data/code read-only and only its history directory writable, and it has no API-key mount. It does not create jobs, call sources/Jev, alter crawler policy, accept facts or retry targets. Historical Woodman's and Iowa campaigns are backfilled with their existing evidence. Missing URLs for the larger Iowa run are recorded individually as resolution gaps. The running Iowa worker is not restarted to add observation.

Versioned observer/future-runner release `33002ee9c21263acb5f7b3bb39c5c9c654cde76c93d7393786fb395c9067700f` is under Tower's productivity `config/crawl-releases/`. Use this history-enabled source for future activations against the existing pinned state bundles. Other states remain staged/disabled. The observer also reads future status files even when an older pinned runner created them; exact failure detail depends on what that older runner recorded.

New state preparation retains unresolved prior host/target holds with event references. Updated state runners journal snapshots before source transports and at terminal outcomes, preserve known HTTP reason/stage/timestamps, and consult prior history before paid/source calls. A later success does not silently clear an earlier access/review hold. A hold can be cleared with an explicit, evidence-bearing review; that does not enable any source or bypass fresh robots, identity, budget, rights or runtime activation gates.

## Operator tools

Default inspection/backfill is offline (it writes only the history directory and reports):

```sh
PYTHONPATH=. .venv/bin/python scripts/crawl-history.py --data-dir DATA_ROOT
```

Use `--watch` to observe continuously or `--history-dir` for a separate writable history volume. To clear an actually reviewed hold, supply `--resolve-hold host:HOSTNAME --evidence review:TICKET_REFERENCE`; target hold keys are included in the ledger. No holds were cleared as part of installing this history feature. Use references rather than credentials, source bodies or private data in review evidence.

Tower source/live overlay: `compose.crawl-history.yaml`, profile `crawl-history`, service `bord-food-crawl-history` in `tower-productivity`. Only this observer service is recreated on updates. Its health check requires a fresh heartbeat and an empty scan-error list. Restart policy is unless-stopped; repeated snapshots do not duplicate outcomes. No national crawl activation or serving API/Bòrd image update accompanies this service.
