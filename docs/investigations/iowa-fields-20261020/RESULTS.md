# Iowa field expansion — 20 October 2026

Owner scope: Iowa groceries including independents; improve branch fields before a statewide
refresh; pricing deferred, no full inventory. Owner raised cumulative Jev ceiling to $15 with
selective calls. Public source requests use hello@foldlab.app and existing robots policy.

## Published results before the statewide refresh

Directory: **735 → 741 Iowa stores; 9,309 → 9,315 total**. Six additions required exact
SNAP-plus-Overture name/address corroboration and duplicate/format/closure checks. Existing IDs
are preserved. Iowa is not a complete active-license census. Licensing coverage remains unresolved;
SNAP membership and OSM/Overture assertions alone do not prove every active grocery is covered.

| Field | Before, 735 stores | After, 741 stores |
| --- | ---: | ---: |
| Phone present | 287 | 503 |
| Website present | 331 | 480 |
| Normalized weekly hours with IANA timezone | 10 | 314 |
| Derived America/Chicago timezone | 735 | 741 |
| Branch email, provisional source report | 0 | 84 |
| Departments | 0 | 11 |
| Accessibility | 0 | 10 |
| Pickup link / delivery link | 0 / 0 | 1 / 1, unverified |
| Dated holiday exceptions | 0 | 0 |
| Reviewed entrances / aisle mappings | 0 / 0 | 0 / 0 |

For the unchanged 735-store cohort, phones are now 497 and websites 476; the other
six records are new additions. The earlier 357 raw hours strings are distinct from the ten normalized weekly schedules.
New provisional reports are not independently verified. Corroborated phones increased
103 → 252, websites 17 → 116; normalized corroborated hours remain 10. All email/departments/
accessibility counts above are source_reported, with null verification dates. Retained shared
provider emails were removed from 86 branch-specific fields (corporate/customer-service scope).
Conflicts increased from 61 across 46 stores to 217 across 182 stores because more sources are
now compared, not because disagreements were discarded. There are 616 coordinate-bearing stores;
125 lack coordinates. No permanent closure was invented. Current unknown status remains unknown.
See completeness-before-statewide.json for per-field statuses and exact denominators.

Overture public release 2026-09-23.1 was queried to an Iowa/US geographic subset with an anonymous
local DuckDB operator tool, not an application dependency. Retained 1,758 rows / 2,856,938 bytes;
SHA256 55a9f0dbc6cc4bb280218f7193b06b407ea44e3991b587ad6c933df8b93e2ea6.
1,258 grocery-classified assertions, 425 exact assertions matched 410 prior stores; 833 unmatched
assertions remain review candidates, not distinct missing locations. CC0/CDLA-Permissive-2.0/
Apache-2.0 provider attribution and source property lineage are retained. Computed confidence and
Overture-signals do not create votes. No paid source API or national extract was acquired.

## Small live pilots and corrections

| Run | Actual result |
| --- | --- |
| pilot1, four targets | Jewel published; Natural Grocers and Family Fare held; old ALDI URL policy block. Three Jev calls. |
| pilot2, five targets | Save A Lot and Natural Grocers published; Sam's Main Street Market invalid robots media held; Wheatsfield parser TypeError paused with Whole Foods pending. Two Jev calls. |
| pilot2-repair | First nullable-attribute repair was incomplete; TypeError remained, no paid call. Retained page and safe stack frames identified the remaining path. |
| pilot3, three targets | **3/3 published:** Hy-Vee Dollar Fresh Maquoketa, Wheatsfield, Whole Foods West Des Moines; all extracted phone, website, weekly hours. Three Jev calls. |
| pilot4, three new/canonical URL targets | All held by redirect policy, no paid calls. |
| redirect-review, same three | Recorded HTTP 301 locations, no branch redirects followed and no paid calls. |
| pilot5, corrected hosts | Valley Fresh Elgin published phone/website/hours; Graziano Brothers retained for branch review; ALDI inherited history hold discovered. Two Jev calls. |
| pilot5-aldi-repair | After metadata-only hold repair, current ALDI site **robots_denied**; no branch request or Jev call. Genuine restriction retained. |

Changes driven by these runs: visible/hydration/Yext literal JSON extraction, exact full-address
matching, department-vs-grocery hours separation, percent-decoded telephone links, day-range
normalization, nullable HTML attributes, bounded DOM and exact branch department tables. No JS
evaluation, assets or product inventory. Seven retained approved pages were replayed offline
with original retrieval clocks/hashes and source identity; latest v6 replay changed Jewel and
Hy-Vee only, zero source/model calls. Model answers never promoted facts or merged store IDs.

History correctness also improved: inherited holds cannot create new host blocks, and parser/
metadata re-ingestion cannot reopen a review of the same physical attempt. The separate repair
receipt records 94 metadata-only/inherited holds reviewed; no new actual access denial cleared.
Earlier pre-fetch-only semantic holds and two exact-address parser holds had evidence-bearing
reviews; old failure events remain retained. Unknown/real access restrictions were preserved.

## Statewide run

`iowa-fields-statewide-20261020` is launched on Unraid in
`bord-food-iowa-fields-statewide-20261020`, **in progress, not complete**. Config includes
481 unique URL targets across 111 hosts plus 260 explicit missing/unsupported/shared URL gaps,
accounting for all 741 directory records. A primary pass plus at most one bounded observed
canonical-URL follow-up runs serially under the same host counters/leases/budget. Prior actual
access holds remain active. No other state is activated. First request/startup evidence is in
live-verification.json and statewide-runtime.json; consult those point-in-time receipts.

Frozen operator release:
`28d60800261366ea5d2f3ac025a84dafd7e3589e95dca6da2d59f5eb630b3b89`.
Existing pinned image sha-f177b5e / image ID
169264bb538c8add672750b01d0124489237e1cc7379c24975915466a8e3ded3.
No Git commit/push, image build/publication or frontend deployment was needed. Worker UID99:100,
1GiB/1CPU, read-only root/code/config/key, dropped capabilities, no-new-privileges, no published
ports. Only worker has source egress. API/history module activations were separate scoped changes.

500 attempts/UTC day/hostname, 45–90 second minimum randomized spacing, stricter robots first;
robots/failed attempts count. Explicit robots aliases are bounded and paced. Conditional cache,
no-store/Vary handling, 304 revalidation and Retry-After backoff are tested. No IP rotation or
restriction bypass. Jev is selective, pinned 1.14.0, cumulative $15 including prior reservations,
maximum $5 per pass. Reservations are not invoice spend. Parent STOP interrupts the child before
requests/models/publication; seven-day deadline, no automatic restart. See ../../IOWA-FIELD-CRAWL.md.

## Validation and limits

Tower repository validation passed with existing generated-output/archive findings. Plan package
validation passed 13 groups/93 checksums. TWR-054 was recorded; Forgejo issue creation returned
HTTP 502, so no linked issue was created. Actual final **374 tests passed, one upstream Starlette warning, 14.51s** using
`.venv/bin/python -m pytest`. Ruff check and 179-file format check passed; generated OpenAPI
matches; `git diff --check` passed. Routine tests used synthetic fixtures/mocked transports.
Actual pinned Python 3.12 image preflight ran with network disabled and passed provisional
field publication/retention; model/source requests zero. Offline campaign plans passed on the
real Unraid image before launches. Network-disabled enrichment and replay acquired no new data.

Serving store-field module SHA256
efc76d66a40f597fc9a188bbd8c65d0fccaac7539844643938e25aeb19164aa2,
version store-field-evidence-v3. API-only update verified healthy; history-only update verified
healthy with network none. Direct container/API checks and preservation assertions are in
live-verification.json. Bòrd was separately updated by its own thread to rc.18; this work did
not implement or deploy companion code and preserved its current start time during scoped updates.
All unrelated dirty repository work was preserved.

Products/guidance still expose **455,458 USDA branded products and 49 official Cold Food Storage
Chart rows**. USDA legacy pack remains 469,046 foods including Foundation/FNDDS/SR Legacy generic
fallback data. No pricing integration. Full FoodKeeper still blocked by official HTTP403.
The retained US-labelled OFF worker is **failed**, not running or published: 597,000 selected
before `Duplicate source key`. Existing products remain safe/unchanged; no OFF delta boundary,
watermark or freshness is claimed, and automatic OFF is disabled. This separate import defect
was recorded but not repaired within the Iowa field task.

Remaining gaps: authoritative census denominator, 260 branch URL gaps, held/review pages,
conflicting values, coordinate gaps, direct verification of provisional contacts and explicit
holiday/access/entrance/aisle evidence. Fields stay zero where no suitable evidence exists;
models do not manufacture data to improve a completeness score. No claim of 100% Iowa coverage,
full statewide completion, full FoodKeeper/OFF activation or companion feature completion.
