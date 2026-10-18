# 03 — Domain, identities and evidence

## Entity grain

| Entity | One record represents | Ownership |
|---|---|---|
| Organization | A corporation/operator/cooperative, not every banner combined | Reference API |
| Chain/banner | A consumer-facing grocery brand in a country | Reference API |
| Store location | A physical branch/site incarnation with time-bounded aliases | Reference API |
| Source record | One upstream namespace/key/revision | Reference API |
| Assertion | A source-backed value for one entity/path/scope | Reference API |
| Product | A retail trade item identity, not a generic ingredient | Reference API |
| Food record | A USDA/OFF source record at a revision | Reference API |
| Retailer listing | A chain/operator-scoped SKU/product association | Reference API |
| Assortment evidence | A branch/channel listing observation | Reference API |
| Price observation | Dated price, basis, conditions and currency | Public API or private Bòrd, never mixed implicitly |
| Inventory observation | Dated reported availability for branch/channel/item | Same separation |
| Placement | Aisle/section/shelf or geometry anchor at a branch | Reference API plus private override in Bòrd |
| Map asset | One licensed source/version/floor, not a generic street map | Reference API |
| Store profile | Household name, chosen branch, route and preferences | Bòrd |
| Pantry batch / purchase / receipt | A household fact and its explicit transaction | Bòrd |

Never embed a full store catalog into a chain/store response. Link separate listing/observation collections. The same product may have multiple in-store placements and multiple channel prices.

## IDs

Allocate opaque permanent internal strings (for example `chn_<uuid>` and `sto_<uuid>`). Human-readable IDs in examples are assigned illustration values, not an algorithm based on a mutable name/address. Namespace every external key: `walmart_us:2827`, `usda_fdc:123`, `open_food_facts:<code>`, `osm:node:<id>`. Preserve raw retailer numbers as strings including leading zeros. Maintain aliases/redirects so Bòrd links survive source-ID churn and brand renaming.

Separate organization from banner. Walmart and Sam’s Club have distinct chain IDs even when the parent is shared. Walmart Neighborhood Market can be represented as a format/sub-banner with an explicit grouping rule; do not infer that ATP’s brand string is the entire canonical chain taxonomy.

A retailer source key that moves to a substantially different physical address can represent a relocated store. Keep the old site record and introduce a new site with `relocated_to`; review the operator-branch alias’s validity interval. A simple address spelling correction keeps the same store. A building’s fuel station, pharmacy and supermarket are not automatically separate grocery branches, nor blindly merged by coordinates.

## Matching

Existing explicit source crosswalk wins unless identity conflict is detected. New store candidates require compatible banner/operator, normalized address and spatial/phone evidence. Exact numeric distance thresholds are configurable candidate filters, not proof. Same address + conflicting operator or unit yields review. Correlated upstream sources (e.g. ATP appearing inside Overture) count as one provenance root, not independent corroboration.

Products use strict GTIN-8/12/13/14 checksum validation and compatible pack context. Keep the existing USDA permissive lookup only at the compatibility edge. A UPC-E, variable-weight label, PLU or arbitrary SKU must carry its type; do not pad it and claim a globally valid GTIN. Name/brand/package matching yields candidates unless an explicit reviewed crosswalk exists. Same GTIN never justifies averaging competing nutrition revisions.

## Temporal assertions

A public record carries `schema_version`, internal ID, source references and record metadata. Source assertions include:

- `source_id`, source record/release ID and root lineage.
- `source_observed_at` or `source_published_at` when known, `fetched_at`, `last_checked_at`, and separate `fact_changed_at`.
- `valid_from` / `valid_until` only when supported; a local TTL is `fresh_until`, not claimed real-world validity.
- Path, value, units, scope (`chain`, `branch`, `channel`), authority class, extraction method and normalized hash.
- License/policy ID, extraction/normalization version and review status.

Use `null` for missing values and an explicit status/reason. Empty allergens are not “allergen free.” Unknown stock is not zero. A page checked today may contain a years-old map. Source date and fetch date are never interchangeable.

## Fact precedence and corrections

Select preferred values per field, not by whichever source was imported last. Prefer suitable official branch data, then direct source-origin bulk, then independent supplemental observations, then explicitly labeled inference. Preserve conflicting assertions. A user override stays in Bòrd and is not replaced by catalog updates. Operator curation in the API is a separate audited overlay with evidence, never an edit to an upstream raw record.

Distinguish absent fields in a partial feed from explicit source deletion/nullification. Partial coverage cannot erase previously sourced hours or coordinates. A source’s withdrawal of an assertion does not erase another source’s evidence.

## Counts and geography

Store both `reported_count` (with date, banner/group scope, formats and geography) and `observed_count` (computed from a named published generation). Count distinct qualifying sites per chain; states_50, DC and territories separately. Keep `minimum_count`/`approximate` qualifiers. Neither count is silently promoted to a verified national census. Derived counts update when membership/lifecycle changes, without crawling corporate statistics pages every day.

## Quantities and retail data

Money is a decimal string plus currency, or scaled integer with an explicit scale. Include package/weight/volume basis, channel, tax status, loyalty/coupon requirement and observation date. Expose advertised versus historical price separately. A known product or historical purchase does not establish current branch stock. Inventory records need source-permitted expiry; after expiry they become stale/unknown in “current” projections.

Package amount, serving amount, net weight, drained weight and edible yield are different fields. Mass↔volume needs ingredient/form-specific density evidence. Dry/cooked and prepared/unprepared nutrient basis remain separate. API returns evidence and unresolved conversions; Bòrd owns pantry deficit and pack-choice calculations.

## Location and hours

Retain geodetic coordinates, source and accuracy; never synthesize coordinates from a ZIP centroid without a `centroid` accuracy label. Store IANA timezone, normal weekly periods, end-day offsets, holiday exceptions and department-specific schedules. “Open now” can be unknown when exceptions/timezone are missing. Do not apply the main-store hours to pharmacy or pickup slots.

## Example and schema relationship

`examples/real/` contains V1 native envelopes around the earlier Walmart/Coralville records. The original v0.1 files are preserved in `examples/reference-v0.1/`. Their map/stock/coordinates remain unknown. New examples are dated references, not freshly fetched production records. `contracts/*.sql` illustrates empty relational storage; Codex must implement migrations and validate actual domain constraints, not execute these files as an unreviewed production upgrade.
