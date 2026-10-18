# 09 — Integrating with our-recipes / Bòrd

## Keep household logic in its existing application

Bòrd owns reviewed pantry products/batches, purchase intake, recipes, nutrition snapshots, shopping deficits, store preferences and Instacart handoff. The food API owns reusable catalog data and public/licensed evidence. Lookup is not consent to create a product, add stock, alter a recipe, record consumption or place an order.

The current integration seams were rechecked at `843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb`: food-data source types/checksum validation, provider/cache service and supermarket profile input schemas [R08–R10]. Inspect current services, DB tables, auth/origin/actor guards and migrations at implementation time. Do not extrapolate old auth descriptions.

## Two rollout stages

**Stage A, API repository only:** keep the current USDA mirror variables working. Existing Bòrd continues using `/fdc/v1` with its current provider. Ship typed native contract, fixtures, client example, and updated compatibility script. This is safe even before the companion app changes.

**Stage B, companion repository:** add a server-only `BordCatalogClient`, native store selection and generation-aware food transport. Run `prompts/04-BORD-COMPANION.md` in an authorized `our-recipes` checkout. Editing API code alone is not proof this stage is deployed or tested.

## Proposed configuration

```dotenv
BORD_FOOD_API_BASE_URL=http://bord-food-api:8080
BORD_FOOD_API_KEY=<server-side read key>
FOOD_DATA_MODE=catalog_preferred
FOOD_DATA_ALLOW_REMOTE_FALLBACK=false
STORE_DIRECTORY_ENABLED=true
```

Modes: `direct` preserves the current source-provider path; `catalog_preferred` uses local first with only explicitly enabled external fallback; `catalog_only` prohibits direct external food lookups. Default fallback remains false. Existing `USDA_FDC_BASE_URL`, `USDA_FDC_API_KEY`, `USDA_FDC_ENABLED` remain supported. Do not put keys in `NEXT_PUBLIC_*`, responses or browser bundles. Compose must pass these server variables; `.env` presence alone does not prove container propagation.

## Source versus transport

A USDA record delivered by Bòrd Food API remains `provider=usda_fdc`; OFF remains `open_food_facts`. Introduce a nested catalog reference with `transport_id`, `source_id`, `source_record_id`, `source_revision`, `catalog_generation`, `canonical_product_id`. Do not use `provider=local` for the transport, because that value already represents household-local product behavior in current code.

Keep current food record semantics unless an additive migration is necessary. Extend enums only for an actual underlying source. Do not present joined source attributes as one authoritative averaged nutrition vector. Source alternatives retain attribution, units, missingness, image licenses and preparation basis.

## Concrete change map

| Current location | Intended work |
|---|---|
| `src/lib/config.ts` | Validate server-only catalog config, modes, timeout and fallback policy |
| `src/lib/domain/food-data.ts` | Add catalog/source-revision references and not-ready/conflict states; preserve GTIN checks |
| `src/lib/services/food-data-service.ts` | Route local catalog requests; separate resource budgets from external quotas; namespace cache by config/generation/normalizer |
| `src/lib/providers/food-data-provider.ts` | Preserve source-provider contract; add transport adapter only as necessary |
| `src/lib/providers/usda-food-data-provider.ts` | Keep legacy behavior; expose additional supported measures natively without mutating old source facts |
| `src/lib/domain/list-settings.ts` | Add nullable canonical store reference to supermarket-profile input, server-validated |
| `src/lib/db/schema.ts` + next actual migration | Store catalog link/snapshot separately from profile identity and custom fields |
| Current supermarket/list services and UI | Branch picker, source freshness, unlink/relink and manual custom-store fallback |
| Existing food picker/confirmation services | Pin source revision on selection and recheck on confirmation |
| Current system/settings UI | Read-only catalog/bootstrap/source state; no provider secrets |

Inspect actual service/UI filenames instead of fabricating them. Do not choose a numeric migration filename from this plan; use the repository’s next migration mechanism and verify schema history.

## Store profile link

Add nullable fields or a separate association table: household profile ID, `catalog_store_id`, linked source/catalog version, linked-at timestamp and selected immutable store metadata snapshot. Preserve existing profile UUID, name, notes, location label, section/aisle IDs, ordering, category rules and shopping list relations.

A catalog correction can update an official-metadata projection, but user text/route overrides never change automatically. If the source says relocated/closed, show an actionable notice; do not silently relink a household to a different address. Unlink keeps local profile data. A missing/disabled catalog does not disable current shopping lists.

## Store ordering precedence

Household override -> usable branch-specific placement -> reviewed department mapping -> existing deterministic category route -> Unassigned. Unknown maps/aisles never produce guessed official aisle numbers. When a map changes, retain manual routes but invalidate unverified coordinate anchors tied to the old version.

## Reviewed food confirmation

Carry the selected immutable source revision and expected GTIN. The server re-fetches that revision through the catalog transport or returns renewed-review required. Confirmed lawful snapshots are stored in Bòrd for durable nutrition/recipe attribution; rotating public catalogs must not erase them. Local user edits stay separate from imported provenance.

Include endpoint/config fingerprint, source generation, normalizer and locale in lookup cache identities. Poll capabilities/generation on a bounded schedule (proposed five minutes with conditional requests), invalidate affected search caches on generation change, and keep record-revision caches when compatible. No cross-household receipt details leave Bòrd.

## Change feed and watched stores

V1 can use generation polling. A later sync loop uses `/v1/catalog/changes` to update only linked official store projections. Cursor loss triggers a bounded re-fetch of linked entities, not a national reimport into Bòrd. The API may support an operator-configured list of watched store IDs for higher freshness; V1 does not automatically upload a household’s watchlist. Demand signals contain only required IDs and only under explicit configuration.

## Purchases and prices

Continue existing Bòrd purchase idempotency and transaction boundaries. Optionally add store ID, package/currency/basis and observation date to a reviewed purchase. These remain private. The API returns public historical evidence; Bòrd combines it with its private history for the UI. No duplicate pantry system or automatic upstream receipt contribution.

Pack-aware budgets and leftovers are V2: API supplies package/measure/price evidence, while Bòrd calculates actual deficit and integer pack counts. Distinguish cash paid from consumed portion cost, and no “cheapest” claim with omitted unknown-price lines.

## Offline and failure behavior

Bòrd’s native client displays `initializing`, `temporarily unavailable`, `stale` and `disabled` distinctly; existing locally stored products remain usable. A selected-store offline read bundle is a later feature. Do not add offline mutation replay without a separate conflict/idempotency design. The companion tests should preserve the app’s current PWA policy.

## Required integration evidence

Run current formatting/lint/types/unit/integration/OpenAPI gates and the repository’s existing release tests as applicable. Use synthetic source fixtures; forbid real paid/external calls. Test old Bòrd against new USDA endpoints and new client against fixtures for uninitialized/ready/stale/partial/rights-blocked states. Test profile migration, unlink/relink, preserved aisle overrides, unknown stock, changed source revision, provider cache isolation and idempotent confirmation. Record an unavailable browser/Docker environment as not run, never passed.
