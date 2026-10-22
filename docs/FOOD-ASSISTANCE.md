# Food assistance datasets and post-supermarket enrichment

Food assistance is a separate reference directory, not the user's household pantry and not
an extension of the supermarket count. Keep Python/FastAPI, SQLite FTS5/RTree and immutable
pack publication. No PostgreSQL, PostGIS, browser or paid model is required for ingestion.

## Records and API

- **Sites** describe physical premises and operator contacts, access, coordinates and facility
  hours. A food bank warehouse is not necessarily a public distribution point.
- **Services** describe pantry groceries, prepared meals, community fridges, mobile pantries or
  an unspecified food-assistance service, with eligibility, application, documentation,
  service area, languages, appointments and distribution schedules when explicitly supplied.
- **Events** describe a dated distribution with explicit start/end offset timestamps and
  cancellation status. Recurring prose is retained as a schedule, never expanded into invented
  future events. An organization's office schedule is never copied into distribution hours.

Authenticated read routes use the existing envelope, catalog generation, bounded keyset
cursors and source-rights filtering:

```
GET /v1/food-assistance/sites?dataset=osm&state=IA
GET /v1/food-assistance/sites?dataset=osm&lat=41.6&lon=-93.6&radius_km=10
GET /v1/food-assistance/sites?dataset=directory&postal_code=50316&query=pantry
GET /v1/food-assistance/services?dataset=osm&site_id=...&service_type=meal
GET /v1/food-assistance/events?dataset=directory&state=IA
GET /v1/food-assistance/{sites|services|events}/{id}?dataset=osm
GET /v1/capabilities
GET /v1/system/status
```

`dataset=directory` selects permissive/explicitly authorized sources in the `assistance` pack;
`dataset=osm` selects the **separate** ODbL `assistance_osm` pack. There is deliberately no
merged default that relabels OSM fields under CC BY. An unpublished pack returns 503
`CATALOG_NOT_READY`, distinguished from a successful empty search. Do not silently fall back
between licenses. Show attribution and confirmation warnings in downstream clients.

Search supports state, ZIP, service type, site ID, geographic radius and bounded text search.
Past/cancelled events and reported permanently closed sites are hidden by default but can be
inspected with `include_past_events=true` / `include_closed=true`. Events are source reports,
not guarantees of availability. `public_access=unknown` is not an assertion of walk-in access.

## Automatic sources and update semantics

| Source | Implementation | Refresh | Current activation |
|---|---|---|---|
| OpenStreetMap | Bounded state Overpass snapshots; native node/way/relation IDs, tag provenance, source clock, separate ODbL pack | Weekly | Explicit 13-state post-supermarket profile |
| Feed America (`feedam.org`, distinct from Feeding America) | State/type-filtered paginated bulk connector; validates counts, scope, duplicate IDs and page completion | Daily when enabled | Rights review hold; no automatic production import |
| Municipal sources | Reusable ArcGIS WGS84 and Socrata connectors with reviewed per-dataset field maps, license and attribution | Daily when enabled | No jurisdiction profiles activated |
| Authorized HSDS exports | Joined location/service/service-at-location, contact and schedule export bundles | Daily when enabled | No 211 credentials/entitlements configured |

`config/food-assistance-policy.json` and `config/food-assistance-campaign.json` select Iowa
and WY, AK, VT, ND, DE, SD, MT, RI, NH, HI, ID, WV. Other states are not activated. All new
sources remain optional/off in generic installations; the explicit campaign profile enables
OSM. The source adapters also work in the standard scheduler when explicitly configured.

Downloads use the existing exact-origin/DNS-pinned transport, byte/request/time/storage
budgets, conditional validators and verified cached files. Scope/parser/profile changes
invalidate transformation cursors. Candidates are validated before publishing their partition.
Overpass errors/remarks and missing clocks, wrong states, ignored filters, repeated IDs,
non-WGS84 ArcGIS points, exhausted pagination and unreviewed rights quarantine the candidate.
Content-hash comparison publishes changed records only. Empty/partial feeds are **additive**;
absence does not close or delete a pantry. A failed candidate retains the last good generation.
A changed premises identity is held with the candidate and prior identity retained; contacts
from the new premises are not attached to the old address. Source field alternatives and
operator conflicts remain inspectable. Duplicate suggestions never merge different programs
at one church, or copy OSM fields into permissive records.

OSM's `social_facility=food_bank` does not reliably distinguish a warehouse from a public
pantry. It therefore starts as `food_assistance_unspecified`, retaining original tags.
`social_facility=soup_kitchen` maps to meals. Generic food-sharing shelves are not automatically
called refrigerated community fridges. No nutritional/product catalog or current pantry
stock is derived from these records.

## Enrichment follows supermarket crawling

```
python scripts/run-food-assistance.py config/food-assistance-campaign.json --data-dir /data
python scripts/run-food-assistance.py config/food-assistance-campaign.json --data-dir /data --run --resume
```

The first command stages/inspects only, with zero source or paid requests. The second is the
explicit long-running operator activation. The worker waits for the **whole** named supermarket
controller to become terminal, with no active child and all expected chunks finished or
explicitly held. A premature per-state summary, paused/stopped campaign or budget pause cannot
release the gate. This wrapper can reference future state campaign IDs in a new versioned
profile; it does not modify the immutable current supermarket worker.

Once released, each pass processes only due assistance jobs and up to **25 operator pages**.
Passes are six hours apart, bulk updates follow their own daily/weekly source intervals, and
accepted operator pages are not revisited for seven days. This is a bounded initial enrichment
phase rather than a claim that every pantry will be reached in one pass.

Only source-supplied HTTPS operator URLs with a structured premises/name are eligible. Shared
multi-site URLs, missing contacts and prior holds remain review items. Each branch uses the
same persistent frontier, robots cache/backoff and worker lock as grocery crawls, **500 daily
attempts per host**, **45 seconds plus random 0–45 seconds** between requests or stricter robots
rules. A page budget includes robots requests. Redirects fail closed for review. No endpoint
guessing, login, IP rotation, images, PDF downloads, bulk inventories or prices.

Structured page facts require the exact name, street, city and state. A reviewed operator host
may confirm facility contacts/hours or an explicit closure report, with field-specific dates.
Unreviewed domains may fill a missing field as source-reported; conflicting existing values are
retained for review. Confirmed facility hours expire after seven days, contacts/status after
30 days. These never become verified service distribution times. Raw feed claims of
verification are labeled `source_claimed_verified_at`; retrieval time is never relabeled as
independent verification. The API retains unresolved conflicts and `needs_confirmation`.

Selective Jev review is enabled in the supplied campaign for ambiguous pages and a deterministic
sample. It uses the existing shared ledger, **cumulative $15 cap**, one $0.01 conservative
reservation per selected page, text-only questions, no automatic paid retries. Model categories
are `review_only`; they cannot override an identity failure, invent eligibility/schedules, grant
rights or establish inventory. Reservations and answered requests are reported separately from
actual billing, which is not measured. The existing key is read from a protected mounted file,
never embedded in source/config/output. No OpenAI batch is submitted by this feature.

## Persistence and stopping

Use the same `/data` bind mount as the food API. Source downloads, the immutable assistance packs,
control checkpoints, per-target history and Jev ledger survive replacement/restart. The worker
uses its frozen configuration fingerprint on resume; policy changes require a new reviewed
campaign/profile. No serving catalog is edited in place.

Create `/data/crawl-campaigns/food-assistance-after-small-states-20261021/STOP` to pause the new
phase, including cooperative in-flight cancellation. It remains idle while that marker exists.
Removing it allows the next scheduled pass. Docker `stop` stops the worker. Grocery workers
are not stopped or resumed by either assistance command.

Each run writes targets/gaps and duplicate review candidates plus child target status/history.
No phone call, email, partnership application or directory signup is sent automatically.

## Source audit and access boundaries

See [dated evidence](investigations/food-assistance-20261021/RESULTS.md).

- [OSM licensing](https://www.openstreetmap.org/copyright) requires attribution and ODbL handling.
  The public Overpass endpoint is used serially for small state-scoped responses; large national
  expansion should reuse a retained Geofabrik extract/local filtering rather than poll every
  state aggressively. Geofabrik PBF replication is not implemented by this addition.
- [Feed America HSDS](https://feedam.org/hsds) and its descriptor claim CC BY 4.0, but the live
  types response has a null data license and says individual records come from upstream sources.
  Two Iowa sample bank records had January 2025 verification claims and one address conflicted
  with the [Iowa HHS directory](https://hhs.iowa.gov/assistance-programs/food-assistance/emergency-food).
  Explicit `rights_reviewed=true` and an approved upstream-source allowlist are required before
  activating this connector. No provider's directory-wide total is treated as a pantry count.
- [211](https://apiportal.211.org/) supports authorized export. The generic HSDS bundle importer
  does not establish 211 production access; credentials and contributor rights are still needed.
- Philadelphia, Seattle and Baltimore County machine-readable sources were identified. Their
  dataset licenses, field maps, geographical scope and source clocks require a reviewed profile;
  they are not treated as national coverage or downloaded automatically in this 13-state phase.
- Feeding America, Plentiful, AmpleHarvest and WhyHunger remain partnership/discovery references;
  no unverified bulk endpoint or unrestricted license is assumed.
- USDA SNAP remains a **retailer authorization** dataset, linked to groceries, not a pantry list.
  USDA TEFAP commodity/product information describes program-level foods, not any location's
  present stock. Direct FNS documentation requests returned 403 during this audit; no guessed
  commodity download, ingredient mapping or inventory claim was introduced.
- Food Environment/Access Atlas and Map the Meal Gap are aggregate analytics sources. New food
  insecurity metrics, restricted-data licensing and recipe/household functionality are deferred.

Bòrd assistance UI, mobile calendar/reminders, household pantry recognition and corrections
moderation are companion work, not changes made to the household app by this API feature.
