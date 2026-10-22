# Store fields and retained evidence

The directory now supports branch phone/email/website, local weekly hours, IANA timezone,
dated holiday exceptions, operating status, pickup/delivery links, departments, accessibility,
entrances and reviewed aisle/category mappings. These are optional fields: missing values are
not silently filled from a corporate footer, a model answer or a nearby business.

`field_evidence` retains raw and normalized assertions, native IDs, source URL/path/revision,
provider lineage, acquisition and observation dates, branch binding and validation results.
`field_provenance` records status, supporting assertion IDs, verification time/expiry and method.
`field_conflicts` preserves disagreements. Credentials in evidence URLs/objects are redacted.
An observation/fetch date is not proof the business fact changed on that date.

A current, valid, exact-branch source report may fill a gap as `source_reported`, with null
verification dates. Independent verification needs agreement across two provenance families. ATP and the retailer page do not count as independent when they use
the same retailer host; a discovery wrapper is attributed to its original provider; Overture
records inherited from Foursquare/OSM do not create another vote. Jev/OpenAI confidence is never
field verification. Later directory updates retain verified values and surface disagreements.

Only explicit, corroborated operating-status assertions or a recorded operator review establish
permanent closure. Missing from a source, absent SNAP authorization, failed fetches, expired
hours and OSM `disused:shop` do not establish it. `permanently_closed` is null when unknown.
`closure_reported_at` is a reporting/observation date, never an invented actual closure date.
Hours describe local schedules, not live open/closed status. Dated holiday closures do not
mean permanent closure. Unsupported OSM hours expressions remain raw for review.

Timezones are derived only for explicitly US stores in unambiguous single-zone states;
all Iowa stores can use America/Chicago. Derived is distinct from verified. Split-zone states
and unknown countries remain unresolved; no UTC offset abbreviation is substituted for IANA.
Holiday exceptions are accepted only when dated source evidence exists; no calendar is guessed.
Entrances and aisle/category mappings require explicit operator review, even if sources agree.
They do not establish routable indoor geometry, media rights or current inventory.

## Offline operation

Use an installed package or `PYTHONPATH=.` for the source checkout:

```sh
PYTHONPATH=. python scripts/enrich-retained-stores.py --data-dir /data --run-dir /data/operator-imports/fields-review
# Review plan.json and records.jsonl, then publish from retained evidence:
PYTHONPATH=. python scripts/enrich-retained-stores.py --data-dir /data --run-dir /data/operator-imports/fields-publication --publish
```

`--state IA` narrows the scope; absent state means all published stores. The underlying Iowa
roster reader keeps its Iowa default for existing callers. No HTTP/model request is made.
Publication uses a fenced replacement stores database and atomic generation switch. Existing
store/chain identities, source records and unrelated packs remain intact. Do not run two heavy
workers together; the normal worker lock deliberately fails fast when busy.

Optional `--places overture_places=FILE.jsonl` / `--places foursquare_os=FILE.jsonl` accept retained
extracts. Each row must include documented native IDs, structured address, acquisition clock
`_retrieved_at` and preferably `_source_url`; original provider observation clocks are retained.
Only unique exact-address/name-compatible branch matches are considered. Provider license and
attribution must be reviewed before acquiring or publishing a real extract. The later [Iowa field campaign](IOWA-FIELD-CRAWL.md) acquired a pinned public Iowa Overture
subset. No authenticated Foursquare connector was activated.

`--reviews FILE.json` accepts an array of `{assertion_id, decision: "accept", reviewer, reason,
reviewed_at}`. Reviews bind a retained, valid assertion and remain auditable on replay. Source
rights restrictions remove dependent evidence and fall back to permitted baseline values.

The Iowa statewide and generic state campaign runners extract JSON-LD and bounded Schema.org
microdata, retain page-level mailto/tel contacts separately, and reconcile fields after an
approved branch-page publication. This adds no fetch, assets or model calls. Ambiguous branch
roots remain held. Existing robots checks, delays, host budgets, failure history, rights and
Jev spending gates continue to apply. No full product inventory is captured. Other state
campaigns remain staged until separately activated. The currently deployed historical Iowa
worker scripts are not silently replaced or restarted by the API module activation.

## Next evidence acquisition priorities

1. Resolve the 61 current field conflicts and ambiguous multi-store page evidence; retain both sides.
2. Recrawl approved exact branch pages using the existing robots-aware transport for fresh contact,
   local hours, explicit holiday exceptions and pickup/delivery/departments evidence. Corporate-only
   links stay candidates until branch scope is established. Existing records do not contain enough
   evidence to fill most emails, exceptions or service links automatically.
3. Refresh known OSM native IDs in bounded batches (query builder `osm_verification_query`), so
   lifecycle changes remain visible even after a `shop` tag disappears. Also inspect separately
   mapped entrances with an independently reviewed business association; proximity is insufficient.
4. Acquire a pinned Iowa subset of Overture/Foursquare after license/provider-lineage review.
   These are useful for contacts/closure assertions; an existence confidence is not field accuracy.
5. Review retailer floor-plan/aisle assertions against an exact branch/version. Neither a department
   list nor a product tag automatically becomes an aisle mapping.

See the [source/API discovery](RETAIL-DATA-DISCOVERY.md) and [execution evidence](investigations/store-enrichment-20261020/plan.md).

Current Iowa execution and updated provisional-contact policy: [Iowa field refresh](IOWA-FIELD-CRAWL.md).
The numerical acquisition priorities above describe the earlier 735-store baseline.
