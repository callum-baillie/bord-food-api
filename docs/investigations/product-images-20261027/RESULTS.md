# Product image acquisition — 27 October 2026 CDT

The Unraid food API now serves a local product-image cache with a paced Open Food Facts (OFF)
API fallback. Activation was at **2026-10-28 04:00:20 UTC** (27 October locally). This is a small
verified acquisition batch, not a complete download of all OFF or US product photos.

## Measured results

| Check | Result | Evidence |
| --- | --- | --- |
| Bulk acquisition from OFF's public AWS mirror | 39/39 selected images; 824,457 JPEG bytes; 125.18 seconds; 39 asset requests, **zero product API calls** | `bulk-result.json` |
| Barcode deliberately omitted from the bulk reference index | One product API call and one image download; 6,549.64 ms first lookup, 4.03 ms local repeat; zero repeat network calls | `fallback-result.json` |
| Live Aldi Happy Farms image, UPC/EAN `4099100013566` | HTTP 200 JPEG; 1,769.95 ms cold, 7.00 ms cached; 304 on ETag; zero repeat network calls | `live-verification.json` |
| Final cache after verification | **41 images, 879,362 bytes**; two total product API calls, 41 AWS requests | `live-verification.json` |
| Existing food catalog | 469,046 foods; generation `g_3d03aef2ba8745718bde0e9dac73fc13`; pointer byte-for-byte unchanged | `deployment.json`, `checks.json` |
| Existing two Aldi product-name resolutions | Exact matches in 27.33 ms total | `live-verification.json` |
| Live service/auth checks | API, Bòrd and history healthy; no OOM; keyed images 200, missing key 401, invalid GTIN 422; metadata/license/hash checks and trusted HTTPS health passed | `live-verification.json`, `checks.json` |
| Offline regression | **464 tests passed**, Ruff passed, OpenAPI matches; one upstream Starlette deprecation warning | `checks.json` |
| Actual dependency image smoke | Synthetic JPEG + authenticated HTTP, network disabled, exited 0 | `preflight-result.json` |

The visible Aldi photo was inspected: it is the Happy Farms sharp cheddar package. OFF marks the
selected source photo as the front; the raw 400px derivative also includes countertop background.
The repeat measurements through Bòrd's container include HTTP overhead; the standalone cache
measurement does not. Cold requests can exceed five seconds and need a separate image timeout.

The 39 bulk targets came from an ordered prefix of the retained OFF export, filtered to existing
USDA barcodes with selected front metadata. One of the 40 selected records was held back for the
fallback test. This selection is **not a representative image-coverage sample**. The earlier
[85.5% metadata finding](../off-image-coverage-20261027/README.md) concerns any-image metadata in a
different, pinned OFF snapshot; it does not establish front-image coverage of the USDA catalog.

## Storage, activation and rollback

- Cache: `/mnt/cache/appdata/bord-food-api/product-images/`; 1 GiB image quota and 5 GiB free-space
  reserve. No bulk job remains running. The full global image collection was not downloaded.
- Existing 13,179,356,850-byte OFF product export remains under `/data/downloads/open_food_facts/`.
  Its image references are not themselves image files. The full OFF product adapter remains off.
- Image: `bord-food-api:product-images-036f99434082`, installed ID
  `sha256:c15bfcb134ee621c0d45f8c849ec52ba1dff7622ad8758e945fed9dd962b2305`.
  It derives from the prior pinned `f177b5e` base and adds Pillow 13.0.0; no registry push occurred.
- Read-only application mount:
  `config/product-image-releases/036f9943408260d193fdfaca74fed2e65ad753019143afb103544effb900dc33/bord_food_api`.
  It copies the actual live module tree, including the intervening logging repair, and changes only
  `api.py`, `settings.py`, plus the two new image modules. Installed hashes match `release.json`.
- Only `bord-food-api` was recreated. Bòrd/history image IDs and start times match this task's
  `before-containers.json`. Their earlier independent deployments are preserved.
- Protected pre-change Compose/policy backup:
  `/mnt/cache/backups/bord-food-api/20261027-product-images/`. Restore only the API service block
  and `product_images` policy section if rolling back later; do not overwrite unrelated changes
  made since this backup. Recreate only the API. The separate cache can remain.
- Source and live Compose changed only the API image/module mount. Policy comparison proves the
  only semantic policy change is `product_images`. USDA/source settings, keys and catalogs remain.
- Standard Tower audit was attempted before changes in an isolated copy; DevBox `192.168.0.30`
  was unreachable. Canonical inventory was preserved. Tower repository validation passed with
  existing ignored generated-output and sensitive-archive findings.

Bòrd's current native client still produces `images: []`; no Bòrd application source or UI was
changed. The new authenticated image endpoint is ready for a server-side consumer/proxy. Visible
photos in the Bòrd interface are not claimed. See [integration and bulk commands](../../PRODUCT-IMAGES.md).

## Other sources investigated

| Source | Barcode matching / access | Bulk images and suitability |
| --- | --- | --- |
| [Open Food Facts AWS collection](https://openfoodfacts.github.io/openfoodfacts-server/api/aws-images-dataset/) | Public HTTP/S3, no key; barcode directory + selected image ID from product metadata | Organized originals, 400px derivatives and OCR; monthly mirror may lag. Best verified source for this implementation. [AWS registry/license](https://registry.opendata.aws/openfoodfacts-images/). |
| [UPCitemdb free API](https://www.upcitemdb.com/wp/docs/main/development/plan/) | No signup/key; 100 combined requests/day, six lookups/minute, sustained one per ten seconds; image URLs in lookup responses | Useful small secondary lookup, not an open bulk image collection. A live lookup for Aldi `4099100013566` found the item but returned no image URLs. [Third-party image rights remain with their owners](https://www.upcitemdb.com/terms); not enabled for automatic caching. |
| [Datakick / GTINsearch](https://gtinsearch.org/download) | Downloadable CSV of 6,561 GTIN-14 items, CC0 metadata | Small organized supplement. Its download page explicitly reserves images to their respective copyright owners; not a generally reusable photo archive. |
| [FoodRepo API v3](https://github.com/digitalepidemiologylab/foodrepo_api/blob/master/v3/README.md) | Barcode and images, but an account/API key is required | [Historical Swiss open dataset](https://pmc.ncbi.nlm.nih.gov/articles/PMC6040205/) includes images. Current service/bulk freshness and US overlap were not verified; no deployment. |
| [HoloSelecta](https://data.mendeley.com/datasets/gz39ggf35n/1) | Downloadable 2020 research collection with GTIN annotations, CC BY 4.0 | Real organized image dataset, but vending-machine/research scope rather than a broad current US grocery catalog. No deployment. |

No verified source establishes complete coverage of all US foods, Aldi, Walmart or any store's
current inventory. A valid barcode/product-name match can still have no photo. OFF image
attribution, source links, license and transformation details are preserved separately from USDA
nutritional provenance; these images are not presented as USDA photography.
