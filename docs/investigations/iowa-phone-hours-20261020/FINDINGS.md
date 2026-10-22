# Improve Iowa phone and hours coverage

**Recommendation: fix retained-evidence reconciliation first, then add a separate official-website discovery queue for independents.** More requests against the current fixed URL queue will leave most missing phones untouched. Add co-op/independent-network and local civic directories as discovery sources, and use official branch pages for current hours. Evaluate paid data only after measuring these gains.

Snapshot: October 20, 2026, 20:53:51 UTC, generation `g_55952b0eaf534c1e817cc5507ae1cf6b`. Grain is one canonical in-scope Iowa branch, excluding four redirected duplicates and two scope-excluded stores: **735 stores**. Query observed a stable manifest. The ongoing crawler may change later numbers.

## Where the missing fields are

| Field | Present | Missing | Interpretation |
| --- | ---: | ---: | --- |
| Phone | 498 (67.8%) | 237 | 15 present phones are already marked chain contacts, not direct branch numbers |
| Website | 474 (64.5%) | 261 | Presence includes conflicts and corporate/third-party URLs; it is not usable crawl coverage |
| Normalized weekly-hours records | 312 (42.4%) | 423 | 298 have all seven day entries; 14 are partial week representations |

Only 252 phones and ten schedules currently have corroborated provenance. Presence, direct contact, current source report and independent verification must be measured separately. There are no format-invalid selected phone/hours values in this snapshot; the problem is primarily acquisition/selection, not selected-value syntax.

The 336 independent/unmapped stores have **140 phones and 17 schedules**; they contribute **196/237 (82.7%)** missing phones and **319/423 (75.4%)** missing schedules. “Unmapped” does not prove independent ownership. Smaller chains without a canonical chain link can fall into this group.

## Highest-impact findings

1. **High severity, high confidence: the crawler cannot visit most missing-contact stores.** 210 of the 237 missing phones and 249 of the 423 missing schedules are in the current missing-URL queue. Of all 258 URL gaps, 244 have no retained website assertion, five have HTTP-only candidates, one social-only, and eight unsupported/shared/ambiguous candidates. A fixed list of websites cannot solve discovery gaps. Add store name + full address + city discovery and keep alternative candidates with binding/reasons.
2. **High severity, high confidence: some hours conflicts are representational.** Of 34 missing schedules with eligible conflicting evidence, 13 agree on every overlapping weekday and already have a full-week source. Fareway examples pair Monday–Saturday hours with a second schedule adding explicit Sunday closure. Prefer a reviewed fuller report where overlap agrees, without claiming the partial report verifies the missing day. Twenty-one have real overlapping-day disagreements and need source review. Do not make every omitted weekday closed or discard genuine conflicts.
3. **Medium severity, high confidence: retained sources still have a small recoverable tail.** After strict unique name/address matching, retained OSM has candidate phone values for 28 missing phones and schedules for 46 missing schedules; scope-filtered Overture has phone candidates for 27. The union is only 31 phone candidates, not 55. Most are already retained/held. Only six OSM phone, 22 OSM hours and two Overture phone matches lack any prior field assertion from that source. These are candidate review ceilings, not promised new fields; provider/department scope, duplicates and disagreement remain gates.
4. **Medium severity, high confidence: supported raw formats are unnecessarily narrow.** Among missing schedules, retained invalid evidence includes dayless time ranges and seven stores with seven-day schema hours written as `9am`/`8pm`. Add deterministic source-specific normalization, with negative cases for ambiguous labels. Dayless OSM syntax has source semantics; generic bare page text does not prove daily opening. Preserve raw input and distinguish partial schedules from complete weeks.
5. **High severity, high confidence: new providers need contact scope.** ALDI conflicting toll-free numbers and Walmart main/pharmacy/garden or money-transfer contacts should not compete as equivalent branch phones. Store all contacts with role/scope and count known chain contacts separately. Format validity does not prove a direct/reachable number; no phone calls were made.

## Sources ranked by likely value

| Priority | Source | Phone value | Hours value | Next action |
| --- | --- | --- | --- | --- |
| 1 | Retained OSM / Overture / ATP | Small immediate tail, already partly imported | OSM/ATP reconciliation and parser repair | Offline plans with exact crosswalks, per-day comparisons and before/after candidate counts |
| 2 | Official independent websites and network locators | Main contact + correct canonical URL | Strong current branch evidence | Discover through NCG, IGA and exact civic listings; support AWG and other repeated public site templates |
| 3 | Municipal/chamber/economic-development/tourism directories | Useful for rural/ethnic independents without sites | Variable; verify department vs whole store | Native member IDs, address-bound business panels, dated assertions; directory copies are not independent votes |
| 4 | Current Iowa DIAL/WIC public rosters | Potential identity/contact leads | Not a verified comprehensive hours source | Obtain current schema/export through public access; avoid owner personal contacts and old membership claims |
| 5 | Foursquare Open Source | Phone/website/social leads | No documented free OS hours column | Measure incremental Iowa yield beyond Foursquare already in Overture before acquiring more |
| 6 | Licensed Foursquare Premium / HERE / TomTom | Potentially useful | Documented hours functionality | Only evaluate after persistence/redistribution rights and budget; small independent-heavy sample |

The Overture schema has phones/websites/socials but no weekly-hours field. Foursquare OS also lacks documented weekly hours; Premium explicitly lists hours. Google Places has relevant fields, but its storage/caching policy is a poor fit for an assumed permanent catalog backfill. OSM-derived resellers may repeat the same source; do not buy duplicate evidence as corroboration. See [source registry](sources.json) for primary documentation and acquisition status.

## Confirmed research examples

- **Oneota, Decorah:** currently missing phone/hours/website. NCG's directory points to its official site; the exact 312 West Water Street page posts **563-382-4666 and daily 09:00–20:00**. This is a strong new crawl candidate, not an imported or independently verified fact. [NCG](https://www.ncg.coop/find-co-op), [official site](https://oneotacoop.com/).
- **Hometown Market, Earlham:** official `/locations/` has exact premises, phone and Monday–Saturday/Sunday schedules. The ongoing crawl has now populated these fields. Add a reusable public AWG-template profile and observed same-site contact/locations links, rather than expecting every independent homepage to contain a structured store node. [Official location page](https://earlhammarket.com/locations/).
- **Zamora, Marshalltown:** Travel Iowa has an exact address and phone lead, but explicitly warns the listing has not been updated within 12 months. Keep as a stale lead and find a current business source. Restaurant/ordering hours may differ from grocery hours. [Travel Iowa](https://www.traveliowa.com/places/zamora-fresh-market/7208/).
- **Fiesta Foods, Hartley:** the municipal listing supplies a phone and store website. This demonstrates a useful rural directory pattern, not measured statewide coverage. [City listing](https://www.hartleyiowa.com/business/grocery-convenience-store/fiesta-foods).

## Repeatable execution order

1. **Offline repairs:** evaluate the 13 overlap-compatible schedules; normalize labelled am/pm schema input; rejoin retained assertions after address cleanup; classify contact scope. Keep review-bound decisions and raw conflicts. No new model/source requests needed for this stage.
2. **Discovery pilot:** 20 independents, split between missing URL, fetch/redirect failures, partial schedules and provider conflicts. Resolve official websites through network/civic sources. Follow robots and existing shared request counters. Review known HTTP→HTTPS/www migrations and observed same-site `/locations`, `/contact` and `/about` links with fresh target/robots checks; no blanket redirect relaxation.
3. **Platform profiles:** AWG/public location cards, common CMS contact panels and NCG/IGA member discovery. Use source-bound address aliases (West/W, Avenue/Ave, legal name variants) without widening to nearby stores or matching by name alone. Allow one branch-specific footer/contact panel only when site ownership/single-premise evidence supports it; keep generic corporate/footer contacts held.
4. **Measure incremental yield:** new usable direct phones, complete seven-day schedules, newly found official URLs, false branch/department matches, conflict reductions and requests per accepted field. A published crawl outcome alone is not a phone/hours success. Break out independent/unmapped stores and chain contacts. Preserve cohort IDs across runs.
5. **Statewide missing-field pass:** activate the proven profiles against remaining Iowa gaps after the pilot. Retain durable per-target failures/holds and refresh dates; avoid repeatedly hitting blocked hosts. Do not reset daily counters. Do not alter the currently running frozen config in place.
6. **Human/store corrections for the long tail:** a reviewable correction path with store ID, proof URL/date, scope and expiry will cover stores without machine-readable sites. No outreach was sent. Consider dated sign-image review only when lawful source acquisition and separate image/model budget are explicit.

Use OpenAI only after acquiring new source evidence, to extract or classify ambiguous snippets in at most nine real inference requests per authorized pass. The previous 524 evidence-less stores cannot be completed by repeating an evidence-only prompt. No further paid job was submitted here.

## Policy and API changes to make these gains dependable

Return per-field source/report/verification status, checked/observed dates, direct-vs-chain phone scope, weekly day coverage and partial/unknown days; expose raw hours and conflicts to the operator. Add field-specific retry reasons and expired schedules. Suggested pilot freshness policy: recurring hours due in 30 days, phones in 90 days, with sooner refresh on detected changes; holidays have explicit date ranges. These are proposed tuning values, not a deployed schedule or new verification dates. Re-fetching an old provider row does not prove a recently surveyed phone/schedule.

Do not copy a chain-wide timetable into all branches, turn licensing dates into closure, manufacture holidays, treat pharmacy/restaurant/pickup hours as store hours, or count mirrored sources twice. For ALDI-like cases track confirmed “no public branch phone” separately from unknown; do not invent availability or fill every row with customer service.

## Boundaries and reproducibility

This was read-only production inspection plus official documentation/web research and offline analysis of already retained files. No serving publication, crawler config edit/new run, new bulk-source acquisition, paid API/model call, contact outreach, deployment or Git push. The authorized existing Iowa worker continued independently.

The diagnostic initially read raw pack rows (739 after exclusions); manifest redirects were then applied, yielding the correct 735 canonical denominator. All reported counts use that corrected snapshot. Raw source candidate ceilings overlap, include provisional/possibly stale reports, and were not published. No claim of 100% Iowa census or future coverage percentage is supported.

Artifacts: [analysis](analysis.json), [inspectable notebook](analysis.ipynb), [code](analyze.py), [portable report](report.html), [sources](sources.json). Snapshot and inputs are public-source operator evidence, not household data. Supporting source file hashes are in input-receipt.json. Notebook/script derive the same summary from the saved snapshot and retained source files; do not treat later crawler snapshots as the same cohort/time.

## Validation record

Offline analysis and both notebook code cells executed; saved analysis equality passed. Full API suite: 388 passed, one upstream warning, 73.21s using a dedicated temporary fixture directory on /home. An earlier /tmp run had 384 pass/four import-budget failures because available tmpfs space was below the unchanged 5GiB reserve; no code change was needed. Ruff/format/diff checks passed. Portable report canonical validation and exact payload/structural checks passed; its full browser verifier detected a shared toolbar horizontal overflow with classic scrollbars, reproduced separately. That presentation limitation remains recorded in checks.json; the Markdown findings and underlying calculations are unaffected. No plugin source was modified.
