# 12 — Deployment, operation, backup and resource planning

Commands below are **proposed post-implementation interfaces**. They do not work against the current repository until Codex implements them. Do not run them as part of building this plan.

## Runtime choices

Recommended Compose: `bord-food-api` read service plus `bord-food-worker` using the same image and persistent local data volume. Worker has outbound network only under source policy; API should have no external acquisition role. Both use UID/GID 10001 by default, with documented Unraid 99:100 override only when ownership is prepared. Retain container port 8080 / existing published 8081 convention.

Unraid one-container option: `python -m bord_food_api run` supervises read API and one worker. It must reap processes, forward signals, expose worker-heartbeat status and restart/fail visibly on child failure. The API is not “healthy data” merely because its worker is alive. Avoid privileged mode, Docker socket mounts and host-network requirement.

## Proposed operator interface

```sh
# Local-only inspection / planning; must not touch the network:
python -m bord_food_api status --json
python -m bord_food_api sources list --json
python -m bord_food_api sync --plan --source all_the_places
python -m bord_food_api jobs list --json

# Role entry points:
python -m bord_food_api serve
python -m bord_food_api worker
python -m bord_food_api run

# Explicit post-install controls:
python -m bord_food_api sources pause all_the_places
python -m bord_food_api sources resume all_the_places
python -m bord_food_api jobs retry <job-id>
python -m bord_food_api catalog rollback <generation-id> --plan
```

`--plan` is network-free and produces `would_discover`, `would_download`, `would_crawl` with estimates only when metadata is known. It cannot secretly resolve live URLs to determine a plan. `sources resume`/retry are acquisition-authorizing operator actions and must explain effective policy before work. Actual rollback requires a separately explicit apply flag; never choose/deploy a generation automatically from a doc example.

Retain current `import [paths...]`, `refresh [--force-download]` and plain legacy `status` compatibility; new flags must not ambiguously reinterpret existing positional arguments. Publish their USDA changes through the common generation manager. Commands operate on the configured data directory, never an assumed production path.

## First installation after code is complete

1. Back up any existing API data. Do not attach Bòrd’s household directory to the API container.
2. Set API key and operator network/source policy outside Git. Use `configs/production.example.json` as a reviewed starting point; it contains no credentials.
3. Start the chosen role layout with an empty API data directory. New runtime production preset queues bulk bootstrap; examples are not loaded.
4. Inspect `/live`, `/ready`, status and source jobs. Confirm data counts reflect real publications and source dates.
5. Connect Bòrd’s current USDA variables for backward-compatible use. Apply the companion native integration later with its own tests.
6. Only after reviewing a specific source, enable optional packs/crawlers. Actual costs/rights/quotas are activation evidence, not inferred from config samples.

The proposed Compose file references code/features not yet present; the shipped implementation must update real `compose.yaml`, `compose.unraid.yaml`, `Dockerfile`, healthchecks and the Unraid XML, preserving existing settings/mount conventions where possible.

## Resource budgets — initial engineering limits, not benchmarks

Read API target test allocation: 2 vCPU, 2–4 GiB RAM. Worker target: 2–4 vCPU, 4–8 GiB, one heavy build at a time. No GPU. Plan an initial 50 GiB work allowance for selected packs, then size from actual downloads/imports; full OFF/images can exceed it. Media is separately capped and disabled by default. Production settings must fail preflight rather than assume the host has these resources.

Preflight **incremental free space** needs: incoming artifact(s) + decompression/ETL spill + new private snapshot(s) + backup/retention growth + safety reserve. Already occupied retained data is not counted twice as free-space need. Check both filesystem free bytes and configured quota. Recheck during streaming. The package’s JSON budget values are test starting points only.

Prefer local SSD-backed Unraid appdata/cache storage for SQLite/control files. Do not rely on SQLite locking over an arbitrary NAS/network filesystem; test the selected volume and keep single-host operation. External backup tools protect completed consistent bundles, not arbitrary in-flight database files.

## Backups

Back up control DB via SQLite backup API, committed generation manifests, all referenced required catalog/asset objects or a rebuild manifest, curation/identity history and policy config excluding secrets. Source downloads can be omitted if publicly reproducible and their hashes/versions remain recorded; an unrecoverable source requires its permitted retained raw copy. Keep a last-good generation for fast recovery.

Restricted live caches, tokens and private Bòrd receipts are not part of an open catalog export. Bòrd performs its own household backup, including selected source snapshots and catalog IDs. The identity ledger is critical: rebuilding it from scratch can break app links even if the public datasets are redownloaded.

## Restore and rollback tests

Restore into an isolated empty directory first. Validate manifest schema/hashes, DB integrity and all referenced objects; ensure no expired restricted payload returns from an old backup. Restore control state and generation together. Reconcile stale leases/prepared jobs before enabling network. Test rollbacks after crashes at each publication phase. Restore must not advance source cursors past the catalog actually restored.

Do not downgrade the application binary against an incompatible migrated control DB. Restore a matching backup or use a documented reversible migration. Source outage recovery is distinct from software downgrade.

## Metrics and alerts

Publish counters for successful/failed/no-op source checks, real source age, transferred bytes, new/changed/unchanged records, withheld records, detail requests avoided, closure candidates, delta gaps and queue age. Track source/entity group breakdown so healthy USDA does not hide broken stores. Alerts should identify actionable source failures and disk/lease problems, not repeatedly notify about intentionally disabled optional sources.

## Maintenance and scaling

Provide capped source retention and staging cleanup after job recovery, not random deletion. Periodic immutable-object GC uses quiesced readers/leases per Architecture. Upgrade to Postgres or independent search only after evidence of a real concurrent-writer/spatial/search bottleneck. National-directory size alone is not a requirement to add infrastructure.
