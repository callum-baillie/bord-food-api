# Platform runtime and operator controls

The read role (`python -m bord_food_api serve`) opens HTTP without importing or downloading. A fresh data directory contains schema and runtime metadata only; the worker never loads repository examples or chain research. `/live` is process liveness; `/ready` reports required pack availability; legacy `/health` retains its USDA catalog meaning.

`python -m bord_food_api worker` runs the durable scheduler and one heavy job at a time. `worker --once` processes at most two due jobs, prints JSON and exits. The SQLite queue survives restart, coalesces missed intervals, heartbeats leases and fences publication. `sync --due --once` is suitable for an external timer. Use one resident worker or one external timer, rather than both. An OS lock also prevents overlapping heavy work.

`python -m bord_food_api run` supervises separate read and worker children for a single-container install, forwards termination signals, reaps children and exits visibly if either child fails. Compose uses separate roles; the Unraid Compose and image default use `run`. HTTP healthchecks use `/live`, so an empty or downloading catalog does not cause a health restart. Worker health is independently checked with `worker-health`.

## Configuration and precedence

Set `BORD_FOOD_CONFIG` to an operator-owned JSON policy file; production and development-offline examples are under `plans/food-data-platform/configs/`. Mount that file and set the variable in **both** Compose roles when overriding defaults. Examples are documentation, not imported business data. API keys remain environment secrets, and acquisition has no API-key response or logging path.

Without an explicit file, new installations allow only registered HTTPS bulk origins for USDA and selected All The Places outputs. Optional SNAP, Open Food Facts, Open Prices and FoodKeeper are disabled. Direct crawlers, paid sources, media rehosting and arbitrary/private-network URLs remain disabled. A changed delivery CDN needs an explicit reviewed origin; redirects do not expand the allowlist. OFF and other optional sources also need source-specific resource/license review and configured delivery locations. SNAP resolution may require an operator-supplied current resource.

`DATA_DIR`, `IMPORT_DIR`, `PORT`, `API_KEY` and `DATASETS` retain their meanings; `DATASETS` selects USDA types only. Explicit `AUTO_DOWNLOAD=false` suppresses managed USDA acquisition unless an explicit new USDA `enabled` policy replaces it. An offline network policy disables every automatic source. Local USDA files are selected before an empty USDA pack is acquired and pin that pack against managed replacement; `allow_managed_refresh_after_local_import: true` on the USDA source opts into replacement. Existing `foods.sqlite` is validated and adopted by the worker without deleting the original; corrupt adoption stops acquisition and requires operator repair. Adoption and local import retain unknown versions as unknown.

Local `import [paths...]` builds privately and replaces only the USDA pack, preserving stores/products. Symbolic-link imports are rejected. `refresh [--force-download]` retains legacy whole-USDA replacement and uses the guarded transport and publisher. No serving database is edited in place.

## Inspection and intervention

These commands are network-free:

```sh
python -m bord_food_api status --json
python -m bord_food_api sources list --json
python -m bord_food_api sources explain-due all_the_places
python -m bord_food_api sync --plan --source all_the_places
python -m bord_food_api jobs list --json
python -m bord_food_api jobs inspect JOB_ID
python -m bord_food_api catalog rollback GENERATION_ID --plan
```

The plan reports unknown estimates as unknown and never fetches metadata to improve them. `sources pause SOURCE` persistently prevents new acquisition and fences in-flight publication. `sources resume SOURCE` removes the pause only when the effective configuration enables that source. `jobs cancel JOB_ID` revokes the job fence; `jobs retry JOB_ID` retries a terminal failure only under enabled policy. Resume/retry authorize subsequent worker acquisition; neither command performs HTTP itself.

Rollback requires `catalog rollback GENERATION_ID --apply`; inspection does not change the pointer. `backup NEW_DIRECTORY` uses SQLite's backup API for mutable state and copies immutable manifests/objects. `restore BACKUP_DIRECTORY --apply` requires an empty target installation; restore first into an isolated directory with offline policy and inspect status before enabling a worker. Back up the external operator policy and secrets separately and apply current rights restrictions before enabling reads or acquisition. Preserve matching application/schema versions for binary rollback. Back up Bòrd household data separately; it does not belong in this service volume.

## Deployment boundary

The image includes application code and dependencies, with no catalogs, downloaded datasets, source credentials or household files. Default UID/GID is 10001:10001. Unraid's 99:100 override requires pre-created writable appdata ownership. Use local SSD/cache appdata for SQLite, no privileged mode, Docker socket, or host-network requirement. Worker preflight reserves staging/free space and rejects byte/expansion limits; actual dataset capacity requires measurement. Retain the previous generation and matching state backup before upgrades.

Implementation tests use fixtures and mocked source transports. No live dataset import, crawler run, paid request, Docker/Unraid deployment or Git push is implied by those tests. First real activation remains the separate procedure in `plans/food-data-platform/prompts/06-RUNTIME-ACTIVATION-LATER.md`.

Source rights and acquisition pauses are separate. `rights restrict SOURCE --reason "review evidence"` immediately withholds that source and pauses acquisition. `--retention-until UNIX_TIMESTAMP` records a retention deadline; source policy can also set an ISO UTC `retention_until` or `can_retain: false`. Configured denials persist and never auto-clear when a file changes. `rights allow SOURCE --reason "review evidence"` records a reviewed clearance only after removing a conflicting configuration restriction; acquisition stays paused until `sources resume SOURCE`.

For physical removal, stop **all API/read processes**, leave the worker idle/stopped, then run `rights purge --quiesced`. The explicit flag confirms reader quiescence; the command also acquires the heavy-worker lock. Purge publishes a lawful replacement and removes restricted retained objects according to the platform policy. Do not use the flag while readers still reference old generations. Backup/restore honors source denials and retention expiry; an old backup cannot be used to resurrect restricted records. Ordinary pause retains last-good data, while rights restriction withholds it.

## Source semantics and limits

All The Places supports reviewed selected-spider outputs or the explicitly chosen `published_archive_us_grocery` profile. Archive mode can transfer worldwide non-grocery bytes before local filtering; it never silently replaces the smaller profile. Unknown equal banner names from different unreviewed spiders are kept separate. Counts are observed imported sites in the named generation, not a nationwide census. SNAP/ATP exclude U.S. territories by default; explicit source scope can include them.

OFF full imports without verified `baseline_extraction_started_at` remain snapshot-only and expose the alignment reason. Supply that boundary only with source evidence; retrieval time is not extraction time. With a proven baseline, deltas validate `(from,to]` coverage, overlaps, source revisions, conflicts and gaps. Changing parser/filter policy forces compatible replay or full reconciliation. Empty eligible delta intervals still require a visible generation acknowledgment before advancing their watermark.

Store records expose `field_refresh` group hashes and local scheduling clocks. Local first-seen/fact-change time is not retailer verification. Address/coordinates have 180-day audits; ordinary hours use 60 days or 14 for watched stores, and maps use independent negative backoff. Known facts survive fields omitted from a feed. Disabled crawlers create no detail jobs; the framework's planner reports only justified changed/missing/due candidates. Raw snapshots and normalization are distinct from retailer detail verification.

`rights purge --quiesced` removes revoked catalog generations/objects and source-scoped download caches after rebuilding the current permitted view. Stop API readers first; do not use this flag as a substitute for actual quiescence. Identity reservations remain durable to avoid ID reuse. Backup excludes forbidden historical payloads and must not be treated as an unrestricted public export. Optional media needs a separate permitted asset/rebuild procedure; V1 does not download or render map bytes automatically.

The optional Woodman's map-link adapter has an explicit one-job operator path:

```sh
python -m bord_food_api crawl --plan --adapter woodmans_maps
# After independent source/terms/robots/contact review and a later activation:
python -m bord_food_api crawl --once --adapter woodmans_maps
```

Both `network.crawl_enabled` and `crawler.enabled` default false. Activation additionally requires `crawler.adapters_enabled: ["woodmans_maps"]` and `crawler.adapters.woodmans_maps` with `enabled`, `source_authorized`, `terms_reviewed`, and `robots_reviewed` set true, plus an identifying `crawler.operator_contact`. The descriptor's `approved_targets` must be a bounded list of `{url, store_id, expected_branch}` for existing catalog branches. Its reviewed host is `www.woodmans-food.com` and path scope `/store-locations/`. No target list is populated at installation. The worker validates current robots rules, identities, host spacing, daily/run budgets and publication fencing. The adapter discovers links from approved HTML pages; it never downloads map assets. `crawl --once` selects only that explicit map job and does not schedule bulk bootstrap. Default periodic scheduling creates no crawler jobs. Pause/resume and terminal-job retry retain these independent activation gates.
