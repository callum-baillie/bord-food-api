# Verification — 2026-10-16

Verified locally on Linux with Docker 29.8.1 and Docker Compose 5.5.1. The image uses Python 3.12; the local test environment uses Python 3.14.7.

## Automated checks

- `python -m pytest -q`: **34 passed**. Coverage includes real USDA JSON wrapper shapes, ZIP streaming, null placeholders, nutrient zero/missing semantics, exact GTIN matching, publication-date ordering, input validation, optional API-key authentication, concurrent requests, download caching/checksums, failed imports, writer locking, atomic replacement, and startup persistence.
- `ruff check .` and `ruff format --check .`: passed.
- `python scripts/smoke-docker.py`: built the image and passed container startup, search, detail, authentication, failed-import preservation, live catalog replacement, and persisted restart checks using synthetic records.
- Both Compose files validate. The Bòrd override validates when combined with Bòrd's Unraid Compose file. The Unraid XML parses.
- The Python test run emits one upstream Starlette warning about its HTTPX test-client integration; all tests pass.

## Official dataset import

Downloaded the current JSON archives directly from [USDA](https://fdc.nal.usda.gov/download-datasets/), streamed all four into SQLite, built the FTS5 index, and passed SQLite `quick_check` before publication.

| Dataset | Download release | Imported food records |
| --- | --- | ---: |
| Branded | 2026-04-30 | 455,458 |
| Foundation | 2026-04-30 | 363 |
| FNDDS | 2024-10-31 | 5,432 |
| SR Legacy | 2018-04 | 7,793 |
| **Total** | | **469,046** |

Foundation's 32 trailing null placeholders were counted and skipped. All non-null food records were validated. Raw USDA publication dates use `M/D/YYYY`; barcode sorting interprets these dates without altering the original detail fields.

The database is **1,442,578,432 bytes (about 1.34 GiB)**. Compressed downloads total about 212 MiB. This machine took about eight minutes to import/index all datasets. The import process was observed around 70 MiB RSS during sampling; this is not a measured peak or a hardware-independent requirement.

The verified database is retained in `data/foods.sqlite`, with original archives and source manifests in `data/downloads/`. These files are gitignored. Full source hashes and import provenance are in the database and `.verification/results.json`.

## Real Bòrd provider and Docker runtime

Served the complete database using the built `bord-food-api:local` container, mounted read-only. Docker's healthcheck reported **healthy**, and `/health` returned 469,046 foods.

Ran `scripts/verify-bord.mts` through the adjacent Bòrd repository's `tsx` and `tsconfig.json`. It imported Bòrd's actual `UsdaFoodDataProvider` and made local HTTP requests:

- Generic oats search: 7 normalized records.
- Selected generic detail: 20 recognized nutrient values.
- Branded oats search: 20 normalized records.
- Exact barcode lookup: matched the selected product's canonical GTIN.

The container reported about 46.8 MiB memory usage after these requests. This is a smoke-test observation, not a load benchmark. The test containers were removed after verification. The local image remains available.

## Deployment boundary

The initial checks above used a locally built image. GitHub Actions now defines testing and image publication to `ghcr.io/callum-baillie/bord-food-api`; run results are available on the repository's Actions page. No container has been deployed to the user's Unraid host. Actual Unraid networking, storage permissions, and the deployed Bòrd instance still need verification on that host.
