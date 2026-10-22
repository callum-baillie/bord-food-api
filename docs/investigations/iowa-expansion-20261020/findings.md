# Iowa coverage expansion — 20 October 2026 UTC

Published 373 additional source-backed Iowa store records on Tower/Unraid: **362 → 735**.
The directory now contains 9,309 store records across its existing geography. This count is
source-backed directory records, not a certified census of distinct currently operating stores.

| Evidence | Actual result |
|---|---:|
| Complete frozen-ID Iowa SNAP reference acquired | 2,882 retailer assertions |
| OSM Iowa candidates acquired | 666 assertions |
| Public bulk API requests | 35 |
| New primary records | 333 SNAP, 40 OSM |
| Other matched native assertions in first pass | 525 |
| Source assertions held for review | 501 |
| Source assertions excluded | 2,149 |
| Previous store payloads preserved byte-for-byte | 8,936 |
| Rehearsal replay additions | 0 |
| Added records with an observed website field | 12 |
| Additional paid calls / retailer requests | 0 / 0 |

All 99 counties occur in the SNAP reference; membership in SNAP and county reach do not prove
that all grocery stores have been found. SNAP includes pharmacies, convenience/dollar stores,
markets and other formats. Grocery/supermarket/superstore classification is filtered accordingly.
Provider assertions retain native IDs, raw source facts, clocks, attribution and licenses.

The native API now returns all three New Pioneer stores, both Iowa Bender's locations, and
Walmart #4256 at Ames. USDA/maps objects and all previous store payloads were preserved.
Store-pack storage grew from 43,212,800 to 44,830,720 bytes (about 1.54 MiB added).
Publication: `g_06c5c35bb5174eab98572bb872b95436`.

Reviews are assertions, not distinct missing stores: 236 lack an address/name, 105 are close
or otherwise ambiguous against existing identities, 92 have uncertain format, 11 may be
specialists, 9 have address conflicts, 14 are near new proposed identities, 33 conflict at
new addresses, and one conflicts on state. Several may already describe published stores.
No name/proximity-only merges, store closures or absence-based deletions were performed.

A matching pinned ATP spider's detailed stats now gate completeness. The investigated Walmart
export had timed out with 2,772 queued requests remaining. Normal finish, a drained queue,
raw-export count equality and no unreviewed large decline are required to assert completeness;
unverified archive members remain partial. Other sources retain their previous persisted
cache fingerprints. Existing fixture/compatibility behavior remains tested.

The current full-census gap is an independently verified active grocery-license roster plus
remaining record reconciliation. Iowa DIAL's [transition notice](https://dial.iowa.gov/licenses/food-establishments-hotels/food-resources/safher-transition-faq)
identifies 20 October 2026 as the SAFHER transition date. The public portal returned a JavaScript
shell to the documentation fetch; no browser provider was available for interactive inspection.
No complete active grocery denominator, portal account or external records request was obtained.
The new discovery workflow supports explicit dated incremental reruns; no periodic Iowa source
schedule or new retailer crawl was activated. Hours/maps/aisles and chain associations remain
limited to actual source evidence. Bòrd code was not changed.

Full artifacts, raw responses and review/crosswalk ledgers are retained on Unraid at
`/data/discovery/iowa-20261020-r2/`. The first failed acquisition is retained separately. Current
catalog/control/frontier/model-budget/history backups precede publication; the rehearsal ran
against independent copies with container networking disabled. The bounded JSON receipts here
contain counts and public IDs, no credentials. See [operator guide](../../IOWA-DISCOVERY.md).

Verification: **317 tests passed** (one upstream warning,28.57s); Ruff,126-file format check,generated OpenAPI,plan checksum validation and Tower repository validation passed. The final serving guard preserved historical USDA/OFF/FoodKeeper cache identities in both fixture and actual-image checks. See verification.json and final-guard-live.json.
