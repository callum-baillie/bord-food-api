# 05 — Incremental synchronization and field volatility

## Three independent forms of incrementality

**Network:** avoid a transfer using release IDs, ETag/Last-Modified, provider deltas, selective source files and bounded detail requests.
**Processing:** normalize/index only new or materially changed records after raw and normalized hashes.
**Publication:** replace only affected immutable packs, retaining other object references.

A source that only publishes snapshots may still require a full changed snapshot download. Do not describe a locally diffed full download as upstream delta access. CPU/storage savings and request savings are separate metrics.

## Persistent state

Per source partition (e.g. ATP spider, USDA data type) retain: last discovered release, resolved URL/validators, content hash, parser/filter/config version, staging checkpoint, published watermark, snapshot coverage scope, last successful full reconciliation, and the last **distinct source run** used for absence tracking. Per source record retain stable source key, raw/business group hashes, source membership and observation revisions.

`last_checked_at` advances after a network check. `source_observed_at` advances only with genuinely new source evidence. `fact_changed_at` advances only on a business-field change. HTTP 304 proves unchanged representation relative to your validator, not that every real-world value was freshly verified by the retailer.

## Release-level algorithm

```text
if effective network/source policy disallows this operation: blocked_by_policy
resolve candidate artifact under allowlisted rules
if same immutable release + parser/filter versions + audit not due: no work
conditional download when supported
if 304: record check; do not enqueue every store
if payload bytes hash matches: no normalization; advance only supported metadata
otherwise: parse into private staging; detect schema/filter changes
compare source-key set and normalized group hashes to prior complete scope
upsert changed source assertions and allocate/reconcile identities
run validation; build affected catalog objects
publish manifest; THEN acknowledge watermark/source run
queue only justified follow-up work with a durable dedupe key
```

Do not trust ETag as a content checksum, or treat HEAD success as proof the body has the expected schema. Servers may not support HEAD/conditional requests. Fall back to a bounded GET/hash at the relevant interval. Always account for bytes actually transferred, including range requests and retries.

## Snapshot diff

For each partition use a staging membership table keyed by source namespace/key. Hash normalized business-field groups with stable key ordering; exclude fetch time, HTML navigation, advertisements and session IDs. Retain a raw hash separately. If parser version changes, replay cached bytes before making a new web request. If a geographic filter changes, rebuild membership and mark it a scope change: removed rows are not closures.

- **New source key:** resolve potential duplicate; create identity or queue ambiguity; source only missing fields.
- **Known key, same business hashes:** record membership/freshness without new enrichment/index writes.
- **Known key, changed hours/services:** update those assertions; no address/geocode work if identity/location group unchanged.
- **Known key, location conflict:** route correction/relocation review; preserve old address history.
- **Absent key:** only evaluate absence after a complete, validated, comparable source snapshot. Failed, empty, partial, filtered or stale runs never create absence evidence.
- **Explicit source tombstone:** withdraw that source assertion at its timestamp; do not infer global closure unless the source’s semantics support it.

A batch with unknown coverage cannot be promoted to “complete” because it returned HTTP 200. Evaluate row counts, required fields, pagination completion and source-specific structural evidence. Default proposed sudden-drop gate: more than 20% and at least 10 prior eligible records requires review; smaller sources use stricter per-source rules. This threshold is a safety heuristic, not a statistical truth.

## Lifecycle handling

Source absence after 3 distinct valid complete snapshots spanning at least 21 days may set `missing_from_source` and queue a bounded validation; it does **not** automatically set `closed`. A fresh explicit official closure/relocation can set the corresponding lifecycle state with evidence. Removal from SNAP only withdraws authorization; lack of OFF product data only withdraws that source’s product record.

A reappearing key clears that source’s missing status but keeps history. A newly opened store may lack hours/coordinates: publish known facts with unknown fields. Stable identity never depends on array order or crawl sequence.

## Proposed field policies

These intervals are local defaults, not claims of data validity or vendor retention permission. “Days” are scheduled UTC durations with jitter. Directory updates can immediately supply changed values without waiting for the detail-crawl interval.

| Field group | Normal detail recheck | Triggers that bypass normal interval | Why |
|---|---:|---|---|
| Canonical ID | Never regenerate | Reviewed merge/split/alias event only | References must be stable |
| Store existence/source membership | Weekly roster check | Explicit official closure/opening; source release changed | Discover new/missing stores cheaply |
| Address and coordinates | 180 days, staggered | Bulk hash changed; relocation notice; operator correction; conflicting identity | Low volatility, not immutable |
| Name/banner/operator | 90 days | Acquisitions/rebrand in source; bulk hash changed | Keep identity while recording changes |
| Phone, website, services | 30 days | Changed bulk/page validator; request for missing field | Moderate volatility |
| Main/department hours | 14 days for watched stores; 60 days otherwise | Official update, missing schedule, approaching known exception | Higher user impact; avoid nationwide daily crawls |
| Holiday exceptions | Only if source supports them; 3-day window checks around relevant dates | Published exception; watched store | Unknown rather than invented closures |
| Map candidate/page | 90 days; not-found backoff 30→90→180 days | New branch, remodel, changed map URL/hash, user request | Avoid repeated irrelevant downloads |
| Verified map asset | Conditional request when map version/page indicates change | Explicit remodel or changed asset hash | Image change invalidates old anchors |
| Product metadata | OFF deltas daily after enabled baseline | Source revision/pack conflict; explicit request | Product facts independent of branch stock |
| Public historical prices | Daily export check | New source release | Preserve actual observation date |
| Live price/availability | Demand only; retention from provider contract | Explicit bounded request | Never crawl every product × store |
| FoodKeeper | Monthly metadata/hash check | Official resource version change | Small/irregular reference data |
| SR Legacy | No routine data update | Repair or explicit source correction | Finalized source dataset |

`configs/field-refresh-policy.json` mirrors this policy. Unknown provider cache retention has no invented default: disable live caching/integration until validated.

## Field-level targeting has real limits

A retailer may publish address and hours in the same page. Refreshing hours may transfer that whole page; skip geocoding, identity resolution and address writes when the normalized location hash is unchanged. Do not promise field-only HTTP downloads where no such endpoint exists.

A new store already fully described by a bulk record does not need a detail crawl. Queue only missing required fields or an explicit map/enrichment request, and only for permitted sources. Batch source roster checks are distinct from visiting each store URL.

## OFF delta continuity

Source exporter evidence supports time intervals `(from,to]` over changed active products [S06]. Maintain a contiguous acknowledged window, not merely “highest timestamp seen.” Sort intervals, detect gaps, dedupe/replay overlaps, and compare source revision/timestamps before applying a row. A delayed older delta cannot overwrite a newer snapshot record. Equal timestamp with different hashes is a conflict, not automatic overwrite.

Baseline and delta clocks must overlap safely. Record the baseline retrieval window and export metadata; replay a verified interval beginning before its extraction started and extend to a known continuous point. A max timestamp found among filtered rows is **not** a baseline watermark. If a Parquet baseline cannot be aligned to the JSONL delta contract, keep it snapshot-only until alignment is proven.

Retention gaps, stale index timestamps, unresolvable baseline coverage, feed errors or parser changes trigger full reconciliation or source-degraded status. A full snapshot is not an atomic instant unless the publisher says so: stage it and reconcile overlapping changes. Complete deletions/obsoletes and automated recalculations still need periodic full/source-supported reconciliation. Never label these changed-product dumps a guaranteed complete CDC stream.

## Adaptive work and starvation

Maintain per-entity next-due timestamps and per-host quotas. Watchlists increase priority for selected branch hours/maps, not permission to exceed quotas. First discovery and integrity recovery outrank optional map refresh. Aging promotes neglected due jobs; low-priority work must not disappear permanently. One active job per `(source, partition, operation, effective_version)` dedupes concurrent requests and post-restart retries.

## Synthetic acceptance example

In `examples/synthetic/snapshot-diff-case.json`, a prior snapshot has two synthetic stores. The new complete snapshot keeps one unchanged, changes only the other’s hours and adds a third. Expected: one new identity, one hours update, zero address re-enrichment for the two existing stores, no closure, one conditional missing-field task for the new store **only if crawling is later enabled**. Applying the same snapshot twice creates no duplicate jobs or versions. These are not Walmart inventory/location observations.
