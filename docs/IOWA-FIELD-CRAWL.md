# Iowa store field refresh

This campaign refreshes Iowa branch contacts, local hours, timezone, explicit holiday
exceptions, operating status, pickup/delivery links, departments and accessibility.
It retains floor-plan links and aisle/entrance assertions for review. It does not collect
full product inventory, product pages, prices, accounts, carts or checkout data.
Other states remain staged. The directory is not a verified census of active Iowa groceries.

## Evidence and publication

The serving API uses `store-field-evidence-v3`. A valid, fresh, exactly matched source
report may fill a missing field as `source_reported`. That means provisional information,
with source/observation/check dates and an expiry, **not independent verification**:
`verified_at` and `verified_until` remain null. Two independent provenance families agreeing
can mark a field `corroborated`; an assertion-bound operator review can mark it `reviewed`.
Conflicting values and original assertions remain available. An existing conflicting value
is retained rather than silently replaced. Provider existence confidence and Jev scores
are distinct from field verification.

ATP, a direct retailer page and an Overture copy of that retailer's data count as one
retailer family, including vendor-hosted locators. A newer exact official branch report can
supersede its own older ATP wrapper assertion; it cannot erase independent disagreements.
Source refreshes preserve enriched values and all original source records. Unsupported or
withdrawn provisional assertions fall back to the permitted baseline or remove a newly
introduced field. Raw assertion history remains intact.

Shared provider email addresses across distinct branch IDs are held for scope review,
including corporate customer-service contacts. They remain retained assertions with
`contact_scope=shared_across_locations`, not branch-specific email fields. A single provider
email is still provisional; direct retailer/independent corroboration is preferable.
Timezones are derived IANA `America/Chicago` for Iowa, not verified live opening status.
Holiday exceptions need explicit dates. Permanent closure needs explicit official plus
independent evidence or an operator review. Unknown is not open. Entrances and aisle/category
mappings require a bound human review and do not imply routable geometry or current stock.

Publication builds a replacement SQLite stores pack and atomically switches generations.
USDA FDC IDs, nutrient amounts/units, product/guidance/maps packs and non-Iowa stores are
preserved. A shared exclusive heavy-worker lock and renewable leases serialize publication.

## Extraction and source expansion

The bounded parser handles JSON-LD, microdata, pure JSON hydration, literal Yext profile JSON,
visible branch contact links and local weekly schedules. It binds the street and explicit
postal code or city/state, rejects ambiguous/corporate/footer/department-only evidence, and
never evaluates JavaScript. Explicit department tables are retained separately from grocery
hours and aisle mappings. Old paid-approved pages can be replayed offline with their actual
retrieval date, identity and HTML hash; replay makes no source or model requests.

The retained 2026-09-23.1 Overture Iowa extract supplements SNAP/OSM/ATP: 1,758 assertions,
1,258 grocery-classified candidates, 425 exact address/name assertions matching 410 existing
stores before six strict SNAP-plus-Overture additions. The 833 unmatched assertions are review
work, not 833 missing stores. Native IDs, provider clocks, licenses and lineage are retained.
Computed Overture confidence/signals are not independent votes. See the acquisition receipt.
No Foursquare authenticated API or recurring Overture acquisition was enabled.

## Execution policy

`scripts/run-iowa-fields.py` inspects offline by default; `--run` explicitly activates requests.
`scripts/run-iowa-fields-campaign.py` runs a primary pass and at most one canonical URL pass.
The second pass uses only observed HTTPS www/slash redirects or the reviewed ALDI locator
migration. It preserves store ID/address and performs fresh robots and exact branch review.
A maximum of one explicitly configured robots alias redirect may be fetched. Other branch
redirects are recorded without following them. No broad redirect, DNS or IP fallback exists.
Successful canonical routes are reusable only for unchanged source-bound store identities.

Each hostname shares persistent counters across runs: 500 attempts per UTC day, including
robots and failed attempts. Each request waits at least 45 seconds plus fresh random 0–45
seconds, applying any stricter robots delay/rate first. Explicit robots aliases also wait
between requests. HTML is bounded to 2 MiB; at most three requests per branch qualification
allow robots + one approved robots alias + branch HTML. No assets/images/PDFs are fetched.
A 64 MiB bounded conditional cache honors no-store/Vary and validates saved bytes; 304 reuse
still requires identity, robots, policy and review. Retry-After creates a shared host backoff.
Access/robots/network failures hold the host; they are not automatically retried.

Jev 1.14.0 checks every pilot page and selectively checks new/provider/homepage/canonical or
ambiguous pages plus a deterministic 5% sample. It receives bounded branch evidence. No paid
pre-fetch URL approval is needed after static source validation. Jev cannot authorize access,
resolve identity conflicts, invent facts or establish verification. Uncertain branches remain
held. Reservations persist before calls with no automatic paid retry. The owner's cumulative
ceiling is $15, including old runs; each full pass reserves at most $5/500 calls. The $0.01/call
reservation is a conservative accounting bound, not an invoice or measured spend. Keys stay in
a read-only worker secret mount, never catalog/config responses or logs. No image calls occur.

## Operations

Current run IDs, release hashes, actual outcomes and test evidence are in
[investigation results](investigations/iowa-fields-20261020/RESULTS.md). Parent and child status
files live under `/data/crawl-campaigns/` (host `/mnt/cache/appdata/bord-food-api/`). Each child
retains per-target requests/outcomes, reasons, HTTP status, fields, review and publication.
The parent reports active pass, deadline and summary. Missing branch URLs are explicit gaps,
not attempted or successful requests. Persistent crawl-history events keep prior failures,
operator reviews and unresolved holds across states/runs. Inherited holds cannot manufacture
new host failures, and metadata re-ingestion cannot reopen a reviewed physical attempt.

The original field campaign below is stopped. Current quality continuation and point-in-time coverage are documented in [quality results](investigations/iowa-quality-repair-20261020/RESULTS.md) and [reusable profiles](STORE-QUALITY-PROFILES.md). Stop only the current continuation with:

```sh
touch /mnt/cache/appdata/bord-food-api/crawl-campaigns/iowa-quality-continuation-20261020/STOP
```

Or `docker stop bord-food-iowa-quality-continuation-20261020`. Do not stop the serving API, Bòrd or
history observer. A source pause also prevents further work. Parent STOP propagates to the
active child before requests/decisions/publication. No automatic container restart is enabled.
Resume is explicit, with the same persisted config and `--resume --run`; finished child passes
are not recrawled, interrupted work remains subject to review, and the original seven-day
deadline, host counters, histories and cumulative budget persist. Removing STOP alone does not
start a process. A new config requires a new reviewed campaign, not an in-place running edit.

The pre-change consistent backup is `/data/backups/20261020-before-iowa-fields`. It contains
independent current packs, manifests, control/frontier/Jev/history SQLite snapshots and scoped
Compose checkpoints. Operator releases and configurations are versioned read-only mounts on
the existing pinned image; this operation does not require a Git push or a new image publication.
