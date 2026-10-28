# Barcode resolver repair — 27 October 2026

Fixed and verified on the running Unraid API. Bòrd’s live barcode requests now succeed within its existing five-second timeout.

## Cause and repair

A request from the running Bòrd container to `POST /v1/products/resolve` failed after roughly
5.4 seconds. The serving traceback ended in `sqlite3.OperationalError: interrupted` inside
`Platform.iter_records`. The resolver decoded every product to look for identifiers; the active
pack contains 455,458 USDA branded assertions. SQLite's five-second progress-handler deadline
was not converted to the native JSON error contract.

The repair adds a pack-local `product_identifiers` table keyed by namespace, normalized value,
chain and product. Imports rebuild it in private pack copies. Exact GTINs, chain-scoped SKUs
and PLUs return only matching assertions; multiple products sharing a barcode remain separate
candidates. Generation binding, source restrictions, redirects and identifier validation are
preserved. Query failures return retryable JSON 503 responses without SQL details. Older packs
return `PRODUCT_INDEX_NOT_READY` until the explicit offline maintenance command runs:

```sh
python -m bord_food_api catalog reindex-products
```

Maintenance copies and seals a replacement pack, then atomically publishes it without changing
entity payloads, revisions, provenance, source checkpoints/check times or other packs. It is
idempotent. Publication interruption and recovery are covered by regression tests.

The real-catalog rehearsal also caught SQLite choosing an entity-ID walk for an ordinary INNER
JOIN to avoid sorting. Both operations appeared as `SEARCH` in EXPLAIN, despite processing all
product IDs. The final CROSS JOIN forces the selective identifier lookup first, followed by
point lookups on `(kind,id)`. The test checks these keys and join order, not just absence of a
literal `SCAN` plan. A real one-key comparison measured about 277 ms versus 0.10 ms; see
`query-plan-before.txt`.

## Completed verification

- `python -m pytest`: 453 passed, one upstream Starlette/httpx deprecation warning.
- `ruff check .`, changed-file format checks and OpenAPI contract comparison passed.
- Installed pinned Python 3.12 image, network disabled, read-only production source mount,
  UID/GID 99:100, 2 GiB limit: full-catalog index build and SQLite integrity checks passed.
- All 455,458 complete entity rows were directly compared before/after indexing; unchanged.
  The index contains 443,350 product/identifier associations.
- Final real-image HTTP rehearsal: five batches containing known Aldi barcodes, a confirmed
  absent barcode, an invalid check digit and a duplicate barcode all returned HTTP 200 with
  the expected exact/not_found/invalid/candidates statuses. Batch median 9.53 ms, first 89.16 ms;
  Python peak RSS 56,660 KiB. These are measurements for this corpus and host.

The initial isolated launch omitted PYTHONPATH and exited before doing work. The second was
stopped to make the index builder read pages sequentially. A third reached successful sealing
and HTTP tests but exposed a test-fixture mistake: all-zero GTIN exists twice in the real source,
so it cannot be used as an absent barcode. Corrected tests use a confirmed absent GTIN and retain
all-zero matches as duplicate candidates. Final tests reused the already sealed product pack,
recompared every entity and reverified its content hash. No failed rehearsal published to the
serving catalog.

## Operational scope

Only platform.py, native_api.py and __main__.py are changed relative to the exact installed
module tree. The staged source preserves all other live modules. No new image or Git push is
part of this repair. Source acquisition flags and credentials are not changed. Rehearsal and
maintenance containers have networking disabled and cannot acquire retailer datasets or invoke
paid providers.

The standard Tower inventory collector was run from an isolated copy to preserve canonical
inventory. Its development-VM leg failed `No route to host` for 192.168.0.30; direct Unraid
inspection is the service evidence. TWR-059 / Forgejo issue #22 tracks this repair:
https://git.tower/callum/tower-operations/issues/22

See `preflight-result.json`, `release.json`, `before-containers.json`, `checks.json` and the
explicit operator scripts in this directory. Before-module files are retained to separate this
patch from existing uncommitted repository work.

## Production publication and activation

The network-disabled maintenance worker completed successfully in 557.56 seconds. It backed up
the current generation, every current pack and a consistent integrity-checked control database
at `/data/backups/20261027-before-barcode-index`. Compose is backed up separately at
`/mnt/cache/backups/bord-food-api/20261027-barcode-index/compose.before.yaml`.

Published generation `g_3d03aef2ba8745718bde0e9dac73fc13` changes only the products object. Its SHA-256
`80ba94a3192dbe0db16c8d1fc5f5e52c67bc4146274666c58b3233effd341d37` exactly matches the full-catalog
rehearsal, whose complete entity comparison passed. Source checkpoints/check times, registry
revision, redirects and all five other packs are unchanged. USDA remains 469,046 foods.

Only `bord-food-api` was targeted by Compose activation, at 20:23:34 UTC. The same pinned base
image is retained; the read-only module tree now comes from
`config/barcode-releases/a7b1d769edaa6ad9adb037d534a05a38962e9ec84c87ba3a7c11f1cba2f6667c/bord_food_api`.
Only platform.py, native_api.py and __main__.py differ from the prior live tree. Module hashes
were directly verified inside the serving container. Source/live Compose differ only at that
module mount, and the canonical source release was mirrored locally.

Five live six-identifier batches from the actual Bòrd container returned HTTP 200 and the
expected exact/exact/exact/not_found/invalid/candidates statuses. The first took 81.79 ms;
subsequent batches took 11.62–12.94 ms. Known Aldi barcodes 4099100013566 and 4099100009927
returned the preserved cheddar and pumpkin spice cream cheese names. Raw and padded forms
resolve to the same product. Local USDA food detail/search, live/ready/health and unauthenticated
401 checks passed. Trusted `https://food-api.tower/health` returned 469,046 foods. No new ASGI or
SQLite interruption errors were found after API activation. All three observed services are
healthy with no OOM; the history container retained its original start/image.

A separate Bòrd image update/recreation happened at 20:05:58 UTC, before the 20:23 API activation.
It changed image 2cec8d48… to 17ae8046…, so Bòrd’s start/image cannot be claimed unchanged across
this investigation. This repair’s deployment command targeted only the API and preserved that
newer Bòrd configuration; live checks used the currently running Bòrd. No companion code or
household writes were performed by the verification requests.

Tower repository validation passed with zero violations and existing archive/generated-output
findings. The failed development-VM inventory leg remains a separate limitation. No Git push,
image publication, new dataset acquisition, optional-source activation or paid requests were
performed. Full receipts are `publication.json`, `live-verification.json` and `checks.json`.

After verification, the six exited task containers and disposable rehearsal database copies were
removed. Serving objects, source downloads, the current-generation backup and all receipts remain.
See `cleanup.json`. Forgejo issue22 is closed.
