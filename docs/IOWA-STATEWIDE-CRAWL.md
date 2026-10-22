# Iowa branch campaign

This document records the historical 19 October run. The newer 741-store Iowa field refresh
and updated $15 cumulative Jev policy are documented in [Iowa field refresh](IOWA-FIELD-CRAWL.md).

`iowa-statewide-20261019` expands the earlier 14-branch qualification pass into a durable queue covering all 319 currently supplied Iowa URL candidates. These resolve to existing canonical store IDs. The directory has 362 source store records;43 lack usable source website URLs and remain explicit resolution/review gaps. The pilot's blocked Costco/Target/Trader Joe's hosts account for28 targets held without new paid calls or requests. That leaves291 candidates eligible for live qualification, not guaranteed successful extraction. Coverage remains an incomplete source roster, not an Iowa census.

The separate Tower worker is `bord-food-crawl-iowa-statewide`, service `bord-food-iowa-statewide`, profile `iowa-statewide`, project `tower-productivity`, overlay `compose.iowa-statewide.yaml`. It uses the existing tested ed0edd4 base image and a read-only versioned Python release, not an update to the serving API/Bòrd. No Git push or image build is required. Source `retailer_maps` is enabled only for the explicit operator campaign and paused on exit.

One serial worker rotates hosts and retains target state. It reads shared host counters before any paid decision. Following the owner's 19 October pacing amendment, the limit is 500 requests/day/hostname (originally 50). Requests to the same host wait at least 45 seconds plus a new uniformly random 0–45 seconds; any stricter robots Crawl-delay/Request-rate replaces the minimum before adding that jitter. Robots requests and failed attempts count toward the shared persistent daily allowance; resuming never resets it. 512KiB HTML and two requests/page including uncached robots remain enforced. A day without enough request slots defers the branch until the next UTC day. Waiting releases the heavy worker lock so core bulk imports can proceed. Each fetch has a renewing job lease and checks source pause, STOP and SIGTERM. Access/policy failures hold the host and its remaining branches; uncertain model/source identity becomes a review hold. No automatic network/model retry or IP fallback.

The campaign may wait across days, with a seven-day deadline. Budget exhaustion is `paused_budget`, with pending targets retained; it does not report completion. Crash-interrupted targets require review on explicit resume, preventing duplicate paid calls/fetches. Automatic container restart is off. Resuming requires the same configuration and the `--resume --run` flags, within the unchanged budget and deadline. For an explicitly authorized pacing change, stop the worker and checkpoint its status/control/frontier/Jev/history first. Run `run-iowa-statewide.py NEW_CONFIG --amend-pacing-from OLD_CONFIG` offline: the controller lock excludes an active worker, only max_pages_day/min_spacing/spacing_jitter_seconds may change, and config_revisions retains both fingerprints. Then resume separately with the new configuration. Target identities, outcomes, counters, spend and original deadline are preserved. Other changes require a separately approved configuration/campaign.

The scope is `public-store-layout-evidence-v1`: store details, hours/services, map links, departments/aisles and incidental item-to-aisle identifiers. No full product catalog, prices, inventory capture or product-page crawling. Source URL/hash/JSON paths/text excerpts are retained under `evidence/` as review_required; they are not automatically accepted store/placement facts. No PDFs/images/assets downloaded/rehosted or implied route geometry/media rights. Bòrd household data and the other49states/DC staging remain untouched.

Jev uses the existing pinned model and shared ledger, with no key values in logs/config. Previous campaigns reserved$0.62; this campaign reserves at most$4.37/437calls, within the original cumulative$5 cap including the earlier pilot allowance. The conservative reservations may pause the queue before every eligible branch is checked. No additional spending was authorized or assumed.

Status: `/data/crawl-campaigns/iowa-statewide-20261019/status.json` (host `/mnt/cache/appdata/bord-food-api/crawl-campaigns/iowa-statewide-20261019/status.json`). Status includes pending/published/review/blocked/interrupted counts, active target, next host due time and budget; phase can describe the last action after a pause, so read state first. Published map records may be `not_found`; a completed check is not a discovered usable map.

From `/mnt/cache/git/compose/productivity`, stop only this worker:

```sh
docker compose --env-file .env -p tower-productivity -f compose.yaml \
  -f compose.iowa-statewide.yaml --profile iowa-statewide stop bord-food-iowa-statewide
```

Alternatively create the campaign's `STOP` file or pause source `retailer_maps`. Do not remove unrelated/orphan containers. Source pause/STOP persists until the operator explicitly resumes. Never apply an entire local productivity Compose file over the live project.

Pre-run backup `/data/backups/20261019-pre-iowa-statewide` contains the control/frontier/Jev SQLite snapshots (quick_check passed), current manifest and independent copies of its referenced immutable packs. USDA/store packs must remain identical during this map/evidence campaign. External protected source/Compose/credential configuration remains in the private Tower repository; secret rotation was not performed.

Cross-run target outcomes and unresolved retry holds are retained in the shared [crawl history ledger](CRAWL-HISTORY.md). Use its history-enabled runtime for future activations; the existing state bundles remain disabled.
