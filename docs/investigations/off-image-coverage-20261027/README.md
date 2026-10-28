# Open Food Facts image coverage — 27 October 2026

The Open Food Facts product record includes a barcode (`code`) and image metadata. Match
normalized barcodes across sources, then use OFF's own image references/URLs and original
code/path rules rather than inventing a filename from a USDA food name.

OFF publishes a separate image collection in the public `openfoodfacts-images` AWS S3 bucket,
with an object inventory at `data/data_keys.gz`. An AWS account is not required. The collection
is synchronized monthly, so the newest image metadata may precede its appearance in that
mirror. Product images use CC BY-SA; database metadata uses ODbL. See URLs in `coverage.json`.

Live read-only Unraid inspection found the retained OFF product JSONL gzip:
13,179,356,850 bytes, downloaded 18 October 2026. It contains metadata, not the image files.
The food API's appdata had no JPEG/PNG/WebP files or image archives; its `objects/media`
directory does not exist. No image download, source activation, service restart or catalog
publication was performed for this investigation.

## Downloadable-table coverage

The OFF-maintained Hugging Face food table at revision
`89cfb571db20b1f1b246f27cab71837fc96225b1` (updated 27 October, 09:07:24 UTC) contains
**2,117,571 food records**. Across all 2,068 row groups, the image-key statistics indicate
**1,810,935 records with image metadata**, or **85.5194% (about 85.5%)**. The remainder is
306,636 records. Historical upload timestamps/max-image IDs produce slightly different
counts (1,811,438 / 1,811,074); all three metrics round to 85.5%.

Method: two validated HTTP range requests obtained the pinned Parquet footer (45.6 MB),
not the entire 4.3 GB table. Summed `row_group.num_rows - image_key.statistics.null_count`
for `images.list.element.key`, and cross-checked against `last_image_t` and `max_imgid`.
Every row group supplies null-count statistics. Missing/empty image lists contribute a
null marker to the image-key column; image entries carry their keys. This is a metadata
coverage estimate, not an image-availability audit. The full table was not downloaded.
The footer is retained in gitignored `data/off-image-coverage-20261027/` with a SHA-256
in the JSON receipt. The inspection dependency was installed only in a temporary directory;
application dependencies were unchanged.

This is **any-image** coverage, not a count of usable front-of-pack photos, current AWS
objects, U.S.-only foods, unique validated GTINs, or images matching the USDA catalog. It is
also a newer/different snapshot from the product JSONL retained on Unraid. None of those
other percentages has been inferred from this number.

OFF's live search count returned HTTP 503; its web pages were inaccessible to the web tool.
Hugging Face's precomputed statistics returned HTTP 500 and its filter request timed out.
The complete downloadable-table footer provided the independent count above. A bounded
5,000-record read of the retained JSONL confirmed the barcode/new image metadata structure;
that ordered prefix was not used as a representative coverage sample.
