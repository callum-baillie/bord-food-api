# 07 — Crawlers to implement, not run now

## Hard activation boundary

During Codex implementation, automated tests, image builds and this plan’s preparation: **no retailer crawl runs**. Examples and saved synthetic HTML fixtures support development. Bulk acquisition also stays out of production during implementation. At installed runtime, the bulk worker can start automatically under its configured preset; crawler requests require all of:

1. Global crawling enabled.
2. Specific adapter enabled.
3. Per-source/host crawl authorization recorded, including robots/terms review and identifying contact.
4. An approved discovery target and bounded scope.
5. Host/request/byte/time budgets available.

Map byte download and rehosting require separate storage/display permissions. A blank/unknown rights review is not an approval. This makes runtime automatic **after explicit setup**, not an open-ended crawler by default.

## Chosen stack

Keep simple discovery/extraction in Python and the central network policy. Use Scrapy as an optional acquisition extra for sites that need robust sitemap/pagination handling; use its AutoThrottle and robots support as additional controls, not as replacements for durable queue limits [S11]. Browser rendering is a separate, disabled capability for a future demonstrable need. Do not ship a browser in the default API image.

Do not clone/run the whole ATP spider suite on startup. Reuse its published CC0 outputs. Upstream spider code can demonstrate parsing but may include proxy/geolocation settings or robots behavior unsuitable for this installation; code availability does not mean those defaults should be copied. Pin and audit any reused implementation and preserve its software license.

## Adapter A — official store directory/sitemap discovery

**Purpose:** obtain source keys and canonical detail URLs for new/removed/changed stores when a bulk feed is unavailable or incomplete.

Input is a registered directory/sitemap descriptor, never an arbitrary browser URL. Output: source key, canonical URL, source-reported update marker when trustworthy, discovery scope/page completeness and available store fields. Maintain discovered URL membership/hash to avoid fetching every detail page on every check.

Use `lastmod` only as a hint. Websites can regenerate every sitemap date or omit changed pages; use conditional validators and scheduled audits. Resolve same-host relative links under a safe base. Ignore account, cart, search-product, ad and tracking URLs. Bound page count, depth, query variants and pagination; detect loops.

Walmart source lead: `https://www.walmart.com/sitemap_store_main.xml`, store pages such as `/store/2827-coralville-ia`, and prior ATP `walmart_us` implementation [S15]. **Walmart direct crawling is not a required live capability in V1.** If access is blocked, retain ATP bulk/local facts and mark the adapter unavailable. No CAPTCHA bypass, mobile-app private API emulation, session harvesting or hidden endpoint scanning.

## Adapter B — Woodman’s official map-link pilot

Known public example: `https://www.woodmans-food.com/store-locations/north-aurora/` [S16]. The observed HTML has an explicit `Store Map (PDF)` link and a separate geographic map link. Implement a bounded extractor tested with a synthetic fixture reflecting those distinct link roles.

Extract candidate link, anchor/context, associated official branch page, file type hint and discovery evidence. A PDF extension alone is insufficient: exclude weekly ads, coupon leaflets and unrelated documents. Exact file content type and layout classification are verified only during an authorized asset-validation step. Match branch address/number/name rather than filename slug alone. A chain-level generic guide stays chain-scoped.

Initial unit-test fixture contains made-up domain URLs under `.test` and no downloaded map bytes. Runtime discovery may publish the official link and `rights_pending`; it may not fetch/rehost the PDF until rights permit. Track `discovered`, `not_found`, `blocked`, `unsupported`, `ambiguous`, `stale`, `rights_pending` separately.

## Adapter C — structured data/store-page details

Parse explicitly allowed Schema.org `Store`, `GroceryStore` or `LocalBusiness` JSON-LD when present, then retailer-specific HTML as a fallback. Neither `hasMap` nor an image implies an indoor floor plan. No JavaScript execution is needed for JSON-LD extraction. An internal page-state object is a fragile parsing detail, not a documented API contract.

Request only new entities, missing required fields, changed roster hashes, user/operator correction triggers or due field audits. A new store with complete bulk fields should not trigger this adapter by default. Match the returned page to the intended branch before writing assertions.

## Crawl defaults proposed for enabled sources

One request at a time per retailer host; minimum 5-second spacing; adaptive backoff; 500 pages/day/source; 50 pages/run unless explicitly raised; 2 MiB HTML response cap; 3 redirects; max depth 2; no query permutations; no authenticated sessions. The tighter of site policy and these limits always wins. Robots retrieval is cached no longer than its supported policy requires and checked before new crawl scope. Use a real identifying User-Agent with configured operator contact. Placeholder contact blocks production crawling.

Sitemap XML is parsed without external entities and within compressed/expanded byte/URL-count limits. Headless browser work, if added later, uses isolated ephemeral containers, no credentials, no internal-network access and lower budgets.

## Map asset model and safe rendering

Keep source URL, branch/floor association, original content hash, media type, source version/date, observed map date, rights policy, dimensions, coordinate system and asset freshness. Unknown dates remain null. A new version invalidates unverified placement anchors; do not silently attach old aisle coordinates.

Allowed originals are stored content-addressed, not under user-controlled paths. PDF rendering is sandboxed, network-disabled, CPU/time/page/pixel limited; SVG is sanitized or rasterized and never served with active scripts. Set safe content types and attachment disposition for originals. Product images have equivalent limits and independent terms. Do not use OCR for ordinary HTML/JSON data; any later scanned-map interpretation must be reviewed and remain distinguishable from official geometry.

## Future routing

A real graph requires walkable spaces, entrances, connections, obstacles and validated item anchors. A map image or aisle number is insufficient. Keep manual household aisle ordering useful even with no map. OSM/IndoorEqual geometry, IMDF or a licensed commercial map may support a later version, but none provides a proven nationwide supermarket floor-plan database in this plan.

## Setup procedure after implementation

Operator selects one adapter/source, reviews terms/robots/reuse, sets identifying contact and budgets, runs a **network-free plan**, then explicitly activates a limited runtime job. Inspect the change/rights report before expanding its scope. This setup is documented in `prompts/06-RUNTIME-ACTIVATION-LATER.md`; it is not part of the main implementation run.
