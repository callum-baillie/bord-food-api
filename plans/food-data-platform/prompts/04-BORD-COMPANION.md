# Companion Bòrd integration — run in an authorized our-recipes checkout

Implement the companion integration with the tested `bord-food-api` native contract. Read the current Bòrd AGENTS, schema/migration system, auth/actor/origin/idempotency boundaries, food-data providers/services, supermarket-profile services, current configuration and tests. Read `docs/09-BORD-INTEGRATION.md` from this package and the API’s generated OpenAPI. Never reset to the recorded audit SHA or copy old migration numbers.

Add a server-only `BordCatalogClient` with bounded requests and schema validation. Configuration: `BORD_FOOD_API_BASE_URL`, `BORD_FOOD_API_KEY`, `FOOD_DATA_MODE=direct|catalog_preferred|catalog_only`, `FOOD_DATA_ALLOW_REMOTE_FALLBACK=false`. Preserve existing USDA mirror variables. The local catalog is a transport: underlying provider IDs remain USDA/OFF, with generation/revision/canonical identity metadata added separately. Extend source enums only for genuine new sources.

Cache by transport/config fingerprint, source generation, normalization version and relevant locale. Do not charge local catalog requests against the external USDA quota. Catalog-only mode must prohibit remote fallback and source image fetches. No secret may reach client bundles, logs or backups that exclude credentials.

Add a nullable canonical store link and metadata snapshot to existing supermarket profiles using a new migration. Preserve profile UUID, names, custom labels, notes, aisle IDs/order, manual overrides and shopping-list references. Provide search/link/unlink/custom-store fallback. External updates are suggestions/evidence, never silent overwrite of household routing.

Integrate native food/product lookup into the existing review-first picker. Confirmation reloads the exact source revision or requests review on a material change; it never silently substitutes newer nutrition. Persist selected snapshots/attribution under existing household backup policy. Enrichment and source refresh do not create pantry stock, consumption or cart actions. Retain existing purchase idempotency and Instacart handoff.

Expose sanitized source/bootstrap status without creating an unprotected administration surface. Map absence/rights pending and stale hours remain explicit. Do not add offline write replay or copy the national catalog into household backups.

Tests use a mock/local API and temporary Bòrd database only. Cover T36–T40, current USDA provider compatibility, config switching, unavailable API and review/stock invariants. No live crawlers/downloads/paid requests/deployment/push. Return migration steps, actual tests and a precise implementation report. If API contract/code is unavailable, do not fabricate success: implement against the supplied contract with mocks and record the integration gate.
