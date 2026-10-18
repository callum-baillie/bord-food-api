# 04 — Bulk sources, acquisition and costs

**Research snapshot:** 17 October 2026. URLs are source leads/documented endpoints, not evidence that an import ran. Runtime must resolve, pin and validate each artifact. No data subscription or account is necessary for the default USDA/ATP workflow. Hosting, bandwidth and maintenance still cost resources.

## Acquisition order

1. Start the API with zero business records. Initialize only schema, source descriptors and an installation ID.
2. The runtime worker resolves configured bulk releases. Default core: the four selected USDA JSON datasets and approved All The Places U.S. retailer outputs.
3. Download within budget, normalize into staging, reconcile and publish usable packs independently. A slow/blocked optional source does not stall USDA/store serving.
4. Enable SNAP/OFF/Open Prices/FoodKeeper only when their operator policy is configured; use the source-specific behavior below.
5. Queue direct retailer detail/maps only for missing/changed/explicitly requested evidence and only for approved crawler adapters. Bulk output discovery is not permission to crawl every website in the output.

## Source catalog

| ID / source | Source/download location | Format and strategy | Activation / cost |
|---|---|---|---|
| `usda_fdc` | `https://fdc.nal.usda.gov/download-datasets/` | Discover latest per-type JSON ZIP; preserve original wrapper/type and source dates | Default core, $0, CC0 [S01] |
| `all_the_places` | `https://data.alltheplaces.xyz/runs/latest.json`; per-spider `/runs/latest/output/{spider_name}.geojson` | Whole source snapshot -> local ID/hash diff; actual resolved run date, not fetch date | Default core for approved descriptors, $0; CC0 outputs [S02] |
| `snap_current` | `https://www.fna.usda.gov/snap/retailer-locator` | Resolve official **current** CSV/resource link, preserve source snapshot metadata | Optional; $0 public data; direct page blocked in this review [S03] |
| `open_food_facts` | `https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz` | Stream baseline; changed-product delta files after matching baseline/cursor | Optional due size/ODbL; $0 data [S04–S06] |
| `open_food_facts_parquet` | `https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet` | Alternate baseline; resolve/pin dataset revision and adapt nested/list schema | Optional alternate, not a second logical product source [S05] |
| `open_prices` | `https://prices.openfoodfacts.org/data/prices.jsonl.gz`, `locations.jsonl.gz`, `proofs.jsonl.gz` under same `/data/` | Versioned JSONL snapshots -> ID/content diff, dependency-preserving country filter | Optional, $0 data, ODbL [S07] |
| `foodkeeper` | Catalog: `https://catalog.data.gov/dataset/fsis-foodkeeper-data`; JSON candidate `https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json` | Discover official English JSON, validate current HTTPS target; full small snapshot/hash | Optional, $0, catalog lists CC0 [S08] |
| `overture_places` | `https://stac.overturemaps.org/catalog.json`; `https://docs.overturemaps.org/getting-data/` | Pin release and schema, U.S. GeoParquet extraction, local diffs or validated release changelog | V1.1 optional; no mandatory paid query service [S09] |
| `osm_indoor` | `https://download.geofabrik.de/north-america/us.html` | Selected regional PBF/indoor extract; replication only after a proper baseline | V1.1 optional; ODbL; coverage unknown [S10] |

`configs/sources.manifest.example.json` is the machine-readable counterpart. Discovery URLs may redirect; every hop must meet the source’s exact network policy. A documented URL is not a blanket host wildcard.

## USDA: reuse, do not replace, the importer

The official download page supplies JSON and CSV, but the existing importer deliberately supports JSON/ZIP. Retain it. Resolve each selected data type separately, reusing the existing filename-date recognition. Do not synthesize the newest date or require the four sources to share a publication month. A single new Branded release should reuse unchanged Foundation/FNDDS/SR data; do not download/import all types again unnecessarily.

Maintain per-dataset normalized shards or staging membership so changing Branded cannot remove other types. For the legacy single USDA database, copy the previous valid snapshot and replace that source partition in private staging, or rebuild the assembled pack using cached per-source shards. Preserve duplicate-FDC-ID failure policy where appropriate and all missing/zero nutrient semantics.

Poll a small release descriptor weekly (daily around an expected release only as a configured optimization), download on version/hash change. SR Legacy is finalized, so bootstrap once and no routine data refresh; manual correction/reimport or very infrequent metadata audit remains possible. A source file can be corrected at the same URL: conditionally revalidate with headers/hash on the configured audit schedule, never assume URL immutability [S01].

## All The Places: output first, spiders second

Official code: `https://github.com/alltheplaces/alltheplaces`. API docs: `https://github.com/alltheplaces/alltheplaces/blob/master/API.md` [S02]. Candidate selected spider names from the prior/current source review include `walmart_us`, `aldi_sud_us`, `target_us`, `kroger_us`. Before enabling a descriptor, inspect that exact file in a pinned upstream checkout and source output metadata. The checked-in chain research is not an automatic allowlist.

The per-spider URL redirects to its latest successful non-empty run. Store the resolved URL, run ID, actual collection time when available, checksum and parser version. A new global run does not prove a particular spider succeeded. The same resolved output must not repeatedly advance `source_observed_at` or closure-absence counters.

Filter country and formats; retain main grocery locations while avoiding pharmacy/fuel department double-counts. Multi-banner spiders must be split into canonical banner/format records using explicit mapping. Prefer the exact retailer store URL from the output to constructing a slug. Publish measured coverage by source/banners, not “all USA supermarkets.”

Initially support a bounded, version-controlled set of descriptors. Adding a descriptor is a small reviewable operation. A later opt-in full ATP archive importer may discover candidate grocery banners across all outputs; it still must enforce country/type rules and create review candidates, not execute upstream spider code or crawl arbitrary output URLs.

## SNAP: do not substitute history for current authorization

The current locator provides CSV downloads; the historical page is a different dataset. The current official page was search-visible but direct fetching returned 403 during research, so this package intentionally does **not** invent a current CSV filename or ArcGIS item ID [S03].

Implement a landing/resource resolver plus a configured official-file override and a local-import path. If it cannot resolve the current resource under allowlisted policy, set `source_location_unresolved`, preserve other sources and expose the manual acquisition instructions. A user-supplied override needs host/schema/rights review; it is not an unrestricted URL-fetch API. Do not repeatedly scrape a blocked page or silently take the historical ZIP.

A SNAP authorization withdrawal changes SNAP evidence, not store-open status. Missing SNAP records do not prove a closed store. Retain authorization IDs/types when available and field-level evidence. Schema-key discovery is a controlled adapter mapping; unknown key changes fail quarantine rather than guessing which column is the address.

## Open Food Facts: baseline plus genuine bounded deltas

Primary baseline: official JSONL dump (parser compatible with source-shaped delta records). Optional Parquet from the official OFF account uses different nested/list structures and needs its own normalization adapter [S04–S05]. Import selected country tags plus explicitly requested/saved product identities; missing countries should produce a candidate or an on-demand retained record, not categorically reject a valid household product.

Index: `https://static.openfoodfacts.org/data/delta/index.txt`. Relative files use `openfoodfacts_products_<from_ts>_<to_ts>.json.gz`. Official exporter code uses `(from_ts, to_ts]` on `last_modified_t` and exports the active-products collection. It retains only a bounded number of recent delta files. The index response surfaced by the web tool in this review was old; **this is not a claim of current delta health**. At activation verify the feed’s actual timestamps and continuity [S06].

Handle delta ordering, duplicate intervals, gaps, stale feeds, parser version and baseline compatibility. Export deltas do not establish a complete tombstone/deletion feed or all automated recalculations. Run periodic full reconciliation (proposed 30 days) for deletion/obsolete-state and derived-field repair; sooner after a gap or stale baseline. Do not add an undocumented “since” API to make incrementality appear easy. No copying upstream MongoDB export shell scripts into Bòrd’s runtime.

Download optional images only for selected items after terms review; database metadata is not an instruction to mirror global image bytes. OFF database, contents, images and upstream code have distinct licenses [S05].

## Open Prices

Download related exports as one logical candidate release, recording individual hashes. Sources can finish exports at slightly different moments, so retry/quarantine missing foreign keys or preserve unresolved references; do not publish dangling location/proof relations as exact branch facts. Filter prices by resolved U.S. location, retaining required related records. Proof metadata can be retained according to policy; proof images are off by default. A new observation with an old purchase date remains an old price. Source editing/deletion needs revision reconciliation, not append-only assumptions [S07].

## FoodKeeper

The catalog lists JSON/XLS and irregular updates. Prefer English JSON, preserve storage conditions and guidance ranges, and resolve current HTTPS resources. Its old catalog download links use HTTP; never blindly downgrade TLS to make a download succeed. Mark unresolved if a current HTTPS artifact cannot be validated. Guidance does not automatically set a batch’s precise expiration or guarantee safety [S08].

## Overture and OSM extension

Use Overture’s release discovery and current `taxonomy`/`basic_category` schema, not stale `categories` examples. The documented catalog points to available releases; pin a release per job. U.S. extraction must include Alaska/Hawaii and apply explicit territory choices. Geospatial filter pushdown can reduce data transfer but is not a guarantee of a tiny scan. Preserve underlying source lineage to avoid counting ATP-derived records as independent evidence [S09].

IndoorEqual is a tool for OSM indoor data, not a collection of official Walmart/ALDI floor plans. Do not deploy its whole stack before measuring useful coverage. No global OSM import or public Overpass bulk loop in V1 [S10].

## Optional APIs and spending

USDA/ATP/SNAP/OFF/Open Prices/FoodKeeper source fees are $0 in the described public/open workflows; optional services have their own terms. Kroger is the first official retailer candidate for branch-specific product/aisle data, but account access, quotas, price/stock fields and monetary tariff remain activation checks. Walmart consumer maps or supplier inventory documentation do not grant arbitrary consumer-app bulk stock access. Instacart remains the existing Bòrd shopping-link handoff, not a catalog mirror. Public per-call tariffs for these retailer programs were not verified; use `unknown`, not `0`. [S12–S14]

No commercial account, API key discovery, proxy service or spend is required by this implementation prompt. Google Places, commercial scraper vendors and paid indoor-map licenses are deferred alternatives; the earlier registry’s cost notes are dated research only. Any later costed connector requires documented unit price, daily/monthly caps, storage rights and explicit account authorization before its source policy can be enabled.

## Expanding beyond selected spiders

See `docs/21-COVERAGE-GROWTH.md` for the V1 optional published-archive mode and automatic eligible-banner discovery. It avoids maintaining a hard-coded exhaustive chain list, but may require a large worldwide archive transfer. It never authorizes retailer crawling.
