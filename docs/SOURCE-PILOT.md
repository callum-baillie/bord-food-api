# Source activation and validation pilot

Owner-authorized follow-up to V1 implementation, 18 October 2026. The owner permits a small, slow Tower crawl, live source validation and up to $5 total optional AI spend. This authorization is separate from the original offline implementation prompt. Companion household changes belong to Bòrd; this pilot changes only the food service and its operator configuration.

## Woodman’s pilot

Use one existing, source-backed Altoona branch from the published ATP `woodmans_markets_us` roster, not a hand-authored seed. Reviewed ATP spider: [upstream source](https://github.com/alltheplaces/alltheplaces/blob/master/locations/spiders/woodmans_markets_us.py). The dated 2026-10-10-13-32-41 output downloaded on Tower is 15,107 bytes and has 19 branches. Preserve its native reference, full address and observation date. Adding this optional descriptor does not expand the four default ATP selections.

Review [robots](https://www.woodmans-food.com/robots.txt), [terms](https://www.woodmans-food.com/terms-of-use/) and the [official branch page](https://www.woodmans-food.com/store-locations/altoona/). Advertise the owner-supplied reachable contact in private operator policy. Start with one branch HTML page, at most two requests including robots, 20 seconds minimum spacing, six requests per day and 512 KiB per response. Use the existing Tower egress address, without rotating IPs. Honor robots, failures and retry instructions; do not distribute requests to bypass limits.

The pilot discovers links only. Copyright/redistribution permission is not established: map bytes, embedded assets and receipt images are not downloaded, rehosted or sent to AI. Discovered links retain pending rights, no display/storage permission, no route graph and no aisle coordinates. After the explicit one-shot run, close the activation gates; no unattended crawler schedule is installed. Future batches require reviewed branch targets, observed first-run behavior and separate media permission.

## SNAP validation plan

Keep activation off until the [official FNS current retailer locator](https://www.fns.usda.gov/snap/retailer-locator) exposes a verifiable current resource or the operator supplies a reviewed current official HTTPS CSV. Do not guess a URL, use historical files as current or infer closure from absence.

1. Record source page/resource URL, retrieval and source dates, length, ETag and SHA-256; reject redirects to unreviewed origins, unexpected HTML and schema drift.
2. Validate stable FNS identifiers, duplicate/conflicting rows, required name/address fields, US/territory scope, postal codes and coordinate ranges. Report missing coordinates separately; do not invent them.
3. Publish first to an isolated catalog. Compare national/state counts, invalid/missing rates and stable IDs across two snapshots. Set initial tolerances from the measured baseline, then require review for unexplained drops, ID churn or geographic shifts.
4. Review stratified matches against ATP by state, banner, dense/rural geography and ambiguous addresses. Exact shared source evidence may link identities; names, chain tags or proximity alone create candidates. Retain source assertions and reversible decisions.
5. Record matched/unmatched/ambiguous counts and sampled false matches before enabling. SNAP means authorization evidence, not current stock, opening hours or verified closure.

Live source access was previously blocked; this pilot does not claim a current SNAP import or verified national coverage.

## OFF scope, size and baseline/delta validation

The official [JSONL export](https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz) redirects to the reviewed exact delivery origin `openfoodfacts-ds.s3.eu-west-3.amazonaws.com`. On 18 October the object advertises **13,179,356,850 bytes (13.18 GB; 12.27 GiB)**, Last-Modified 06:41:48 UTC. It is a worldwide compressed export; filtering to US products reduces retained records, not the full baseline transfer. Images are separate and excluded.

Tower fetched only the first 4,194,304 compressed bytes with an honored Range response. That prefix expands to 26,663,994 bytes and contains 1,124 complete records, 847 tagged US. This ordered prefix is **not a representative sample**, complete baseline or count estimate. Its local expansion ratio would imply roughly 84 GB for the whole object, but that is only a rough planning warning, not a measured full-export size. Product count and final normalized pack size remain unmeasured. Do not budget from the 4 MiB compressed prefix alone.

Initial proposed scope: `en:united-states` plus explicitly retained valid product codes, separate ODbL attribution/provenance, no images, no automatic nutrition-conflict averaging or branch-stock claims. Start with snapshot-only publication. Before a full run, reserve space for the 12.27 GiB artifact, staging/joins, current and replacement packs, retained generations and the 5 GiB free-space reserve. The current service quota is 50 GiB; a full-import capacity rehearsal and explicit retention budget are needed before enabling automatic OFF bootstrap. Stream the input; do not load it into RAM. Measure actual disk/RSS and restart/rollback behavior under Tower’s 2 GiB container limit.

Baseline/delta acceptance:

- Capture object version/ETag/hash and source-proven extraction boundary. Last-Modified, retrieval time and max product modification time are not a valid extraction boundary. Without one, keep `watermark=null` and reconcile full snapshots.
- Read the official delta index, sort intervals, require contiguous `(from,to]` coverage from the trusted baseline boundary. The current index lists 13 intervals. Validate archive schema before publication; re-read/compare the baseline version if acquisition overlaps a replacement.
- In an isolated catalog apply a baseline and consecutive deltas, replay them, interrupt before/after publish, and compare the resulting normalized hashes against a fresh equivalent snapshot. Test missing/overlapping/out-of-order windows, deletions/tombstones, US scope exit/re-entry, retained codes, null/zero nutrients and malformed GTINs.
- Advance the cursor only with the visible generation; a gap, expired window or filter/parser change triggers one controlled full reconciliation. Keep the previous catalog serving on failure. Existing offline tests exercise these cases; live baseline/delta equivalence has **not** been established.

## Open Prices validation

Downloaded the three official [daily exports](https://openfoodfacts.github.io/open-prices/guides/data/) into an isolated Tower validation directory; no price pack has been published. Compressed sizes: prices 21,976,348; locations 1,200,771; proofs 9,419,141 bytes; total **32,596,260 bytes (31.09 MiB)**. Expanded JSONL totals **351,258,598 bytes (334.99 MiB)**. Record counts: 330,576 prices, 7,599 locations, 129,005 proof metadata records. No proof media was fetched.

The initial installed parser rejected a null location after 27,713 US rows. This is unknown location, rather than a dangling non-null reference: the correction omits it from US coverage while still failing on unresolved non-null locations/proofs. Complete scans find one null location, zero missing non-null proof references, 129 observations without a proof reference, 42,822 US observations across 368 locations and 26,689 distinct valid US GTINs. Eleven US-located observations use non-USD currencies and need source review, not conversion or silent relabeling. Dates range back to 2016; these are historical observations, not current offers.

The serving ATP roster (8,646 stores before the pilot; 8,665 after adding Woodman’s) exposes no shared OSM IDs; exact source-ID branch matches are zero. Distance/address/name matching may propose reviewed candidates but must not auto-merge. Check OSM object type, country code, shop type and stale/brownfield locations, chain ambiguity, coordinate distance, source validity and observation dates. Review current/local coverage before enabling a public price pack. Product GTIN matches establish product evidence only, not store identity or current stock. Retain ODbL attribution and raw decimal/currency/discount conditions.

## FoodKeeper implementation and storage

The [official catalog](https://catalog.data.gov/dataset/fsis-foodkeeper-data) lists English, Spanish and Portuguese JSON resources with legacy HTTP links. The resolver now selects the **observed exact English path** and requests its HTTPS equivalent; it never downgrades TLS or invents a mirror. The parser supports workbook rows made of one-field cell objects and reviewed flattened rows. It preserves source IDs, category joins, workbook metadata, opening/thawing/purchase/storage conditions, verbatim units/ranges, null and zero; rejects duplicate fields/IDs and unresolved categories; and never assigns an exact expiry date.

FSIS HTTPS HEAD/GET returned **403 from the workstation and Tower**. Therefore the live English dataset has not been imported and its current byte/record/normalized size is unknown. An older official directory listing showed about 617 kB, which is historical context, not a current measurement. A third-party derivative was examined only for schema research and was **not imported or treated as an official current snapshot**. Keep the source disabled until an official HTTPS artifact can be validated. The download cap is 32 MiB expanded by default. The isolated synthetic import/storage rehearsal described below validated the mounted volume and immutable publication, but cannot establish the live source size.

## Optional AI experiment

Two explicit Jev `jev-1.14.0` calls succeeded: synthetic map-link classification, and a 640×480 original synthetic department diagram with a side Choice and a Box question. The image request included `TypeSafe-Danger-Zone-Images: true`. Results: map candidate; produce on left; box confidence 0.93. No retailer media, household data or keys were included in results.

Usage: 404 + 1,159 = **1,563 input tokens**, 99 output tokens. At the [documented](https://docs.typesafe.ai/models) $0.042/M input tokens and free output, estimated cost is **$0.000065646**, not an independently reconciled account invoice. The experiment capped itself at two requests with no retries (64k per-call maximum implies a conservative $0.005376 input reserve), well under the owner’s $5 total cap. No recurring paid connector or automatic enrichment was enabled. Suggestions must remain reviewable and separate from nutrition, safety, identity, placement and routing facts. This establishes API/image capability on synthetic input, not production image accuracy.

## Execution evidence

Code checks before publication: `python -m pytest -q`: **219 passed**, one upstream Starlette TestClient deprecation warning, 7.34s. `ruff check .`, `ruff format --check .` (92 files), and `python scripts/export-contracts.py --check`: passed. Routine tests use synthetic fixtures/mocked transports. Additional live deployment/pilot results are recorded below when actually performed.


## Completed Tower execution

Application commit **f177b5e1106484c6ca2dffb36fa035c514280d30** passed [GitHub run 39156343117](https://github.com/callum-baillie/bord-food-api/actions/runs/39156343117): 219 tests (one upstream warning, 10.75s), Ruff/format/OpenAPI and synthetic Docker boot/auth/failed-import/atomic-replacement/persisted-restart smoke. Published AMD64/ARM64 image digest: `sha256:b60b064167f0d6acb9f83f046012cdb9fd884275f59014923cb3854468480a03`. Tower pulled the immutable SHA tag and recreated only `bord-food-api` through its actual productivity Compose project. Final container is running/healthy, zero restarts, no OOM; worker health passed. No Bòrd image, household database or unrelated container was changed.

Before activation, a protected consistent catalog/control backup, policy/environment/Compose backup and rollback image were retained. All seven backed-up SQLite files passed quick_check. The original USDA database still matches its pre-V1 SHA-256. No live restore was performed. The general Tower collector’s development-VM leg remained unreachable in the earlier preflight; its partial inventory was not adopted. Direct service/cache preflight and final live checks supplied this activation’s evidence.

The explicit ATP job succeeded for five partitions: **19 changed, 8,646 unchanged**. The final serving catalog has **469,046 USDA foods, 8,665 stores, 23 chains and one discovered map link**. Generation: `g_39e9f3f5bbe84bb9bf3f2aba0f8f1991`. Daily USDA/selected-ATP checks remain enabled; the four optional bulk sources remain disabled.

The crawl job `job_57e6bd7e976b424e81415c9ac4265e02` succeeded. Persistent host counters show **two requests total**, robots plus one approved branch HTML page, under the configured 20-second minimum spacing. The result links Altoona’s source-backed store `sto_d14e2d908f0d42a0b22eefa5774e13a9` to the explicitly labeled “Store Map (PDF)” link. Its URL ends `0093-PF-41-Store-Directory-both-sides.pdf`; the filename is not treated as a trusted map observation date. The PDF itself was not requested. Rights remain pending, `storage_permitted=false`, `display_permitted=false`, `layout_validated=false`, `assets={}`. No raw branch HTML or robots cache was persisted. The source is now paused, with global/adapter configuration gates also closed. No unattended crawl is running.

The corrected Open Prices parser completed all three downloaded exports in **19.12s**, emitting **42,822** US observations without publishing a price pack. The earlier 41,457 count used human country labels; prioritizing `osm_address_country_code` recovered additional source-backed US records. Final currencies: USD 42,811, EUR 3, INR 1, CAD 1, MXN 5, ILS 1. Exactly **14,136 / 26,689** distinct valid GTINs match the existing USDA catalog, covering **23,443 / 42,822** US observations. Only **1,426** observations are within 30 days and **10,308** within 90 days of 18 October; coverage is historical and sparse. Exact branch-ID matches remain zero. A 100 m proximity review produced 59 unreviewed candidates among the 368 observed US locations, including a Grocery Outlet location near an ALDI, demonstrating why distance alone cannot authorize identity merges; no candidate was auto-accepted.

OFF’s 1,124 complete prefix records parsed successfully, emitting 847 US products **only in validation**. Its 13 indexed delta intervals are internally contiguous, but no extraction boundary for this baseline is proven; no live watermark or delta cursor was established, and no OFF product pack was published.

FoodKeeper volume rehearsal imported **1,000 explicitly synthetic rows** into a separate catalog under the validation directory. Source JSON: **386,989 bytes**; first guidance pack: **2,465,792 bytes**; isolated catalog after a second publication: **5,670,272 bytes**. SQLite quick_check passed; unchanged replay returned no_change; changed input published a new object while the prior object’s hash remained unchanged. These are calibration measurements, not the live dataset’s size or guidance content. FSIS’s 403 remains the activation blocker.

Final stores/maps SQLite quick_check passed. `/live`, `/ready`, `/health`, `/v1/system/status`, protected legacy USDA search and native Woodman’s store search returned 200; missing-key native reads returned 401. The actual Bòrd container’s existing native configuration/key reached ready/status/store/legacy-search routes (all 200), and Bòrd’s own health returned 200. This verifies the deployed service connection; it does not extend the earlier companion UI acceptance claim or introduce companion changes.

Validation artifacts occupy approximately **73 MiB** on the actual cache-backed data volume after discarding the initial failed parser’s incomplete normalized output. Raw compressed exports and sanitized reports remain separate from serving packs. Final cache free space was **479,614,205,952 bytes (~446.7 GiB)**. Recovery/configuration paths and executed scripts/receipts are recorded in the private Tower operational runbook; credentials remain out of this repository. Current FoodKeeper dataset byte/count/storage size, SNAP import, a full OFF import and live baseline/delta equivalence remain unperformed.


## Subsequent full OFF download — 18 October

The owner subsequently authorized acquiring the full export. **13,179,356,850 compressed bytes** are now retained on Unraid with pinned version/ETag, expected-length verification and SHA-256 `1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37`. Transfer/hash receipt elapsed 475.56s. No OFF source activation, job, import, product publication, source cursor, extraction-boundary claim or full gzip/schema validation followed. Existing generation and health stayed unchanged. See [current plan status](PLAN-STATUS.md) for the acquisition boundary and current companion/later-milestone status.
