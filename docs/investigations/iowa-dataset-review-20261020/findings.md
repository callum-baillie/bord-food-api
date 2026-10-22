# Iowa store data review

## Executive Summary

- **Discovery is ahead of crawl enrichment.** The directory has 735 Iowa records. Across the Iowa pilot and statewide run, 96 unique stores completed retailer-page checks; the statewide run retained 95 rich evidence files.
- **SNAP and OSM substantially broaden the reference base.** The downloaded Iowa subsets contain 2,882 SNAP retailer assertions and 666 OSM place candidates. Their categories differ and their records overlap.
- **The crawler has not yet produced accepted aisle or map data.** Only 41 saved pages have one structured branch match. All saved evidence remains pending acceptance, and no interior map or item-to-aisle placement was found.
- **Use existing evidence before increasing crawl volume.** Linked downloads contain candidates for missing coordinates, phones, hours and websites. Address normalization and selection of the primary grocery business are immediate verification gaps.

## Separate discovery, page checks and usable facts

A source assertion is one provider record. A published directory record is a canonical API record, not a certified count of distinct operating stores. A completed page check can publish a “not found” map result. A retained evidence file contains source excerpts and structured candidates; it does not imply that its fields have been accepted into the API.

The comparison is an October 20, 2026 snapshot. Completeness percentages use the 735 published Iowa directory records, not all groceries actually operating in Iowa. The original statewide campaign covered 362 directory records and 319 URLs, before the subsequent directory expansion.

## The reference sources are much larger than the completed crawl

**SNAP lists many retailers outside our grocery scope.** Its broad Grocery Store, Supermarket and Super Store categories contain 705 rows before pharmacy and other format checks. Some grocers also occur in Other, so 705 is not an exact grocery census. OSM has 508 supermarket-tagged records and five grocery-tagged records, plus 153 candidates in department-store, wholesale and general-shop categories.

The exact counts below are different populations, not parts of one total. SNAP and OSM native assertions have been linked conservatively to 621 and 276 published directory records; 211 records have links to both sources. Among the 96 completed Iowa page checks, 69 have a confirmed SNAP link and 46 have a confirmed OSM link. An unresolved link does not prove the store is absent from the provider.

### Source and crawl counts

| Population | Records | Scope |
| --- | --- | --- |
| SNAP retailers | 2882 | All Iowa retailer types |
| SNAP broad grocery types | 705 | Before format exclusions |
| OSM places | 666 | Five queried shop categories |
| OSM grocery tags | 513 | Supermarket or grocery tags |
| Published directory | 735 | Combined source-backed records |
| Completed Iowa page checks | 96 | Unique stores across two runs |
| Saved statewide page evidence | 95 | Retained rich evidence files |

## Most current directory records have no saved crawler evidence

**The statewide run saved evidence for 95 stores, or 12.9% of the current directory.** An earlier pilot contributes one additional completed store check, making 96 unique completed checks overall, or 13.1% of the directory.

The chart splits the 319 statewide targets into mutually exclusive outcomes. Host holds include inherited blocks and failed requests; they do not mean all 133 stores were individually fetched. The 43 original records without usable URLs were outside that target list. The 373 subsequently added directory records were also outside this campaign.

### Statewide target outcomes

| Outcome | Records | Share |
| --- | --- | --- |
| Saved | 95 | 29.8% |
| Post-fetch hold | 2 | 0.6% |
| Pre-fetch hold | 89 | 27.9% |
| Host hold | 133 | 41.7% |

**There were 97 statewide post-fetch Jev reviews:** the 95 saved page checks and two pages held after review. The earlier pilot had nine post-fetch reviews; most repeated stores from the statewide run. Across both Iowa runs, the records identify 98 unique stores reaching page review. Those two held pages did not produce retained rich evidence files. Earlier request-attempt flags are incomplete, so they cannot establish a precise historical HTTP request total.

## The crawler saved useful candidates, with limited app-ready enrichment

**Every saved statewide page has a source URL, retrieval time, content hash and visible-text excerpt.** Of 95 files, 41 have exactly one matching structured branch, ten have two matching business candidates, and 44 have no matching structured candidate. The ten ambiguous Walmart pages all contain Grocery and Photo Center descriptions. Selection of the grocery business needs to use business type and page hierarchy as well as address.

The table counts fields on the 41 singly matched pages. All remain review-required. The nine department records describe services or departments; they are not aisle numbers or an interior route graph. No interior map links, geographic map links or item-placement candidates were retained by this campaign.

### Structured crawler fields

| Field | Pages | Saved pages |
| --- | --- | --- |
| Address | 41 | 95 |
| Phone | 41 | 95 |
| Hours | 9 | 95 |
| Coordinates | 9 | 95 |
| Departments | 9 | 95 |

**No saved evidence bundle has been promoted to accepted enrichment.** All 96 Iowa map-pack records are “not found” results, not 96 maps. Separately, earlier Woodman’s work outside Iowa retained map-link candidates; it does not establish Iowa map coverage.

Text excerpts are bounded: 21 of the 95 reach the 4,500-character limit. The retained evidence is not a complete archive of the page. Address-matching failures and unsupported page structures can therefore look like missing fields even when a human can see them on the website.

## Basic location coverage is strong; contact and opening details are uneven

**Every published record has a name and usable postal address.** Only 610 have separate street/city fields and coordinates: 125 existing Hy-Vee records retain full postal-address strings without structured coordinates.

The chart measures populated API fields across all 735 records. A populated value may come from bulk data and is not necessarily recently verified. All 357 populated hours fields and all 287 populated phone fields come from the older ATP-backed records; none of the 373 newly added records has those normalized fields yet. Opening status and timezone remain unknown throughout this snapshot.

### Published field availability

| Field | Records | Share |
| --- | --- | --- |
| Address | 735 | 100.0% |
| Coordinates | 610 | 83.0% |
| Website | 331 | 45.0% |
| Phone | 287 | 39.0% |
| Hours | 357 | 48.6% |
| Timezone | 0 | 0.0% |
| Open/closed | 0 | 0.0% |

## Linked source data can fill some gaps without new retailer requests

**There are concrete enrichment leads in already downloaded, identity-linked assertions.** Counts below are distinct directory records per missing field; a store may appear in several rows, so do not add them. These are candidates for field review, not pre-approved replacements. Preserve conflicting values and source freshness rather than silently choosing one.

The wider OSM download contains 349 phone tags, 275 hours tags, 245 website tags and 16 wheelchair tags. Many are already-known values, unresolved identities or candidates outside the final grocery scope; those raw tag counts are not counts of additional verified app fields.

### Missing-field candidates

| Field | Records |
| --- | --- |
| Coordinates (SNAP) | 94 |
| Phone (OSM) | 89 |
| Hours (OSM) | 27 |
| Website (OSM) | 44 |

## Prioritize verification and promotion before another broad crawl

1. **Join reference evidence into each crawler target.** Supply canonical IDs, source-native IDs, structured addresses, coordinates, matching websites and conflicts to deterministic checks and Jev. Review the 501 unresolved discovery assertions without treating them as 501 distinct missing shops.
2. **Improve branch extraction.** Normalize address abbreviations and full postal strings, retain JSON-LD business types and parent/department context, and distinguish the main grocer from co-located Photo Center or pharmacy entries. Support bounded visible-HTML evidence when JSON-LD is absent.
3. **Review the existing missing-field candidates.** Promote corroborated coordinates, contact details and hours into immutable directory updates, with field-level source and verification dates. Preserve all canonical IDs and household overrides.
4. **Make opening-hours data usable.** Store an explicit timezone, holiday exceptions and freshness before the app presents an “open now” claim. Unknown must remain distinct from closed.
5. **Collect the shopping details Bòrd needs.** Prioritize branch-specific pickup/delivery links, department names, entrance/directions and accessibility evidence. For navigation, retain reviewed category-to-aisle mappings, map version, branch association and display rights.
6. **Keep product inventory outside this crawl.** Prices, availability and full assortment are intentionally absent. If later required, use appropriate product/price providers and Bòrd’s private purchase history, with date and branch identity; preserve the current no-inventory crawl scope.

## Further questions that determine the next validation pass

- Can a complete current Iowa grocery-license roster be reconciled with SNAP, OSM and the directory? Without that denominator, 100% statewide coverage remains unverified.
- Which unresolved assertions describe existing stores, stale businesses or out-of-scope formats?
- Which saved page descriptions can be safely promoted after improved extraction, without fetching again?
- Which branches matter most for household shopping, so limited requests and paid review can focus on missing useful fields?

## Caveats and assumptions

Source counts refer to downloaded Iowa subsets, not national exports. Source record presence, SNAP enrollment, OSM tagging, a recent snapshot clock and current store operation are distinct facts. The SNAP reference’s data clock is October 7, 2026; the statewide page evidence was retrieved October 18–19, Central time. OSM snapshot time does not establish when every individual field was checked.

Some identity matching is intentionally conservative. Published canonical IDs and native crosswalks are unique, but physical-location completeness and all stale/duplicate business assertions have not been independently certified. Field presence is not a freshness or accuracy score. This review performed no new crawler requests, paid calls, serving data changes or companion app changes.
