# Store, product and retailer API discovery — 2026-10-20

This is documentation research plus read-only retained-data analysis. No retailer connector,
authenticated retailer API call, new source bulk download, paid enrichment or image request was
performed. Published product descriptions/nutrition remain separate from branch inventory.

## Public and retained datasets

| Source | Useful evidence | Limits and current work |
| --- | --- | --- |
| [USDA SNAP retailer locator](https://www.fna.usda.gov/snap/retailer-locator) | Store name/type/address/coordinates and authorization snapshot; historical authorization dates in the historical file | No SKU, aisle, hours or current stock. The retained Iowa extract has 2,882 retailer assertions including excluded formats. Native Record_ID is not represented as an FNS license number. Reviewed crosswalk links are attached to canonical stores. |
| [OpenStreetMap](https://wiki.openstreetmap.org/wiki/Key:opening_hours) | Contacts, hours, timezone tags, accessibility, lifecycle and separately mapped entrances where present | Retained Iowa discovery has 666 location assertions. Community tags can be incomplete/stale; unknown or disused is not permanent closure. Store associations need review. ODbL attribution retained. |
| [Overture Places](https://docs.overturemaps.org/schema/reference/places/place/) | Phones, emails, websites, address, operating status and provider lineage | Offline extract adapter implemented; no real extract acquired. Existence confidence is not confidence in each contact field. Provider-derived copies count once. |
| [Foursquare OS schema](https://docs.foursquare.com/data-products/docs/places-os-data-schema) | Contact fields, native place ID, provider refresh/marked-closed dates | Offline extract adapter implemented; no real extract acquired. Marked-closed date is not the actual business closure date. Verify extract license/attribution before acquisition. |
| [USDA branded foods](https://fdc.nal.usda.gov/docs/Branded_Foods_Documentation_Apr2024.pdf) | FDC ID, GTIN where valid, brand, product description and nutrition | Retained catalog projected into native product records, preserving original food references and nutrient amounts/units. Brand ownership/distribution is not branch assortment. No FDC-ID or same-GTIN nutrition merge. |
| [Open Food Facts](https://openfoodfacts.github.io/documentation/docs/Product-Opener/v2/search/get-search/) | Product identifiers, community product/label data; stores_tags and purchase_places_tags as purchase hints | Owner selected en:united-states labels from the retained 13,179,356,850-byte compressed export. Country labels are community scope, not a US-market census. Store tags may suggest a banner but do not identify an exact branch or current stock. Raw hints remain in source_record. Snapshot boundary/delta alignment is unverified; recurring acquisition stays disabled. |
| [Open Prices](https://openfoodfacts.github.io/open-prices/guides/data/) | Dated price/product/proof observations linked to native OSM locations | Retained US sample: 42,822 observations, 368 OSM locations, 26,689 valid GTINs; 14,136 GTINs match the retained USDA catalog (23,443 observations), using strict normalized GTIN only. The exact OSM-ID join against the reviewed Iowa crosswalk yields **zero branch matches**. No Iowa inventory is inferred. No prices pack published by this work. |

The native product retail-evidence route can represent historical observations separately from
listings and live stock. A future Open Prices import should preserve source price ID, native OSM
type/id, proof ID, observation date, currency, GTIN and exact branch resolution status; quarantine
ambiguous GTINs/branches and currency anomalies. No proof images were fetched. The retained US
sample has 11 non-USD observations that require review. A national OSM crosswalk could improve
branch matching beyond this Iowa-only crosswalk; it would still establish historical evidence.

The exact retained-price result and its reproducible read-only script are in
[investigations/store-enrichment-20261020/price-crosswalk.json](investigations/store-enrichment-20261020/price-crosswalk.json).
Earlier GTIN coverage is dated 2026-10-18, not a claim of today's live source coverage.

## API shortlist — discovery only

| Provider | Potential functionality | Access / decision |
| --- | --- | --- |
| [Kroger developer platform](https://developer.kroger.com/reference/) and [Kroger-owned API documentation](https://www.postman.com/kroger/the-kroger-co-s-public-workspace/documentation/nryx3kn/kroger-partner-apis?entity=request-4826685-c459db82-57d0-49d8-9bcd-1f6550558606) | Location-specific product price, availability and aisle information when filter.locationId is supplied; product/UPC identifiers | OAuth application and appropriate public/partner entitlements must be confirmed. Strong candidate for aisle functionality where Kroger banners are relevant. Coverage/redistribution are not assumed. No account, key or request used. |
| [Instacart Developer Platform](https://docs.instacart.com/developer_platform_api) / [API overview](https://docs.instacart.com/developer_platform_api/api/overview/) | Nearby retailer discovery and recipe/shopping-list product handoff; current introduction advertises shopping/product discovery | API key/representative and endpoint-specific approval required. Verify actual product/inventory entitlements before promising a standalone stock API. Useful app integration candidate; not assumed to permit bulk copying. |
| [Instacart Catalog API](https://docs.instacart.com/catalog/catalog_api/overview/) / [Connect](https://docs.instacart.com/connect) | Retailer-side item/catalog and fulfillment integration | Merchant/partner integration, not a general public export of every retailer's inventory. No connector implemented. |
| [Walmart Marketplace inventory](https://developer.walmart.com/global-marketplace/reference/getinventory) | Seller SKU/ship-node inventory | Seller account/token; does not establish access to every Walmart store's grocery assortment. Not a solution for our statewide branch inventory goal. |
| [Hy-Vee supplier content channel](https://www.salsify.com/retailers/hyvee) | Supplier product-content syndication | Supplier/retailer relationship; not a verified public shopper inventory API. No public consumer-data API verified in this research for Hy-Vee, Fareway, ALDI or Trader Joe's. This is an evidence gap, not a claim that none exists. |

Recommended next decision: evaluate Instacart for shopping-list/pickup/delivery handoff and Kroger
for exact-branch aisle/product evidence after access and permitted storage are confirmed. Do not
reverse-engineer private storefront endpoints to fill the gap. No keys are needed for this
research-only phase, and none of these connectors was implemented.

## Storage guidance availability

The documented official [FoodKeeper JSON resource](https://catalog.data.gov/dataset/fsis-foodkeeper-data)
continues to return HTTP 403 from the tested clients. The full FoodKeeper dataset was not imported.
To make the Storage guidance page useful now, a reviewed official
[FoodSafety.gov Cold Food Storage Chart](https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts)
snapshot supplies 49 complete table rows under a separate source ID. Seven ambiguous multiline
source lines were explicitly excluded. Original ranges, refrigeration/freezer temperatures and
quality-only freezing caveats are retained; no precise expiration is invented. The chart's
source review date is 2023-09-19; retrieval today does not make it a newly revised source.
