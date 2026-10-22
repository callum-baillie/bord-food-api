# Staged US grocery crawls

**Later activation:** the owner authorized a bounded scan of the 12 smallest states on October
20, 2026. See [Small-state scans](SMALL-STATE-SCANS.md) for the active plan, updated field runner,
500/day shared host policy and existing $15 cumulative Jev ceiling. The original staging
description/defaults below are retained as historical preparation evidence; the remaining
states are still inactive.

The national campaign is **staged, not started**. The current Unraid staging directory is `/mnt/cache/appdata/bord-food-api/crawl-campaigns/us-staged-20261019-r2/` (`bundle/` contains the state plans; `release/` contains passive runner code). This revision applies the owner’s final scope: store details, maps and aisle/department evidence, excluding full product/inventory capture. There is one plan for each of the 50 states and a separate DC plan. Territories are outside this campaign. These are source-backed discovery rosters, not a verified census of every chain or physical location. No manually researched chain list is promoted into catalog facts.

`stage-us-crawls.py` scans a previously acquired, SHA-256 pinned All The Places archive locally. It streams GeoJSON, uses source grocery formats and native IDs, retains source properties/CC0 attribution, and writes a private staging SQLite index. State names/codes and explicit postal suffixes are supported; conflicting/unknown regions are held. Malformed, duplicate-ID and oversized source scopes contribute no partial records or absence evidence. Missing stores never imply closure. The serving catalog is not opened or changed by staging.

Each state directory contains:

- `plan.json`: disabled activation, contact, provenance, collection profile, pacing/budgets, coverage gaps and field completeness.
- `chains.json`: source banner candidates, source scopes, counts and observed hosts. Counts precede physical-location reconciliation; equal names across sources are not silently merged.
- `roster.jsonl`: full normalized source assertions, addresses, coordinates, source IDs, phone, hours, website and original properties where supplied.
- `targets.jsonl`: exact source-supplied HTTPS branch URL candidates. Missing URLs, homepages, unsupported URLs and unsafe targets remain gaps. No guessed retailer URL aliases.

The root `coverage.json` includes all jurisdictions and upstream errors; `host-queue.jsonl` deduplicates exact URLs nationally and flags multi-identity URLs for review. `bundle.json` pins generated files. One shared Tower data root, frontier and Jev budget ledger must be used across all states. State partitioning does not multiply per-host limits.

## Collection when explicitly activated later

The optional `public-store-layout-evidence-v1` profile extends map discovery with separate review evidence:

- Exact branch-address association; source address, coordinates, contacts, regular/exception/department hours, services/amenities and payment data present in structured HTML.
- Explicit store aisle/department directories and layout properties, with source paths and unverified status. Incidental item-to-aisle references retain only name, native SKU/GTIN and placement properties to link to separate product databases. No standalone products, offers, prices, stock counts, ingredients/nutrition or full assortment are captured by this profile.
- No inferred aisle placement, stock, route coordinates or household preferences.
- Advertised interior map links, separately from geographic `hasMap` links. Image URLs can be recorded; image/PDF contents are not downloaded or rehosted. Media rights remain pending.
- Page URL, retrieval time, content hash, parser version, JSON source paths and a bounded visible-text excerpt. Observation dates remain unknown unless explicit in the source.

The owner clarified that aisle/department and map information should be retained alongside other useful branch-page evidence. The crawl remains limited to supplied branch pages; this does not authorize a separate product-page crawl.

The existing Jev pre-fetch and post-fetch branch/link decisions gate each page; model uncertainty can withhold publication. Full product inventory capture and separate product-page crawling are explicitly disabled. Product catalog/nutrition data should come from the separate bulk/database sources. Rich evidence goes under the campaign's `evidence/`, with `review_required` status, **not automatically into accepted store/placement facts**. Store hours still need timezone/holiday validation. Product discovery/feeds remain outside this crawl. There is no automatic pagination, login or endpoint guessing. Bòrd retains private receipts, pantry, shopping decisions and manual aisle overrides.

## Offline verification and preparation

From the repository root (commands below do not crawl):

```sh
PYTHONPATH=. .venv/bin/python scripts/stage-us-crawls.py data/nationwide-staging/us-20261019-r2 --verify
PYTHONPATH=. .venv/bin/python scripts/run-us-crawl.py data/nationwide-staging/us-20261019-r2
```

To reproduce staging with an existing archive, supply a **new** output directory and its independently recorded run/hash:

```sh
PYTHONPATH=. .venv/bin/python scripts/stage-us-crawls.py NEW_OUTPUT \
  --archive EXISTING_ARCHIVE --source-run PINNED_RUN --sha256 PINNED_SHA256
```

`run-us-crawl.py BUNDLE --state NY --data-dir DATA_ROOT --prepare NEW_CONFIG --offset 0 --limit 25` resolves one bounded batch against already published canonical store identities. It writes a disabled config with zero paid-call budget. Unimported/ambiguous/changed identities and shared URLs are held. Preparation does not import the rosters, enqueue jobs or enable sources. Importing additional roster scopes is a separate controlled publication, with backups, source-run checks, partial-scope semantics and USDA/other-state preservation checks.

## Activation remains unperformed

An operator must review the prepared config, exact targets and holds, refresh source identity/address evidence, finish or stop overlapping Iowa work, and choose a remaining shared Jev budget. Prepared host gates and `activation_enabled` start off. Only the separate explicit `--run CONFIG --data-dir SHARED_ROOT` path can execute, after all existing source, scope, canonical-store, model-budget and contact checks. Do not run it until national activation is requested.

Use one serial worker, batches of at most 25 branches, 45 seconds minimum between requests to a host (or stricter robots delay), one request at a time per host, 50 requests/day/host shared across states, 512 KiB HTML, no redirects or automatic retries, and the existing two-hour campaign ceiling. Fetch robots first and fail closed on unavailable/denied robots. HTTP blocks stop that host; no proxy/IP rotation or access-control bypass. The owner's public-page/robots authorization is recorded separately from retailer terms or media permission.

Jev uses the existing shared ledger and the previously approved **$5 cumulative cap**, not $5 per state. Stage/preparation reserve and spend nothing. Future runs need a protected key path and bounded per-batch budget; do not write key values into plans. Images/Box questions remain off; any future separately authorized image request would need the TypeSafe danger-zone header and independent image rights review.

No cron job, Compose service, container, source-policy change, national catalog import, paid call or national retailer request is installed/started by staging. Code changes and staged files do not update the serving API or Bòrd application.

Cross-run target outcomes and unresolved retry holds are retained in the shared [crawl history ledger](CRAWL-HISTORY.md). Use its history-enabled runtime for future activations; the existing state bundles remain disabled.
