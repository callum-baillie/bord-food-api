# 20 — Data dictionary and semantics

This is the shared vocabulary. JSON Schema constrains representative example shape; implemented Pydantic/OpenAPI and migration tests must cover the complete API, not just the sample subset.

| Field / concept | Type / rule | Meaning |
|---|---|---|
| `schema_version` | semantic version string | Public contract version, not upstream source revision. |
| `chain_id`, `store_id`, `product_id` | persistent opaque string | Assigned identity stable across name/URL changes; never an unscoped external identifier. |
| `external_ids` / identifier rows | namespaced string values | Native retailer/source identifiers; preserve leading zeros and validation state. |
| `source_id` | registered identifier | One source/policy family, e.g. `all_the_places`; not a transport URL. |
| `source_release_id` | source-qualified string | Immutable revision/run/artifact identity when known. |
| `artifact_sha256` | 64 lowercase hex characters | Downloaded bytes fingerprint; not necessarily an upstream signed checksum. |
| `content_hash` | versioned canonical hash | Semantic normalized facts, excluding retrieval/progress noise. |
| `normalization_version` | stable algorithm identifier | Changing parser/hash semantics can require reprocessing even with identical source bytes. |
| `catalog_generation` | opaque generation ID or null before publication | One consistent immutable read view and identity crosswalk version. |
| `source_observed_at` | UTC timestamp or null | When source actually observed the real-world fact; do not substitute download time. |
| `source_published_at` | timestamp/date with precision or null | Publisher’s date for the dataset/document. |
| `retrieved_at`, `last_checked_at` | UTC timestamps | Local HTTP retrieval/conditional check dates; distinct from observed truth. |
| `valid_from`, `valid_until` | nullable timestamps | Explicit source validity, not a guessed universal TTL. |
| `freshness_expires_at` | policy-computed nullable timestamp | Local freshness decision with rule version; not contractual validity. |
| `reported_store_count` | nonnegative integer plus scope/date/qualifier | Published claim, possibly parent/mixed-format; not local observed count. |
| `observed_store_count` | integer plus generation/filter | Unique eligible branches actually imported under a declared scope. |
| `states_50`, `dc_present`, `territories` | integer0–50, tri-state, nullable list | U.S. geography kept explicit; avoid counting D.C. as a state. |
| coordinates | nullable paired latitude/longitude | Valid ranges and source/accuracy; no `(0,0)` sentinel for missing. |
| timezone | IANA identifier with basis | Local hours interpretation; unknown timezone means open-now may be unresolved. |
| regular hours | weekday intervals with end-day offset | Local civil time; split overnight ranges and exceptions explicitly. |
| date exceptions | nullable list plus status | Null unknown, empty list explicitly checked/no known exceptions. |
| lifecycle | listed/open/temporarily_closed/closed/missing_candidate plus evidence | Source absence alone cannot set `closed`. |
| `assortment` | scoped listing evidence | Does not imply quantity or current stock. |
| `availability` | explicit status plus channel/time | Unknown is not out-of-stock. |
| price | exact decimal string + ISO currency + basis | Distinguish shelf/pickup/delivery, package/weight, promotion/tax/loyalty. |
| package quantity | decimal + compatible dimension/unit/form | Net versus drained/edible quantity and multipack counts remain distinct. |
| nutrients | source amount/unit/basis/form | Missing stays missing; zero stays zero; no averaging conflicts. |
| allergens | claims with unknown/present/reported-absent scope | Empty array is not certified allergen-free. |
| map status | discovery status + rights status separately | A known consumer app feature is not a downloaded branch asset. |
| placement | branch/item/aisle/section/shelf plus version/time | Multiple placements possible; no implicit routable coordinate. |
| checkpoint | pending/committed source cursor | Committed only with matching visible catalog publication or documented no-op processing. |
| job fencing token | monotonic lease token | A stale worker cannot publish after another takes ownership. |
| `rights_policy_id` | reviewed versioned policy | Storage/display/transform/export/caching/media decisions are separate. |
| `verification_level` | planned/offline-tested/live-verified/deployed | Do not conflate implementation tests with live access evidence. |

## Absent versus null versus empty

For native responses, required known-shape fields can be null with an explicit status. Omit only truly optional extension fields; consumers must tolerate additive properties. Empty search results are successful only when the relevant pack is usable. `[]` on unknown branch offers accompanies a capability/evidence status, not “free” or “never sold.”

## Version and ID stability

A fact correction creates a source/entity revision but keeps its canonical ID. Merge/split decisions have their own history and aliases. A store moving to a different physical site requires reviewed lineage; blindly keeping or replacing an ID from a branch number is unsafe. Bòrd must retain the selected snapshot and handle canonical alias changes without losing household records.
