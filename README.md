# Bòrd Food API

V1 expansion code now includes empty startup, a durable bulk worker, native store/product APIs and optional source adapters. See [runtime and migration controls](docs/platform-runtime.md), [native OpenAPI](contracts/openapi.json), [Bòrd handoff](contracts/BORD-HANDOFF.md), [V1 verification](docs/V1-VERIFICATION.md), and the separately authorized [Tower deployment](docs/TOWER-DEPLOYMENT.md). Verify the installed image revision when updating.

A small, self-hosted USDA FoodData Central API for Bòrd. One Python container, one SQLite database, no separate database server. Search and food details stay local after the initial import.

Container image: **`ghcr.io/callum-baillie/bord-food-api:latest`** (Linux AMD64 and ARM64).

Start with the [setup and configuration guide](docs/setup-and-configuration.md) for step-by-step Unraid/Compose installation, a complete settings reference, dataset imports, Bòrd connection settings, updates, and troubleshooting.

GitHub Actions runs the tests and Docker smoke test before publishing each push to `main`. Images are tagged `latest` and `sha-<full-commit>`; pushing a `v*` Git tag also publishes that version tag. Pull requests run checks without publishing. The container contains the application; datasets are downloaded/imported into its persistent data volume at runtime.

## Dataset choice

**Recommended: all four JSON datasets.** Branded supplies packaged foods and barcodes; Foundation, FNDDS, and SR Legacy add ordinary ingredients and prepared foods. The default is `DATASETS=branded,foundation,fndds,sr_legacy`. Set `DATASETS=branded` for packaged foods only.

Use the individual **JSON ZIPs** from [USDA's download page](https://fdc.nal.usda.gov/download-datasets/). You can download them yourself or let the container discover the newest releases. A USDA API key is not needed for these public downloads. The full CSV archive is deliberately unsupported to keep the importer small.

The releases available when this project was built (Foundation/Branded April 2026, FNDDS October 2024, SR Legacy April 2018) total about 212 MiB compressed. The importer streams directly from ZIPs and stores compressed food records plus a search index. Allow several GB of free disk for downloads, the database, and a second database during updates. It never loads a whole dataset into memory.

## Quick start

```sh
cp .env.example .env
mkdir -p imports
docker compose up -d --build
docker compose logs -f bord-food-api
```

On first start, the container imports every `.json` / `.zip` file directly inside `imports/` if any exist. Otherwise it downloads the selected datasets when `AUTO_DOWNLOAD=true`. It builds the catalog before opening port 8080; allow time for the first import. Look for `Catalog ready` in the logs.

The API is published at `http://localhost:8081`. Check it with:

```sh
curl http://localhost:8081/health
curl 'http://localhost:8081/fdc/v1/foods/search?query=oats'
```

The default Compose file stores the database and downloaded ZIPs in a persistent Docker volume. Restarts reuse the database immediately and do not download again. Avoid `docker compose down -v` unless you intend to delete that volume.

## Supply your own files

Put one or more original USDA JSON ZIPs, or their extracted JSON files, in `imports/` **before first startup**. Do not provide both a ZIP and its extracted JSON, or multiple releases of the same dataset: duplicate FDC IDs intentionally abort the import.

Set `AUTO_DOWNLOAD=false` to require local input and prevent automatic downloads at first startup. Files may use the USDA `BrandedFoods`, `FoundationFoods`, `SurveyFoods`, and `SRLegacyFoods` wrappers, or a plain array of complete USDA food records. CSV files are not supported.

`DATASETS` controls downloads only. All supplied files are imported regardless of that setting. Adding files to an existing installation does not automatically change its catalog; run the import command below.

## Connect Bòrd

Set these **server/container environment variables on Bòrd**, then recreate its container (or restart the local development server):

```dotenv
USDA_FDC_ENABLED=true
USDA_FDC_BASE_URL=http://YOUR-UNRAID-IP:8081/fdc/v1
USDA_FDC_API_KEY=local
```

`USDA_FDC_API_KEY` must be nonempty because Bòrd uses it to enable the provider. With this service's authentication disabled, `local` is just a placeholder. If you set `API_KEY` on this service, use that same value for Bòrd's `USDA_FDC_API_KEY`. No real USDA key is involved.

If both containers share a user-defined Docker network, use `http://bord-food-api:8080/fdc/v1` instead. The host-published port is 8081; the container port is 8080. `localhost` inside the Bòrd container refers to Bòrd itself.

Bòrd already reads `USDA_FDC_BASE_URL`; no provider code change is needed. Its existing Compose files do not pass this variable through, so adding it only to Bòrd's `.env` is insufficient. Either add it to Bòrd's `environment:` section or use [the supplied Compose override](examples/bord.compose.override.yaml):

```sh
# Run in your Bòrd source directory. Set the actual reachable server address.
LOCAL_FOOD_API_URL=http://YOUR-UNRAID-IP:8081/fdc/v1 \
  docker compose -f docker-compose.yml \
  -f ../bord-food-api/examples/bord.compose.override.yaml up -d bord
```

For Unraid, add the variables directly in Bòrd's Edit Container screen. This project does not change your existing Bòrd configuration. Bòrd still applies its own cache and default 900-request/hour budget, and still tries Open Food Facts first for barcodes. Its explicit USDA name search and USDA barcode fallback use this local service.

## Unraid

Pull the published image on your Unraid host:

```sh
docker pull ghcr.io/callum-baillie/bord-food-api:latest
mkdir -p /mnt/user/appdata/bord-food-api/imports
chown -R 99:100 /mnt/user/appdata/bord-food-api
```

Then either run:

```sh
docker compose -f compose.unraid.yaml up -d
```

Or add a container through the Unraid UI using these values (a [user template](unraid/bord-food-api.xml) is included):

| Setting | Value |
| --- | --- |
| Repository | `ghcr.io/callum-baillie/bord-food-api:latest` |
| Network | Bridge, or the same custom Docker network as Bòrd |
| Host port → container port | `8081` → `8080` TCP |
| Host path → container path | `/mnt/user/appdata/bord-food-api` → `/data` (read/write) |
| Import path → container path | `/mnt/user/appdata/bord-food-api/imports` → `/imports` (read-only) |
| Extra parameters | `--user=99:100` |
| `DATASETS` | `branded,foundation,fndds,sr_legacy` |
| `AUTO_DOWNLOAD` | `true` or `false` |
| `API_KEY` | Blank, or a shared local secret |
| `LOG_LEVEL` | `debug`, `info` (default), `warning`, `error` or `silent` |
| `LOG_FORMAT` | `json` (default) or `text` |

The image runs as UID/GID 10001 by default. The Unraid examples use UID 99/GID 100; make the data directory writable by that user. No privileged mode is required. For the UI template, copy the XML to `/boot/config/plugins/dockerMan/templates-user/my-bord-food-api.xml`, then select it under Add Container. Configure autostart in Unraid as usual.

To update the application with Compose, run `docker compose -f compose.unraid.yaml pull` followed by `docker compose -f compose.unraid.yaml up -d`. Updating the application image preserves the catalog; use the refresh command below when you want newer USDA data.

The service is intended for your LAN/Docker network. Setting `API_KEY` enables shared-key authentication immediately; HTTP itself does not encrypt traffic.

### Logs

Every log line is one JSON object (`time`, `level`, `service`, `component`, `msg`, `role` plus fields): debug and info on stdout, warnings and errors on stderr. `docker logs` and Dozzle read that stream directly, and Dozzle can filter on `level`. Requests that return 4xx are logged as warnings and 5xx as errors (path and status only, never the query string, so API keys stay out of the logs); successful requests and the `/live` probe appear only at `LOG_LEVEL=debug`. Credentials in messages or fields are redacted.

### Reuse the already verified catalog

The original development checkout has a complete, gitignored catalog at `data/foods.sqlite` and the four official ZIPs under `data/downloads/` (469,046 foods; database about 1.34 GiB). **Fresh Git clones and container images do not include this data.** If you have that catalog, copy the **contents** of `data/` into `/mnt/user/appdata/bord-food-api/` before starting the container, then apply the ownership command above. Startup will use the existing catalog immediately. The normal local Compose file uses a separate named Docker volume and will download/import its own catalog unless you seed that volume yourself.

## Update or rebuild the catalog

Download the latest selected releases and replace the catalog:

```sh
docker exec bord-food-api python -m bord_food_api refresh
```

Verified downloads are reused when their release URL and stored checksum match. Use `refresh --force-download` to fetch them again. Older ZIP releases are retained under `/data/downloads`; remove old archives manually if disk space is needed.

Replace the catalog using files in the mounted import directory:

```sh
docker exec bord-food-api python -m bord_food_api import
# Or select specific files:
docker exec bord-food-api python -m bord_food_api import /imports/branded.json /imports/foundation.json
```

Each import **replaces the whole catalog**. Include every dataset you want to keep. The running API continues serving its previous database while the replacement is built. A parse/validation failure, duplicate FDC ID, or failed download leaves the previous database in place. A lock prevents two importers from writing simultaneously. Successful publication uses an atomic rename; subsequent requests see the replacement. USDA's null array placeholders are skipped and counted as `skippedNulls` in source metadata; malformed non-null records abort the import.

There is no background refresh scheduler. Run the refresh command manually or from Unraid User Scripts on your preferred schedule. Source filenames, SHA-256 hashes, download URLs when known, record counts, and import time are available from `/status`. Imports preserve published USDA nutrient values and units; this service does not calculate missing values or make per-serving conversions.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Readiness and total food count; no key required |
| GET | `/status` | Dataset counts and import provenance |
| POST | `/fdc/v1/foods/search` | USDA-shaped search used by Bòrd |
| GET | `/fdc/v1/foods/search?query=oats` | Convenient query-string search |
| GET | `/fdc/v1/food/{fdcId}` | Full imported food detail |
| GET | `/docs`, `/openapi.json` | Interactive documentation and API schema |

```sh
curl http://localhost:8081/fdc/v1/foods/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"rolled oats","pageSize":20,"pageNumber":1,"dataType":["Branded"]}'
```

When authentication is enabled, add `-H 'X-Api-Key: YOUR-LOCAL-KEY'` to food and status requests. Authentication uses this header only. Keys and search text are not written to access logs. `/health`, API documentation, and the OpenAPI schema remain public.

Supported `dataType` values: `Branded`, `Foundation`, `Survey (FNDDS)`, `SR Legacy`. Omit the filter to search all imported types. GET requests use repeated `dataType` parameters. `pageSize` is 1–200 (default 20), `pageNumber` is 1–10000, and query text is limited to 200 characters/20 whitespace-separated terms. Requests over 16 KiB are rejected.

Search uses word prefixes across descriptions, brands, and categories, with all terms required. Numeric queries of 8–14 digits perform exact barcode lookup with leading-zero normalization and newest publications first. Missing nutrient amounts remain missing; zero remains zero. Search results use USDA's flattened nutrient shape, while details retain nested nutrient records. Branded/FNDDS category fields are also exposed as `foodCategory` for Bòrd compatibility.

This implements the search/detail subset Bòrd needs, not every USDA API endpoint or USDA's exact ranking algorithm. It serves the imported release snapshot; it does not proxy live USDA requests. Unknown food IDs return 404, invalid input returns 422, and an unavailable catalog returns 503. Search queries have a five-second database execution limit.

## Develop and verify

Python 3.12+ on Linux (SQLite FTS5 is required):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
# Build and exercise the actual container with synthetic food data:
.venv/bin/python scripts/smoke-docker.py
```

Run without Docker:

```sh
DATA_DIR=./data IMPORT_DIR=./imports .venv/bin/python -m bord_food_api run
```

`serve` starts HTTP without acquisition; `worker` runs acquisition separately, and `run` supervises both. Local Python execution reads environment variables, not `.env` automatically. Compose reads `.env`. Routine tests use synthetic food fixtures and mocked downloads. See [VERIFICATION.md](VERIFICATION.md) for the actual Docker, real-dataset, and Bòrd compatibility checks performed for this version.

To exercise Bòrd's actual TypeScript provider against a running service, from this project directory (with Bòrd checked out beside it):

```sh
BORD_SOURCE_DIR=../our-recipes \
  USDA_FDC_BASE_URL=http://localhost:8081/fdc/v1 \
  ../our-recipes/node_modules/.bin/tsx --tsconfig ../our-recipes/tsconfig.json scripts/verify-bord.mts
```

Set `USDA_FDC_API_KEY` to the shared key if authentication is enabled. This script uses local HTTP and the real Bòrd provider; it does not modify Bòrd or call USDA's live API.

## Data attribution

U.S. Department of Agriculture, Agricultural Research Service. FoodData Central. [fdc.nal.usda.gov](https://fdc.nal.usda.gov/). USDA publishes the data under [CC0 1.0/public domain](https://fdc.nal.usda.gov/api-guide/). Source release information is retained in each catalog's metadata.

Iowa store discovery and reconciliation: [operator guide](docs/IOWA-DISCOVERY.md), including SNAP/OSM provenance, coverage limits and repeatable incremental publication.


Store-field enrichment and operator browsing are documented in [docs/STORE-ENRICHMENT.md](docs/STORE-ENRICHMENT.md).

Repeatable phone/hours repair, official-site discovery and pilot gates are documented in
[docs/STORE-CONTACT-IMPROVEMENTS.md](docs/STORE-CONTACT-IMPROVEMENTS.md).

The explicitly activated, serial smaller-state campaign is documented in
[docs/SMALL-STATE-SCANS.md](docs/SMALL-STATE-SCANS.md), including the source-based ranking,
state qualification passes, shared pacing/budget and durable resume behavior.
The retained-data workflow preserves independent assertions, conflicts, closure uncertainty and
source clocks, and atomically publishes a replacement stores pack. It makes no source or model
requests. [Retail dataset/API discovery](docs/RETAIL-DATA-DISCOVERY.md) distinguishes product
reference data from branch inventory and records research-only connector options.

Iowa field refresh and live pilot/run policy: [operator guide](docs/IOWA-FIELD-CRAWL.md).

Repeatable chain profiles, deterministic identity/address repair and optional bounded OpenAI review: [operator guide](docs/STORE-QUALITY-PROFILES.md).

### Food assistance

Food banks, public pantries, meal programs and mobile distributions have separate optional
reference packs and generation-bound search routes. OSM attribution stays separate from
permissive/authorized directories. [Food assistance integration](docs/FOOD-ASSISTANCE.md)
describes automatic updates, the post-supermarket enrichment worker, source audits and the
remaining licensing/companion boundaries.
