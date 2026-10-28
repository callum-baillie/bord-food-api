# Product images

Product images are an optional barcode-matched cache, separate from the immutable food catalog.
USDA nutrition, FDC IDs, units and source assertions are unchanged. The cache uses Open Food
Facts (OFF); enabling it does not enable or import the full OFF product adapter.

Tower's [published-image deployment and verification](investigations/product-images-publication-20261028/RESULTS.md)
records the committed revision, registry digest and live checks. Earlier pilot receipts remain
historical evidence.

## Requests

All three routes use the existing `X-Api-Key` authentication:

| Method | Route | Result |
| --- | --- | --- |
| GET | `/v1/product-images/{gtin}` | Local JPEG, or bounded acquisition on a cache miss |
| GET | `/v1/product-images/{gtin}/metadata` | Cached attribution, license, provenance and dimensions; never fetches |
| GET | `/v1/product-images/status` | Activation, cached image count, bytes and durable acquisition budgets |

UPC/EAN/GTIN inputs must pass check-digit validation and are normalized to GTIN-14 for matching.
The source's own barcode spelling determines its image directory. Matching uses the exact GTIN;
product names are never used to guess an image.

A request first checks local bytes and their SHA-256. On a miss it tries imported selected-front
references from the public OFF bulk mirror, with the OFF image CDN as an alternative. If those
references are absent or unavailable and API fallback is enabled, it asks OFF for current product
image metadata, validates the returned barcode, downloads the selected front photo and saves it.
It does not choose the first uploaded photo, which could be a nutrition label.

The response has an ETag, supports `If-None-Match`/304, and includes attribution and license links.
Metadata records the source URL, product page, revision, retrieval time and manifest provenance
or API acquisition. Images are decoded, bounded, oriented, stripped of metadata and stored as
JPEGs up to 600 pixels. The mirror's selected original-photo thumbnail may include more background
than OFF's cropped front image.

Missing products/front images return 404 and are cached for one day by default. Temporary source
failures, concurrency, budget limits and throttling return 503 with `Retry-After`; rights blocks
return 403. Concurrent acquisition fails quickly while local hits remain available. Upstream
timeouts are bounded, but a cold lookup involves multiple requests: **do not reuse the catalog
client's five-second timeout for image acquisition**. Live successful cold requests took 1.77
and 6.55 seconds. Show a placeholder, allow a longer image request, and honor retry responses.

## Configuration and storage

Merge this section into the external JSON policy selected by `BORD_FOOD_CONFIG`, preserving the
rest of that policy:

```json
{
  "product_images": {
    "enabled": true,
    "api_fallback": true,
    "cache_quota_bytes": 1073741824,
    "free_space_reserve_bytes": 5368709120,
    "api_daily_limit": 500,
    "asset_daily_limit": 10000
  }
}
```

Both flags default to false. Network acquisition additionally requires `network.mode=bulk_only`;
offline mode can serve already cached images. The existing OFF display-rights revocation blocks
image reads and acquisition. Optional provider keys are not needed. Pillow is the only new
application dependency. Recreate a container after replacing its single-file policy bind mount.

Storage is `${DATA_DIR}/product-images/`: a mutable cache index, an atomically replaced reference
index, and content-addressed JPEG objects. These are independent of catalog publication. Back up
this directory separately if images must survive restoration. The cache stops acquiring at its
quota or free-space reserve; it does not evict images or alter the serving catalog to make room.

OFF product metadata calls are paced at one per five seconds, with a default 500/day cap; image
requests have separate durable per-provider pacing and daily budgets. HTTP 429/503 responses
extend the shared cooldown. These gates persist across processes and restarts.

## Explicit bulk acquisition

OFF publishes an [organized, public image collection on AWS](https://openfoodfacts.github.io/openfoodfacts-server/api/aws-images-dataset/).
Barcode paths and selected image IDs from a retained OFF export let us download the relevant
400-pixel images without one product API call per food. The mirror updates monthly; recent images
can be absent. We fetch selected front images rather than copying the entire global collection,
its duplicate uploads, labels and OCR files.

Run the helper in an environment with the same data directory and external policy as the service:

```sh
python scripts/cache-product-images.py --manifest /imports/off-selected-products.json --limit 100
python scripts/cache-product-images.py --manifest /imports/off-selected-products.json \
  --limit 100 --max-seconds 600 --apply
```

The first command prints a plan. Supported inputs are an OFF product array, `{ "products": [...] }`
JSON, or streaming JSONL (optionally gzip). Use a barcode-filtered manifest for the desired catalog
subset. Manifest publication replaces the image reference index atomically; a failed import keeps
its predecessor. Positive cached images remain. The duration bound applies to image acquisition,
not the preceding streamed reference import or manifest hashing.

Bulk acquisition **does not call the product API by default**, even when runtime fallback is on.
Add `--api-fallback` explicitly to allow it, or supply repeated `--gtin` arguments to target specific
barcodes. Bulk requests are serial, with bounded count/duration and persistent budgets. A completed
run can contain deferred or missing items; inspect the JSONL summary before claiming success.

## Consumer integration and licenses

The current Bòrd native catalog client still returns `images: []`. These image routes are enabled
on the API, but adding visible photos in Bòrd requires consuming them through an authenticated
server-side proxy. Keep the API key on the server; never put it in an image URL or browser bundle.
Do not assume a photo exists just because a USDA product exists.

OFF images carry [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) attribution and
share-alike obligations. Preserve the provided source/attribution/license and disclose the JPEG
transformation when displaying or redistributing these derivatives. OFF database licensing is
separate. Other providers are researched in the [live investigation](investigations/product-images-20261027/RESULTS.md);
their public image URLs do not automatically grant bulk redistribution rights.
