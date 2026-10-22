# Setup and configuration

For the local V1 expansion, read [runtime, migration and activation controls](platform-runtime.md) first. V1 code has not been published or deployed by this implementation; existing published image tags may contain the earlier USDA service. `serve` now starts HTTP immediately; pair it with `worker` or use supervised `run`. Source networking and store-pack readiness are independent of USDA's legacy `AUTO_DOWNLOAD` flag.

Run Bòrd Food API beside Bòrd to serve a local snapshot of USDA FoodData Central. The published image is `ghcr.io/callum-baillie/bord-food-api:latest`, available for Linux AMD64 and ARM64. It contains the application only; your catalog and downloaded source files live in the persistent `/data` mount.

This guide covers [Unraid installation](#install-on-unraid), [Compose](#install-with-compose), [dataset selection](#choose-and-supply-datasets), [settings](#configuration-reference), [Bòrd](#connect-bòrd), [maintenance](#updates-and-backups), and [troubleshooting](#troubleshooting). See the [README API reference](../README.md#api) for endpoints and request limits.

## Install on Unraid

Use the Unraid container UI for the simplest installation. No Git checkout or local image build is required.

1. In the Unraid terminal, create a dedicated data directory and make it writable by the user used in this guide:

   ```sh
   mkdir -p /mnt/user/appdata/bord-food-api/imports
   chown -R 99:100 /mnt/user/appdata/bord-food-api
   ```

2. To supply your own datasets, copy the original USDA JSON ZIPs into that `imports` directory now. Otherwise leave it empty for automatic downloads.
3. Open **Docker → Add Container** and enter the following settings. Enable Advanced View to enter Extra Parameters.

   | Unraid setting | Value |
   | --- | --- |
   | Name | `bord-food-api` |
   | Repository | `ghcr.io/callum-baillie/bord-food-api:latest` |
   | Network Type | `bridge` for access through the Unraid host IP |
   | Port: host → container | `8081` → `8080`, TCP |
   | Path: host → container | `/mnt/user/appdata/bord-food-api` → `/data`, read/write |
   | Path: host → container | `/mnt/user/appdata/bord-food-api/imports` → `/imports`, read-only |
   | Extra Parameters | `--user=99:100` |
   | Variable `DATASETS` | `branded,foundation,fndds,sr_legacy` |
   | Variable `AUTO_DOWNLOAD` | `true` |
   | Variable `API_KEY` | Leave blank initially, or set your own shared key |

   Choose another host port if `8081` is already used. Keep the container port at `8080`. Leave privileged mode off.

4. Apply, then open the container logs. The first start downloads/imports data before opening the API port. Wait for `Catalog ready` and the server startup message. Later starts reuse the existing database.
5. From a computer on the same LAN, check the API, replacing `YOUR-UNRAID-IP` with the host's actual address:

   ```sh
   curl --fail http://YOUR-UNRAID-IP:8081/health
   ```

   Expect `status: ok` and a positive `totalFoods`. Open `http://YOUR-UNRAID-IP:8081/docs` for the interactive API documentation. Enable container autostart in Unraid if desired.
6. Follow [Connect Bòrd](#connect-bòrd) below.

Alternatively, copy the repository's [Unraid XML template](../unraid/bord-food-api.xml) to `/boot/config/plugins/dockerMan/templates-user/my-bord-food-api.xml` on Unraid, select it under **Add Container**, and review the same values before applying.

The container has been tested with Docker; these instructions do not establish that your Unraid host's mounts, permissions, or network have been verified. The health and Bòrd search checks below provide those checks on your installation.

## Install with Compose

Choose one deployment method for a container named `bord-food-api`; do not run both UI-managed and Compose-managed copies with that name.

### Unraid using the published image

On a host with Git and Docker Compose available:

```sh
git clone https://github.com/callum-baillie/bord-food-api.git
cd bord-food-api
cp .env.example .env
mkdir -p /mnt/user/appdata/bord-food-api/imports
chown -R 99:100 /mnt/user/appdata/bord-food-api
# Edit .env for the settings below, then start:
docker compose -f compose.unraid.yaml up -d
docker compose -f compose.unraid.yaml logs -f bord-food-api
```

[compose.unraid.yaml](../compose.unraid.yaml) uses the published image, host port `8081`, UID/GID `99:100`, and the same persistent host directories as the UI instructions. `.env` belongs beside the Compose file and is ignored by Git. Pressing Ctrl+C exits the log viewer without stopping the container.

### Build locally on another Docker host

From a checkout of this repository:

```sh
cp .env.example .env
mkdir -p imports
docker compose up -d --build
docker compose logs -f bord-food-api
```

[compose.yaml](../compose.yaml) builds the application locally, mounts `./imports` read-only, and uses a Docker-managed volume for `/data`. It does **not** mount this checkout's `./data` directory. Check `http://localhost:8081/health` on the Docker host. Keep the named volume: `docker compose down -v` deletes it.

After changing `.env`, run the same `up -d` command again to recreate the container with the new values. `docker restart` alone does not apply changed environment variables.

## Choose and supply datasets

**Recommended: all four JSON datasets.** This covers packaged foods and ordinary recipe ingredients while keeping the importer simple.

| `DATASETS` identifier | USDA dataset | Useful for |
| --- | --- | --- |
| `branded` | Branded Foods | Packaged products, brands, and barcodes |
| `foundation` | Foundation Foods | Generic ingredients with detailed nutrient data |
| `fndds` | Survey Foods (FNDDS) | Common foods and prepared dishes |
| `sr_legacy` | SR Legacy | Additional reference foods |

`DATASETS=branded` is supported when you only want packaged foods. Bòrd's **generic** search selects Foundation and FNDDS, so import those too if you want that filter to return results. An unfiltered API search can search all four types.

Automatic downloads discover the selected JSON ZIP releases from [USDA's download page](https://fdc.nal.usda.gov/download-datasets/). They require outbound internet access during download, but no USDA API key. Search and details use the local database afterward.

For manual input:

1. Download the separate **JSON** archives for the datasets you want. The combined **CSV** download is unsupported.
2. Place the ZIPs, or extracted JSON files, directly in the mounted import directory. Subdirectories are not scanned. Supply one release per dataset; a ZIP plus its extracted JSON would duplicate records and fail the import.
3. Set `AUTO_DOWNLOAD=false` if startup must use only your files.
4. Start a fresh installation, or run the explicit import command below for an existing installation.

Startup checks in this order:

1. An existing `/data/foods.sqlite` is validated and served immediately.
2. If no database exists, all `.json` and `.zip` files directly in `/imports` are imported.
3. If neither exists and `AUTO_DOWNLOAD=true`, the selected datasets are downloaded and imported. With `false`, startup fails until you supply files.

`DATASETS` controls downloads only; it does not filter supplied files. Changing it, adding files, or restarting does not replace an existing catalog. Each explicit import or refresh replaces the **entire** catalog, so include all datasets you want to keep.

Allow several GB of free disk space for source archives, the serving database, and a replacement database during updates. The initial verified four-dataset catalog contained 469,046 foods, used about 1.34 GiB for SQLite, and had about 212 MiB of compressed source files. Those are measurements of the original import, not guaranteed sizes or counts for later releases. Neither the Git repository nor the container image includes those files.

## Configuration reference

These values belong to the **food API container**, separate from Bòrd's variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Empty | Optional shared key. When nonempty, food and `/status` requests require the same value in `X-Api-Key`. |
| `DATASETS` | `branded,foundation,fndds,sr_legacy` | Comma-separated download selection; use the identifiers above. |
| `AUTO_DOWNLOAD` | `true` | Allow automatic download only when startup has neither a database nor import files. Use `true` or `false`. Explicit `refresh` still downloads with `false`. |
| `HOST_PORT` | `8081` | Compose setting for the host side of `HOST_PORT:8080`. In the Unraid UI, edit the port mapping instead. |
| `DATA_DIR` | `/data` in Docker; `./data` in Python | Directory containing `foods.sqlite`, import lock, and `downloads/`. Keep the Docker default and mount persistent storage there. |
| `IMPORT_DIR` | `/imports` in Docker; `./imports` in Python | Directory scanned for manual source files. Keep the Docker default and mount your input directory there. |
| `PORT` | `8080` | Server port inside the container. Keep this default with the supplied port mappings. |

The supplied Compose files pass `API_KEY`, `DATASETS`, and `AUTO_DOWNLOAD` from `.env`; they use `HOST_PORT` for port mapping. Advanced changes to `DATA_DIR`, `IMPORT_DIR`, or `PORT` require editing the service environment and corresponding mounts/ports, not just adding them to `.env`.

The image defaults to UID/GID `10001:10001`; the Unraid examples explicitly override this with `99:100`. There are no `PUID`/`PGID` settings. Bind-mounted storage must be writable by the selected user, and import files must be readable.

For optional authentication, set your chosen key as `API_KEY`, recreate the food API, and set the same value as `USDA_FDC_API_KEY` on Bòrd before recreating Bòrd. `/health`, `/docs`, and `/openapi.json` remain public. Shared-key authentication does not encrypt HTTP; use this service on your trusted LAN/Docker network.

Direct Python execution reads environment variables but does not automatically load `.env`. See [development instructions](../README.md#develop-and-verify) for dependencies and commands.

## Connect Bòrd

Add these **server environment variables to Bòrd**, not to the food API:

```dotenv
USDA_FDC_ENABLED=true
USDA_FDC_BASE_URL=http://YOUR-UNRAID-IP:8081/fdc/v1
USDA_FDC_API_KEY=local
```

Use `local` when food API authentication is disabled. Bòrd still needs a nonempty value to enable its USDA provider. If the food API has an `API_KEY`, use that value instead. A real USDA API key is unnecessary for this local connection.

On a shared user-defined Docker network, the URL can instead be `http://bord-food-api:8080/fdc/v1`. Separate Compose projects have separate default networks. `localhost` inside Bòrd points to Bòrd itself. Always include `/fdc/v1` in the base URL.

In Unraid, add the variables in Bòrd's Edit Container screen and Apply. For Compose, Bòrd's existing files do not pass `USDA_FDC_BASE_URL` through; use [the supplied override](../examples/bord.compose.override.yaml) or add it to the service's `environment` mapping. The [Bòrd local food API guide](https://github.com/callum-baillie/our-recipes/blob/main/docs/local-food-api.md) gives complete Bòrd-side instructions, connection checks, and troubleshooting.

The food API is called by Bòrd's server. Keep Bòrd's `APP_ORIGIN` and trusted origins set to its browser address. Open Food Facts remains a separate barcode provider and may still access the internet.

## Updates and backups

### Update the application

Use Unraid's container update action, or from this repository on a Compose-managed Unraid installation:

```sh
docker compose -f compose.unraid.yaml pull
docker compose -f compose.unraid.yaml up -d
```

For a local source build, pull the code and run `docker compose up -d --build`. Preserve the data mount. Application updates do not refresh USDA data.

### Refresh downloaded datasets

With the API container running:

```sh
docker exec bord-food-api python -m bord_food_api refresh
docker exec bord-food-api python -m bord_food_api status
```

This downloads the latest selected `DATASETS`, reuses verified cached archives when possible, and replaces the catalog. Add `--force-download` to `refresh` to fetch the archives again. If you changed `DATASETS`, recreate the container first so the command uses the new selection. There is no automatic refresh schedule; run this manually or schedule the command with Unraid User Scripts.

### Replace the catalog with supplied files

After copying files into the mounted import directory:

```sh
docker exec bord-food-api python -m bord_food_api import
# Or name every file you want in the replacement catalog:
docker exec bord-food-api python -m bord_food_api import /imports/branded.json /imports/foundation.json
docker exec bord-food-api python -m bord_food_api status
```

The CLI paths are paths **inside the container**. A successful update atomically publishes a new database. The running API can continue serving the previous catalog during the build; failed imports leave it in place. Two imports cannot run simultaneously. Check the exit status and source counts before considering an update complete.

When the container is stopped or repeatedly failing startup, `docker exec` is unavailable. For Compose-managed Unraid installations, fix the input/configuration, then run:

```sh
docker compose -f compose.unraid.yaml stop bord-food-api
docker compose -f compose.unraid.yaml run --rm --no-deps bord-food-api import
docker compose -f compose.unraid.yaml up -d
```

Use `refresh` instead of `import` in the one-off command if you want official downloads. For UI-managed installations, correcting missing files or permissions and starting again is sufficient when no database exists. Preserve an invalid existing database for diagnosis before explicitly rebuilding it; startup does not silently replace it.

### Preserve or move the catalog

The API's `/data` is separate from Bòrd's household database and is not included in Bòrd's backup bundles. To retain the exact dataset snapshot, stop the API and any import job, then copy its data directory to your backup destination. Copy manually supplied sources separately if they live outside that directory. Keep environment configuration/keys separately from source control.

To restore or move an installation, stop the destination container, copy the backed-up data directory's **contents** into its `/data` host directory, set the appropriate ownership, then start and check `/health` and `status`. Rebuilding from source ZIPs is also supported. Downloaded archives are retained under `/data/downloads`; older releases can be removed when no import is running if they are no longer needed for recovery.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Connection refused on first start | Follow `docker logs -f bord-food-api`. No HTTP listener exists until the first import completes. The image allows a 30-minute health-check startup period. |
| Permission denied writing `/data` | Check the actual mount and UID/GID. The Unraid examples require ownership `99:100`; the default image user is `10001:10001`. |
| `No source files found` | With `AUTO_DOWNLOAD=false`, supply JSON/ZIP files directly in the mapped imports directory. Check that the files are readable. |
| CSV or duplicate-ID import failure | Use individual JSON datasets and one release per dataset. Remove duplicate ZIP/extracted JSON inputs and repeat the import. |
| Download fails | Check outbound connectivity and free space; supplying original USDA JSON ZIPs manually is an alternative. Existing catalogs remain usable. |
| `401` from search or `/status` | Supply the configured `API_KEY` as `X-Api-Key`; Bòrd must use that same value. `/health` deliberately does not check the key. |
| Healthy API, but Bòrd cannot search | Verify Bòrd's environment reached its container, include `/fdc/v1`, and test connectivity from Bòrd. See the linked Bòrd guide. |
| Empty generic search | Confirm Foundation/FNDDS were imported. A branded-only catalog cannot satisfy Bòrd's generic filter. |
| New source files have no effect | Run `import`; restarts reuse an existing database. Include all desired datasets in the replacement. |
| Catalog unavailable or search returns `503` | Inspect logs, disk space, and catalog validity. Searches also have a five-second execution limit; try fewer terms. Rebuild from retained sources if the catalog is invalid. |

Useful checks for a running container:

```sh
docker logs --tail 100 bord-food-api
docker exec bord-food-api python -m bord_food_api status
curl --fail http://YOUR-UNRAID-IP:8081/health
curl --fail 'http://YOUR-UNRAID-IP:8081/fdc/v1/foods/search?query=oats&pageSize=1'
```

Add `-H 'X-Api-Key: YOUR-LOCAL-KEY'` to the search request if authentication is enabled. `status` prints dataset provenance and counts without requiring an HTTP key because it reads the local catalog directly.
