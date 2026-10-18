# 18 — Source ledger and verification boundaries

Prepared 2026-10-17. Design choices and proposed schedules are recommendations, not facts asserted by these sources. Each source has a verification level. URLs are discovery documentation; they do not automatically grant crawl or reuse permission.

API baseline: `13ba74e56f9d383edb2cfc57d4020d2c9943705e`. Bòrd integration baseline: `843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb`. Read the actual checkout before implementation.

## R01 — Food API project instructions
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/AGENTS.md

Keep immutable serving catalog and offline fixtures; actual checkout instructions prevail.

## R02 — Food API startup and CLI
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/__main__.py

Current startup blocks on import; new behavior is intentional.

## R03 — Food API routes and bounds
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/api.py

No additional execution or access guarantees.

## R04 — Food API configuration and download
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/settings.py
- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/download.py

No additional execution or access guarantees.

## R05 — Food API catalog and legacy schema
Evidence: **prior_connected_review_same_commit**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/catalog.py

Full implementation reviewed in the prior plan; current tree retains this commit.

## R06 — Food API streamed importer
Evidence: **prior_connected_review_same_commit**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/bord_food_api/importer.py

No runtime import/test performed.

## R07 — Food API container and test inventory
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/bord-food-api/blob/13ba74e56f9d383edb2cfc57d4020d2c9943705e/Dockerfile
- https://github.com/callum-baillie/bord-food-api/tree/13ba74e56f9d383edb2cfc57d4020d2c9943705e/tests

Dockerfile and current tree inspected; application tests not executed.

## R08 — Bòrd food-data domain
Evidence: **connected_repository_read**. Review: 2026-10-17.

- https://github.com/callum-baillie/our-recipes/blob/843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb/src/lib/domain/food-data.ts

No additional execution or access guarantees.

## R09 — Bòrd food-data service
Evidence: **connected_repository_read_partial**. Review: 2026-10-17.

- https://github.com/callum-baillie/our-recipes/blob/843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb/src/lib/services/food-data-service.ts

First 155 lines inspected in this run; provider registry/cache/budgets, not entire application audit.

## R10 — Bòrd supermarket-profile input contract
Evidence: **connected_repository_read_partial**. Review: 2026-10-17.

- https://github.com/callum-baillie/our-recipes/blob/843cd7c017b6a633a1691c8d8a25d7f70c6ee7bb/src/lib/domain/list-settings.ts

Profile input and update definitions inspected; exact DB/migration names must be confirmed during implementation.

## S01 — USDA FoodData Central bulk downloads and data guidance
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://fdc.nal.usda.gov/download-datasets/
- https://fdc.nal.usda.gov/api-guide

Discover current JSON ZIPs; no bulk archive downloaded. CC0 data; keep dataset types and dates separate.

## S02 — All The Places published output and run discovery
Evidence: **official_documentation_and_connected_code_review**. Review: 2026-10-17.

- https://github.com/alltheplaces/alltheplaces
- https://github.com/alltheplaces/alltheplaces/blob/master/API.md
- https://data.alltheplaces.xyz/runs/latest.json
- https://data.alltheplaces.xyz/runs/latest/output/{spider_name}.geojson

Per-spider latest redirects to latest successful non-empty run; no output acquired/validated. Data CC0, code MIT per project.

## S03 — USDA SNAP current retailer download
Evidence: **official_indexed_documentation**. Review: 2026-10-17.

- https://www.fna.usda.gov/snap/retailer-locator

Direct page access was restricted; exact current CSV download resource not verified. Do not invent a filename or ArcGIS ID; current and historical datasets differ.

## S04 — Open Food Facts JSONL data and licensing
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://openfoodfacts.github.io/openfoodfacts-server/api/
- https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz

Database ODbL; contents/media terms separate. No full data download; endpoint existence/health must be checked at runtime.

## S05 — Open Food Facts official Parquet distribution
Evidence: **official_dataset_card_review**. Review: 2026-10-17.

- https://huggingface.co/datasets/openfoodfacts/product-database
- https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet

Different transformed schema from raw JSONL. Pin dataset revision and resolved assets; do not assume range filtering avoids all download bytes.

## S06 — Open Food Facts delta exporter
Evidence: **connected_exporter_code_review**. Review: 2026-10-17.

- https://github.com/openfoodfacts/openfoodfacts-server/blob/main/scripts/mongodb_dump.sh
- https://static.openfoodfacts.org/data/delta/index.txt

Active product last_modified_t intervals (from,to], bounded recent retention; no general deletion-tombstone guarantee. Surfaced index content was stale/cached, not a successful current live-health check.

## S07 — Open Prices bulk exports
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://openfoodfacts.github.io/open-prices/guides/data/
- https://openfoodfacts.github.io/open-prices/guides/import-data/
- https://prices.openfoodfacts.org/data/prices.jsonl.gz
- https://prices.openfoodfacts.org/data/locations.jsonl.gz
- https://prices.openfoodfacts.org/data/proofs.jsonl.gz

Snapshot exports, ODbL; related files require join/revision checks. Proof image mirroring not required.

## S08 — FoodKeeper official data catalog
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://catalog.data.gov/dataset/fsis-foodkeeper-data
- https://www.foodsafety.gov/keep-food-safe/foodkeeper-app

Catalog lists JSON/XLS and CC0/irregular updates; runtime resolve safe current URL. Legacy HTTP link is not permission to downgrade TLS.

## S09 — Overture Places and release discovery
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://docs.overturemaps.org/getting-data/
- https://docs.overturemaps.org/guides/places/
- https://stac.overturemaps.org/catalog.json
- https://github.com/OvertureMaps/overturemaps-py

Current taxonomy/basic_category replaces older categories. Source-dependent licensing/provenance and overlap with ATP; V1.1 extension.

## S10 — OSM regional data and indoor tooling
Evidence: **prior_primary_source_research**. Review: 2026-10-17.

- https://download.geofabrik.de/north-america/us.html
- https://github.com/indoorequal/indoorequal
- https://www.openstreetmap.org/copyright

V1.1 geometry extension; actual supermarket interior coverage and rights must be measured, not assumed.

## S11 — Scrapy crawling controls
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://docs.scrapy.org/en/latest/topics/autothrottle.html
- https://docs.scrapy.org/en/latest/topics/settings.html

Optional implementation library; adaptive rate control does not replace robots, rights, allowlists or budgets.

## S12 — Kroger official developer interfaces
Evidence: **prior_official_documentation_research**. Review: 2026-10-17.

- https://developer.kroger.com/reference/api/location-api-public
- https://developer.kroger.com/reference/api/product-api-public
- https://www.postman.com/kroger/the-kroger-co-s-public-workspace

Current account entitlement, response schema, tariff and retention not tested. Disabled non-core integration; reverify before activation.

## S13 — Walmart developer API distinctions
Evidence: **prior_official_documentation_research**. Review: 2026-10-17.

- https://walmart.io/docs/opd/quick-start-guide/catalog-store-service-locator
- https://walmart.io/docs/affiliates/search
- https://developer.walmartdataventures.com/apis/reference/nrt-store-inventory-details

Supplier/store-service/affiliate contracts are not universal consumer grocery inventory access. Tariffs and account entitlement unverified.

## S14 — Instacart Developer Platform
Evidence: **prior_official_documentation_research**. Review: 2026-10-17.

- https://docs.instacart.com/developer_platform_api/
- https://docs.instacart.com/developer_platform_api/faq/

Retain existing Bòrd shopping handoff. Admission, account entitlement and fee not verified; no marketplace mirror claim.

## S15 — Walmart chain and Coralville dated examples
Evidence: **prior_dated_examples_and_source_code_review**. Review: 2026-10-17.

- https://corporate.walmart.com/about/location-facts
- https://www.walmart.com/store-directory
- https://www.walmart.com/store/2827-coralville-ia
- https://www.walmart.com/store/2827-coralville-ia/shopping-services
- https://www.walmart.com/cp/find-an-item-store-maps/6422847
- https://github.com/alltheplaces/alltheplaces/blob/master/locations/spiders/walmart_us.py
- https://www.walmart.com/sitemap_store_main.xml

Examples preserved from supplied files. Store hours/counts are dated facts, not newly fetched production records. Do not copy noncompliant/proxy settings from an upstream crawler.

## S16 — Woodman’s North Aurora store-map link
Evidence: **official_page_review**. Review: 2026-10-17.

- https://www.woodmans-food.com/store-locations/north-aurora/

Observed distinct PDF store-map and geographic map links. No PDF downloaded; no layout currency or reuse permission established.

## S17 — Codex repository guidance
Evidence: **official_documentation_review**. Review: 2026-10-17.

- https://developers.openai.com/codex/guides/agents-md
- https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex

Prompts rely on repository instructions, scoped tasks and test evidence; no specific model, paid feature, agent count or Goal-mode capability is required.

## Source fees and operational costs

USDA/ATP/SNAP and selected open bulk workflows require no paid data subscription under the published access paths, but compute, transfer, storage and maintenance still cost resources. Optional OFF/Open Prices/OSM licensing requires review of actual use. Current commercial provider tariffs have not been independently established for this package and must remain null/unknown. Previously researched numerical prices in the retained chain registry are dated references, not an active budget configuration. No paid source is enabled by default.

## Supplied artifact provenance

The original expansion plan and earlier registry/examples were read from conversation attachments. The registry is incomplete research, not a source-level census. `reference/input-artifacts.json` records actual local filenames, sizes and SHA-256 fingerprints. No website request is needed to validate those files.
