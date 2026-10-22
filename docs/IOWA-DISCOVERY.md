# Iowa grocery directory discovery

The Iowa scope is all grocery stores, including independents, conventional supermarkets,
grocery-selling supercenters and warehouse clubs. Convenience stores, standalone pharmacies,
dollar stores and specialist meat markets are outside scope. No product inventory is captured.

`python scripts/expand-iowa-directory.py RUN_DIRECTORY` prepares an offline reconciliation
against `--data-dir` (default `/data`). `--acquire --include-osm` explicitly downloads public
USDA SNAP and OpenStreetMap directories. `--publish` publishes the reviewed, reconciled
additions through fenced jobs and immutable catalog packs. Acquisition and publication are
separate operations; running the script without those flags cannot request source data or
publish a catalog. Routine tests mock all source transports.

## Sources and checks

* USDA FNS [SNAP retailer ArcGIS service](https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0)
  and [official publisher item](https://www.arcgis.com/sharing/rest/content/items/8b260f9a10b0459aa441ad8588c2251c?f=json).
  Verify the publisher, schema and data clock; freeze the Iowa object-ID set and verify every
  returned ID in batches of 100. Count, truncation, duplicate-ID or source-clock discrepancies
  fail acquisition. The provider's `Record_ID` is retained as a native record ID, not represented
  as an FNS authorization/license number. SNAP authorization does not establish current opening
  hours, stock, a retailer agreement or a complete grocery census.
* [OpenStreetMap Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API): one bounded Iowa
  area query for supermarket/grocery and related format candidates. Native node/way/relation
  IDs, source clock, original tags, attribution and ODbL license remain attached. Query errors,
  incomplete responses and duplicated IDs fail that source explicitly. Missing addresses and
  uncertain formats remain review items.
* [Iowa DIAL's license/inspection directory](https://dial.iowa.gov/i-need/records) is an
  independent validation lead. Its [legacy inspection portal](https://iowa.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx)
  covers reports through 14 October 2026 and directs newer reports to the replacement system.
  The replacement [SAFHER portal](https://safher-portal.dial.iowa.gov/safher-portal) returned only a JavaScript application shell to the documentation fetch; no browser provider was available for interactive inspection. No complete, active grocery-license denominator has yet been established from it. Inspection
  history alone would also need active-license and store-format reconciliation.

The bulk transport has a real operator contact (`hello@foldlab.app`), a two-second per-host
minimum, 50-request and 24 MiB aggregate budgets, bounded responses/timeouts, origin allowlists,
public-address pinning and no redirects or credentials. These directory API requests are
separate from retailer HTML crawls, which retain robots checks, 45–90 second randomized
spacing (or stricter robots delay), 500 requests/day/host, existing holds and the cumulative
paid-provider budget. This discovery script does not make Jev/OpenAI requests.

## Reconciliation and updates

Keep native assertions and canonical identities separate. Exact normalized full addresses
and compatible store/chain names can match an existing store; compatible assertions from two
providers can share one newly proposed record. Suite information participates in identity.
Coarse addresses, missing coordinates in a city with the same chain, nearby stores, alternate
addresses and name/location changes become review holds. They never merge identities by name
or proximity alone. Records with insufficient addresses, invalid coordinates or conflicting
state evidence are held. SNAP's broad `Super Store` classification does not override pharmacy,
dollar-store or convenience exclusions. Ambiguous specialist formats are reviewed.

`format-decisions.json`, when present, binds operator format decisions to the input bundle
and each exact native payload hash, with evidence URLs, reason and review time. It can resolve
an uncertain grocery format; it cannot override identity/location/state failures or an
explicit format exclusion. Bender's two Iowa stores were checked against its
[official directory](https://bendersfoods.com/), which resolves SNAP's `Other` category.

The script reparses pinned raw assertions with the current classifier before publication.
It reconciles again at the serving generation under the heavy-job lock. Publication adds or
refreshes this operator source (`iowa_store_discovery`, partition `IA`) with `complete=false`:
absence never deletes a store or asserts closure. Existing other-source store facts/IDs and
USDA/map packs are checked for preservation. Replaying the same run retains IDs and adds no
records; a new dated acquisition can incrementally add or refresh this source. Changed native
addresses/names remain held. This is an explicit operator workflow, not a newly enabled
periodic source scheduler. The generic `usda_snap` source is a separate adapter/policy.

## Run evidence and coverage

Each dated run retains `status.json`, per-request raw artifacts and hash/status receipts,
`bundle.json`, `candidates.jsonl`, `plan.json`, `records.jsonl`, `crosswalk.jsonl`,
`reviews.jsonl`, `excluded.jsonl` and, after publication, `publication.json`. Failed acquisition
attempts stay in their original run directories. Do not overwrite them with retries; use a
new directory. A successful acquisition status alone is not proof of publication.

A review count is a count of source assertions, not distinct missing stores: it includes
incomplete OSM addresses, alternate identities, uncertain formats and assertions that may
already describe a published store. Exclusions likewise are assertions, not missed groceries.
All 99 counties appearing in the SNAP reference proves statewide discovery reach, not that
all grocery stores are represented. `census_complete` stays false until the denominator and
remaining reconciliation gaps are independently validated.

The upstream ATP completeness guard now checks the matching pinned run's detailed spider
stats: normal finish, drained queue, positive item count matching the raw export, and no
unreviewed count drop greater than 20% from a known good count. Missing stats, timeouts,
unfinished queues or mismatches mark the snapshot partial and retain the last good count.
Archive members remain partial until separately reconciled. Valid GeoJSON and zero errors in
an aggregate status are insufficient evidence of completeness.
