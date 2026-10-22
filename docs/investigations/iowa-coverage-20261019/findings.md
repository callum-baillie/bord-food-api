# Why Iowa locations are missing

## Executive Summary

- **The directory inherits gaps from its bulk source.** Walmart's upstream collection stopped after eight hours with requests still queued. Our importer retained every eligible Iowa record supplied by the 14 contributing source scopes.
- **Regional chains need another discovery path.** New Pioneer and Bender’s have official Iowa locations but no records in the current directory; their absence is separate from website crawl failures.
- **Website failures reduce enrichment, not store-record retention.** All 362 store records remain present. The crawl finished with 95 completed page checks, 91 review holds, 133 host holds and 43 records without website URLs.
- **The statewide missing total remains unknown.** Six named missing locations can be demonstrated in this investigation; the earlier estimate of 50–90 missing locations remains an unverified planning scenario.

## Count directory coverage separately from website completion

A directory record is a source-backed store assertion. A page check is a request to enrich an existing record with store details, hours, aisle or map evidence. The denominator below is **362 stored Iowa records**, not all stores operating in Iowa. The bulk snapshot began October 10, 2026; this review reads the live directory and finished campaign on October 19, 2026, Central time.

The four outcomes sum to the stored directory. A completed page check does not imply a usable map, accepted aisle data or a unique physical location.

| Existing record outcome | Records |
|---|---:|
| Host hold | 133 |
| Page checked | 95 |
| Review hold | 91 |
| Missing URL | 43 |

## Walmart’s upstream collection ended before its queue was empty

**The missing Walmart rows are already absent before our importer runs.** The pinned export supplies 28 Iowa Walmart records and all 28 are imported. It contains 1,484 Walmart features overall. Its detailed upstream statistics say `closespider_timeout`: the run ended after 28,800.74 seconds, with 4,262 requests enqueued and 1,490 dequeued. The difference is **2,772 unprocessed requests**, not a count of missing stores.

The aggregate results file reports zero errors for this spider. Successful HTTP responses and valid JSON therefore do not establish complete source coverage. The ingestion path currently does not inspect this detailed finish reason. It marks the regional import partial, which protects against interpreting omissions as closures, but it does not recover missing locations.

## Official directories expose concrete missing locations

**Ames Walmart #4256 at 534 South Duff Avenue is a confirmed example.** Walmart’s official Ames directory lists it alongside #749 at 3105 Grand Avenue; the pinned export contains only #749. [Official Ames directory](https://www.walmart.com/store-directory/ia/ames).

[New Pioneer](https://newpi.coop/) lists three retail stores: Cedar Rapids, Coralville and Iowa City. [Bender’s](https://bendersfoods.com/) lists two Iowa stores: Bellevue and Guttenberg. None of those five appears in the current 14-banner directory. The archive name/domain probe and source-member inventory are retained with the supporting evidence; those probes cannot detect every possible alias.

These six examples establish real omissions, but do not validate an exact statewide denominator. Discovering them does not automatically add them to production or authorize broader crawling.

## The importer retained all 362 eligible source identities

**No eligible record was lost between the contributing source scopes and the published Iowa directory.** Replaying the existing country, state, format, banner and native-ID checks yields exactly the same 362 source identities, with no duplicate source keys. Across these 14 scopes, 33 additional Iowa rows are deliberately excluded: 24 pharmacy rows and nine Sam’s Club fuel-site rows. Hy-Vee accounts for 23 of the pharmacy exclusions; its 125 accepted rows were not reduced by crawl holds.

The table compares raw Iowa source features with eligible and published records. It proves transfer fidelity for the contributing scopes, not statewide source completeness. Rows outside those scopes and unrecognized aliases remain outside this targeted replay.

| Source scope | Raw Iowa | Eligible | Published | Missing URL |
|---|---:|---:|---:|---:|
| albertsons | 2 | 1 | 1 | 0 |
| aldi_sud_us | 41 | 41 | 41 | 41 |
| costco_ca_gb_us | 4 | 4 | 4 | 0 |
| family_fare_us | 1 | 1 | 1 | 0 |
| fareway_us | 119 | 119 | 119 | 0 |
| fresh_thyme_us | 2 | 2 | 2 | 2 |
| hy_vee_us | 148 | 125 | 125 | 0 |
| natural_grocers_us | 6 | 6 | 6 | 0 |
| sams_club | 18 | 9 | 9 | 0 |
| save_a_lot_us | 1 | 1 | 1 | 0 |
| target_us | 22 | 22 | 22 | 0 |
| trader_joes_us | 2 | 2 | 2 | 0 |
| walmart_us | 28 | 28 | 28 | 0 |
| whole_foods | 1 | 1 | 1 | 0 |

## Host holds and Jev uncertainty explain the unfinished enrichment

**All 91 review holds are Hy-Vee targets.** Jev answered “fetch” for 89 but with confidence below the 0.8 threshold, so no page request was made for those targets. Two more were withheld after page review because branch confidence was below 0.8. The exact reason for low confidence is not established by the saved choice/confidence fields; it requires review of the branch context rather than assuming a model failure.

**Fareway accounts for 87 host-held targets.** One branch request returned HTTP 500 and the controller conservatively held the rest of that hostname. Other host holds cover Target (22), Walmart (18), Costco (four) and Trader Joe’s (two). Those locations remain in the directory. Transient server failures should be tracked separately from robots or access denials when designing a bounded retry policy.

**The 43 missing URLs are source sparsity:** 41 ALDI records and two Fresh Thyme records have no website field in the supplied bulk rows. The enrichment worker requires an approved branch URL and does not invent one.

## Repair discovery before expanding the enrichment crawl

1. **Add upstream completeness checks.** Read per-spider finish reason and queue statistics; compare counts with prior successful releases and official totals. Retain partial records and provenance, while preventing partial runs from asserting absence or closure.
2. **Add source-backed discovery for uncovered chains.** Reconcile official branch directories or suitable public bulk sources for New Pioneer, Bender’s and other regional groups. Keep native identities, addresses and source dates; check duplicates before publication.
3. **Resolve the 43 missing branch URLs.** Bind observed official URLs to exact existing stores and retain evidence; do not guess URL slugs or use generic homepages as branch evidence.
4. **Review enrichment holds by cause.** Improve branch context for Jev review; design bounded cooldown/retry for transient HTTP 5xx separately from access blocks. Preserve robots, pacing, history and the existing paid-call cap.
5. **Report two coverage measures.** Track discovered locations against a reviewed external roster separately from completed website checks. A higher daily request allowance cannot repair missing discovery inputs.

## The remaining count requires a reconciled roster

How many qualifying chains and locations exist under the intended scope? Which specialist meat markets, pharmacies, convenience stores and warehouse clubs should count? Are other failed source scopes hiding Iowa grocers under different names? These questions require a state-and-format reference roster; the 350/450 planning estimates cannot answer them alone.

## Caveats and boundaries

This is a source and pipeline diagnosis, not a complete Iowa census. Source identities are not proof of unique physical locations. The replay covers all Iowa-contributing scopes; the separate archive string search is an exact name/domain probe, not semantic entity resolution. The national scan previously reported 375 unusable source scopes, but that figure is not an Iowa missing-store count. No trend series was fabricated from this one snapshot.

The investigation performed read-only production queries, offline archive checks and bounded public-document/statistics lookups. It did not restart a crawler, download a new bulk export, call Jev/OpenAI, import stores, change production configuration or deploy software.
