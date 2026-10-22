# Implementation decisions

Implementation decisions follow the original template table; actual checkout drift and justified choices are recorded below.

| Date | Task/ADR | Decision | Evidence | Downstream tests |
|---|---|---|---|---|

## 2026-10-17 implementation execution

- Baseline: `main` at `13ba74e56f9d383edb2cfc57d4020d2c9943705e`. Preserve existing `.env.example`, README and untracked documentation/plans. No production data file is used for tests or modified.
- Execution map: F01–F02 compatibility/network boundary; F03–F06 immutable platform/control; O01–O05 worker/transport; S01–S06 directory sources; P01–E03 optional food/evidence sources; C01–M02 disabled crawlers/maps; A01/B01 generated contract and companion handoff; D01–D03 operations; Q01–Q02 offline acceptance and review.
- The main implementation prompt explicitly permits parallel module ownership after shared contracts stabilize. Root owns control/publication; independent agents own parsers, native API/maps, and runtime/transport.
- V1 packs use a versioned SQLite entity table with FTS5 and spatial RTree plus typed kind, source namespace, content revision and JSON payload. USDA retains its exact existing SQLite schema and payload normalization. This avoids rewriting compatibility code and keeps optional licensed sources independently removable.
- Identity alias decisions are explicit and reversible. New source keys allocate permanent IDs; automatic cross-source/name/proximity merges are withheld. Substantial location changes preserve the former site facts and add review evidence.
- Bòrd is available for read-only inspection; this repository task does not authorize companion writes. Deliver generated contracts and a separate companion handoff. No claim of companion UI implementation.

- Complete source coverage is distinct from complete fields: missing values in a store feed retain prior assertions. Source absence advances only for a distinct comparable validated release, and never proves closure.
- Group-normalized store facts ignore presentation/fetch noise. OFF maintains a separate per-record source clock in its private pack, so a timestamp-only update does not rewrite facts but an older correction still cannot overwrite newer evidence.
- Reviewed canonical merges retain source assertions; transitive redirects are frozen in each generation. Identity editing shares the publisher lock. Rollback publishes a new generation with the selected generation's sources/crosswalk, and atomically recoverable checkpoint replacement.
- Rights are per action. Retention expiry/revocation blocks reads and export; display denial can retain bytes while hiding records. Backup/restore and rollback reject forbidden payloads, including embedded alias assertions. Cleanup requires actual reader quiescence.
- HTTP generation selection uses a request context snapshot. Native queries cannot mix pointers during publication/rollback; control-only feed checks and job metrics may remain fresh.
- OFF unproven extraction boundaries produce a labeled snapshot-only pack, not a fabricated baseline watermark. A verified operator/source boundary is required for native-delta alignment. SNAP retains unresolved status when official current-resource discovery cannot be established.
- Documentation's plan validator now accepts evidence-bearing implementation progress rather than requiring every task to remain not_started. Its original formatting/lint defects were fixed; the manifest is refreshed for modified plan progress artifacts, without changing reference data.
- Docker was used only for explicit local synthetic smoke/empty-image verification under an offline source policy. No remote deployment, Unraid deployment, image push or source acquisition was performed.
- Final offline evidence: 209 tests passed; Ruff, formatting, generated OpenAPI, TypeScript starter, existing Bòrd USDA provider and local synthetic container checks passed. Concurrent control initialization is serialized before WAL setup. Restore prevalidates the control schema before copying objects. OFF gaps attempt one full baseline recovery in the same job, with safe fixed status reasons and no checkpoint advance before publication.
- All 35 main V1 tasks have API implementation/handoff evidence: 34 completed offline and B01 handoff complete. Companion T36–T39, every live activation and five later-phase tasks remain explicitly unperformed. External operator configuration/secrets must be backed up separately and current rights applied during restore.

- On 18 October a new owner request explicitly authorized GitHub publication and Tower deployment/configuration. The tested image is pinned by full application SHA; only the food API service is recreated. Core USDA/selected ATP automatic bulk updates are active; optional/crawler/paid sources stay off. The former local-catalog pin was explicitly overridden for managed refresh while preserving the original database and backup.
- Live ATP delivery uses the reviewed exact `alltheplaces-data.openaddresses.io` origin; the observed successful output run is older than the global/current check date. Current source coverage is recorded as imported observations, never a national census. Live evidence is separate from the prior offline task record and from companion UI/migration acceptance.

## 2026-10-18 — Authorized bounded source pilot

Keep operator activation distinct from offline V1 completion. Register Woodman’s as an optional reviewed ATP spider without expanding four-spider defaults. Run one source-backed branch’s link-only crawler with two requests, 20-second pacing and the owner’s real contact; pause and close activation afterward. Map discovery grants no media rights.

Select FoodKeeper’s observed exact English resource from its multilingual legacy-HTTP catalog and use HTTPS only. Parse actual workbook cell arrays and retain condition fields/metadata; never substitute third-party food safety guidance when FSIS returns 403. Keep live size unknown and distinguish isolated synthetic volume calibration.

Omit Open Prices null-location observations from a US-scoped pack, while rejecting unresolved non-null related IDs. Prefer native country codes to display labels. Keep price data isolated pending currency/freshness/store-match review; proximity is candidate evidence only. OFF remains snapshot-only without an extraction boundary, and a full baseline requires capacity rehearsal. Two bounded synthetic Jev calls validate capabilities; no unattended AI or model-derived source facts.

## 2026-10-19 UTC — National staging only

The owner requested crawls for every state, explicitly not execution. Reuse the already acquired/pinned ATP archive for offline workstation discovery; create separate state plans for all 50 states and separate DC. No national source activation, catalog publication, jobs, schedules, retailer requests, paid calls, image build, Git push or serving deployment. Record owner public-page/robots authorization separately from terms/media rights. Reuse the existing Jev shared cumulative $5 ceiling; zero staging reservations, no per-state budget multiplication.

Keep exact source/native identities and banner candidates before location reconciliation. Unknown/conflicting state, missing branch URLs and failed scopes remain visible gaps; no geographic/name guessing or census/closure claims. Deduplicate the national URL queue and hold multi-identity URLs. Future states share one serial worker, durable host frontier and model ledger. Resolve canonical IDs/address snapshots against the actual published directory before any later explicit activation.

Extend the optional collection profile beyond map links into separately stored structured store/product/offer/placement evidence plus visible source text. Rich evidence requires review; it is not automatically promoted to accepted catalog facts. Require explicit address association and explicit offer-to-branch references, preserve exact decimal price/conditions/provenance, leave stock/timezone/aisles unverified, and retain media permissions off. Bòrd household behavior remains separate. Prepared batches default disabled, with zero paid budget and all host activation gates off.

Owner's final national scope clarification: retain store details, maps and aisle/department information, but avoid full product inventory capture. The final `public-store-layout-evidence-v1` profile therefore disables product catalog, inventory, prices and product-page fetches. Only incidental item-to-aisle references (name/native SKU/GTIN/placement properties) are retained for association with separate product databases. No offers, nutrient/ingredient packs or full assortment extraction. This supersedes the broader evidence-profile choice above; no version was executed against retailers.

## 2026-10-19 UTC — Larger Iowa execution

The owner's “begin the larger Iowa crawl” authorizes this state alone to execute; nationwide staging remains off. Use all319resolved branch candidates, retaining28previous host holds and43missing URL records as explicit gaps. A persistent serial controller defers pending branches across daily budgets instead of treating a short qualification pass as statewide completion. Keep original cumulative$5 model cap; new$4.37 reservation ceiling can pause with pending targets. Reuse the existing tested image with a separately pinned read-only source/config release; do not recreate API/Bòrd or require a Git push/image publication. Full inventory/catalog/price capture remains excluded. No uncertain evidence is promoted to accepted store/aisle/route facts.

## 2026-10-19 UTC — Cross-run target outcome notes

The owner requires failed-target notes throughout every state/run and future executions. Add a separate append-only SQLite operational history rather than altering serving packs or replacing previous run logs. Record per-state/per-run target outcomes, known reasons/HTTP codes/stages/timestamps, retry status and metadata binding; retain unknown historical details explicitly. Missing URLs, inherited/non-attempted holds and host/budget deferrals are distinct from failed HTTP requests. Later success does not delete prior failure evidence; resolving a hold requires an evidence-bearing operator review, without enabling sources or bypassing existing crawl gates.

Use a network-disabled observer with read-only catalog/status/code mounts and a separate history-only writable volume to backfill and follow the currently running pinned Iowa worker without restarting it. Register only whitelisted sanitized metadata/fingerprints; do not expose protected parent directories, keys, headers or arbitrary exception text. Updated future runners journal at source/terminal checkpoints and consult prior history; future state preparation returns held targets with event references. No other state activation, API/Bòrd image update or additional observer model/source calls.

## 2026-10-19 UTC — Owner-authorized Iowa pacing amendment

Increase only the active Iowa campaign to500requests/day/hostname and explicitly resume pending targets. Keep45seconds as the minimum, add one uniformly random0–45second sample per request (including robots), and apply stricter robots delay/rate before adding jitter. Persist previous/current configuration fingerprints through a locked offline pacing-only amendment. Preserve target identities/outcomes/holds, host request counters, campaign start/deadline and cumulative$5 Jev ceiling. No other state activation, target retries, full product inventory capture or serving API/Bòrd update.

## 2026-10-20 UTC — Iowa discovery coverage repair

Owner authorized resolving missing locations/expanding discovery toward full coverage and selected all grocery stores including independents. Preserve the existing directory and add provider-backed assertions through a separate explicit Iowa operator source; do not infer a census from a single ATP export, SNAP enrollment, OSM tagging or a planning estimate. Verify the official FNS ArcGIS publisher/schema/frozen Iowa ID set/source clock; supplement with one bounded OSM state query. Keep native IDs, raw assertions, per-row attribution/licenses and all review/exclusion outcomes. Broad Super Store/Other categories require grocery-format filtering/corroboration; pharmacy/dollar/convenience/specialist exclusions and conservative address/identity holds take precedence. Operator format reviews are bound to exact input/payload hashes and evidence, never name/proximity-only canonical merges.

Treat incomplete ATP output as partial even if aggregate errors are zero: require pinned detailed stats, normal finish, drained queue, raw-export count equality and count-decline review. Unverified archive members remain partial. Preserve last good count and all serving identities; absence cannot delete/close stores. Use fenced immutable publication after real-image network-disabled rehearsal/replay and consistent current-generation backups. Roll out the guarded adapter as a versioned read-only module mount in the existing API image; preserve unrelated Compose text and Bòrd/history services. No new image/push is needed.

Explicit bulk acquisition/publication is authorized; periodic Iowa discovery scheduling, other-state crawls, further paid calls and full inventory capture are not activated by this repair. Repeating a dated run is idempotent; later dated acquisitions can refresh native assertions while holding changed identities. All99counties in SNAP demonstrates source reach, not full operating-grocery coverage. Retain501 first-pass source assertion reviews and the unresolved DIAL/SAFHER active-license denominator; do not present these as501 distinct missing stores or claim100% coverage. New directory coverage is separate from retailer hours/maps/aisle enrichment and companion code changes.


## 2026-10-20 UTC — Field verification, local dashboard and retained product publication

Owner requested richer store fields, explicit permanent-closure status, verification/conflicts,
additional source research, usable product/guidance browsing and geographic dashboard metrics.
Owner selected US-labelled OFF products. Retain independent source assertions and original source
records; do not use model confidence, source absence, corporate contacts, banner names or proximity
as branch facts. Promote fresh exact-branch agreement across provenance families, preserving all
conflicts and operator reviews. Entrances and aisle/category mappings require explicit review.
Derive IANA timezone only for US states wholly in one timezone; label it derived. Keep holiday
exceptions dated and source-backed. Closed hours do not imply permanent business closure.

Reprocess retained SNAP/OSM/page evidence without source/paid requests. Implement Overture and
Foursquare retained-extract adapters but do not activate their acquisition. Future state runners
can reconcile fields from an already approved page without another fetch or model call. Existing
robots/delays/budgets/holds stay intact; historical active worker scripts are not silently replaced.
All non-Iowa state campaigns remain staged, and full product inventory capture remains excluded.

Publish USDA branded projections preserving FDC IDs, GTIN validity, original nutrients and source
references, then import the owner's selected OFF subset from retained bytes in a network-disabled
worker. Same GTIN does not merge product records or establish branch stock. OFF has no proven
baseline boundary; no delta watermark or continuous freshness is claimed, and recurring OFF stays
disabled. Use a separately attributed official Cold Food Storage Chart subset for guidance while
full official FoodKeeper JSON remains HTTP 403; do not call the subset a full FoodKeeper import.

Unraid activation uses versioned read-only module mounts on the existing pinned serving image;
no new Git push/image publication or Bòrd companion code change. Keep Bòrd/history starts intact.
For enlarged packs, batch identity transactions, stream complete-snapshot membership checks and
cache only successfully validated immutable-object inode/size/mtime/ctime signatures in a bounded
process-local cache. Changed metadata still forces checksums and SQLite integrity checks; first
validation per process/object is full. Explicit force=True remains available.

## 2026-10-20 UTC — Iowa field pilots and selective $15 Jev ceiling

The owner authorized Iowa-only field improvements and several small live pilots before a statewide
refresh, deferred pricing/full inventory, and explicitly raised the cumulative Jev ceiling to $15
with selective usage. Keep other states staged. Retain real contact, 500 attempts/day/hostname and
45 seconds plus random 0–45 seconds or stricter robots rules; failed/robots attempts share counters.

Fresh, valid, exact-branch source reports may fill gaps as source_reported, with null verification
dates. Corroboration still requires two independent families. ATP/direct retailer/provider copies
count as one retailer family; independent conflicts remain. Hold shared provider emails for branch
scope review. Closure and reviewed spatial fields retain stronger gates. Jev reviews uncertain,
new/provider/canonical pages and a sample; it cannot invent facts, verify fields or grant rights.

Use a pinned public Iowa Overture extract with exact joins, licenses and provider lineage. Only
exact SNAP plus Overture pairs introduce new stores in this pass; unmatched assertions remain
review candidates, not a missing-store count. No authoritative census denominator was obtained.
Allow one explicit robots alias fetch and one observed canonical-URL follow-up pass, never arbitrary
branch redirects. Preserve actual access holds and raw failures. Inherited holds and metadata
upgrades must not create new host failures or reopen reviews of the same physical attempt.

## 2026-10-20 UTC — Repeatable Iowa quality and bounded post-pass OpenAI

Apply versioned US chain extraction/normalization profiles on future source imports across states,
with conservative independent fallback. Exact source postal text may fill structured components;
retained exact name/address-bound source points may fill missing coordinates, with conflicts held.
Keep operator-reviewed aliases payload-bound/durable and format exclusions separate from closure.
Publish replacement store packs; preserve raw IDs/assertions, other states and non-store packs.

Owner authorized one separate OpenAI Iowa pilot up to $2. Use one Batch containing at most nine
actual inference requests, source fragments only, no search/tools/images. Strict output schema is
not factual verification: require retained exact quotation, branch/document/field/revision binding,
normalization/value equivalence, phone-scope and complete weekly-hours checks. Retain underlying
source lineage/clocks and model annotation; model is never an independent corroboration vote.
Reserve conservatively before transport, no automatic inference retry; post-pass hook prepares
only. Missing source evidence stays missing; other states and additional paid passes remain off.
Research Iowa licensing/WIC/address-point sources; no current complete licensing export or live
geocoder was acquired. No assumption of closure from inactive licenses or benefit authorization.
## 2026-10-20 contact enrichment follow-up

Repair retained evidence before more crawling. A full-week source may fill unknown days only when
all reported overlaps agree; it does not gain independent verification for unreported days. Keep
chain customer-service/ambiguous toll-free/department contacts scoped, with legacy selections
explicitly marked non-direct. Source acquisition clocks and raw source records survive reparsing.

Keep official-directory leads exact-address-bound and separate from branch facts and access
permission. Reuse the contact-panel parser, website-platform classification, normalized exact joins
and all-state name matching in future states, with fresh state-specific source/activation review.
Require accepted missing-field gains between small pilots and a wider pass. Empty/truncated model
context is a parser defect, not a reason to lower confidence requirements; retain failed reviews.
The October20 live first pilot and one corrected-context re-review did not pass the missing-field
gain gate, so follow-up phases remain staged/held. No new OpenAI job or national activation.

## 2026-10-21 UTC / October20 CDT — Explicit smaller-state activation

The owner's next instruction authorizes a first12-state cohort, selected by FNS grocery-format
record counts. Use counts only as a source-dated scheduling proxy; they omit non-SNAP shops and
precede brand review. Keep all50 ranks, retained assertions and published-store counts separate;
do not subtract mixed-grain source counts as exact missing-store coverage. Group similarly small
states into serial <=650-reference-record batches, at most three states, with shared host budgets.

Reuse explicit-state field/profile/contact parsing and add only new native retained ATP keys under
partial operator-state partitions. Preserve other states and original source records/refs; hold
co-located identity doubts and shared URLs. Qualify each state with <=5 reviewed pages before
<=25-page chunks; a failed state pilot does not justify blocked-host retries or stop unrelated
qualified states. The prior Iowa hold remains intact. Existing$15 Jev cap is shared across all
states, not renewed; no further OpenAI/image/inventory/price work. Keep the running frozen release
and latest staged resume-only backup completeness guard distinct in receipts.
