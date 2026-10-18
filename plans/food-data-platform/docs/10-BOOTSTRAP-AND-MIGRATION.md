# 10 — Empty startup, automatic acquisition and migration

## Environment behavior matrix

| Context | Business data at start | Source network | Crawler behavior |
|---|---|---|---|
| Codex implementation | No production catalogs; temp fixtures only | No live data acquisition by default; ordinary dependency/doc access subject to environment permissions | Forbidden |
| CI/build | No real data; synthetic temp fixtures explicit | Denied for tests; package installs are build inputs, not dataset downloads | Forbidden |
| New runtime, production preset | Zero chain/store/product rows | Automatic configured bulk discovery/download after process starts | Disabled unless separately approved |
| New runtime, offline/manual preset | Zero rows until explicit local import | Denied | Disabled |
| Existing installation | Preserve existing `/data/foods.sqlite` | Honor existing explicit `AUTO_DOWNLOAD=false`; new sources require effective policy | Disabled unless separately approved |

Configuration/source definitions are software metadata, not catalog rows. Documentation examples are never found by an import-directory glob. Do not bind `plans/` or `examples/` to `/imports`.

## Fresh production bootstrap

1. Validate config, initialize control schema and runtime installation ID. No sample or chain-registry seed rows.
2. Start HTTP immediately. `/live` is 200; `/ready` and data endpoints accurately indicate missing packs. The Docker healthcheck does not restart the process just because data is downloading.
3. The worker atomically records bootstrap intent per source partition and effective config version. Restart does not enqueue duplicates.
4. Resolve configured bulk sources, download under ceilings, parse/validate staging and publish independent usable packs. Source status and per-pack progress are available while this happens.
5. When required packs are usable, `/ready` becomes 200. A blocked optional pack remains visible but does not block service.
6. Persist next-due schedules and continue incremental updates. There is no one-time-only bootstrap flag that disables future checks.

The production config’s `network_mode=bulk_only` allows only registered bulk data origins. It does not mean every arbitrary website tagged “bulk” is trusted. Crawler/download policy is checked centrally on every outbound path.

## Legacy config precedence

Implement and document a deterministic rule:

1. Explicit new config file/CLI source policy governs its own registered source operations.
2. Existing explicitly set `AUTO_DOWNLOAD=false` prevents automatic USDA bootstrap and refresh unless the operator explicitly replaces it with the new USDA policy; log a safe deprecation/precedence notice. Do not treat “false” as equivalent to unset.
3. `DATASETS` continues selecting only the existing USDA dataset types. It never means “all new data sources.”
4. Operator-placed local USDA files take precedence for initial USDA import when configured, and suppress automatic replacement of that manually selected pack unless `allow_managed_refresh_after_local_import` is explicitly true.
5. No source is silently enabled by copying a JSON sample or candidate registry into the repository.

Use the production example as the recommended **new installation** behavior; preserve explicit legacy restrictions during upgrades. Runtime network configuration must not leak into deterministic tests.

## Existing catalog migration

Do not delete, reset or overwrite an existing `foods.sqlite` to demonstrate empty startup. “Start empty” applies to a new installation, not a destructive upgrade.

Under an operator/migration lock, validate schema/integrity of the existing DB, calculate its checksum and copy it to a managed immutable object (or reference a read-only legacy file during transition). Create an initial managed manifest referencing it. Import existing source provenance; unknown source versions remain unknown. This adoption does not require internet access. Preserve the original file for rollback and document storage costs.

No source credentials, downloads, datasets or household databases belong inside the application image. Existing `import` and `refresh` CLI commands continue to use a safe publisher adapter after migration. Explicit USDA `import` retains its whole-USDA-catalog replacement semantics; it does **not** replace the store/product packs. New generic source import commands have explicit source/type namespaces.

Any adoption error leaves the original file unchanged and produces diagnostic state. A corrupt existing catalog is not automatically overwritten by a fresh network download. Operator recovery is required.

## Empty datasets and identity initialization

Reserve canonical IDs lazily when source facts arrive. Runtime source descriptors may name Walmart as an adapter target, but `/v1/chains` remains empty/not-ready until a valid catalog is published. An operator’s confirmed local import can create data; examples remain test-only.

The chain research registry has incomplete counts and unverified domains. Use it to prioritize descriptors in development. Do not automatically import all 300 as real chains or crawl their URLs. Banners that fail two-location eligibility stay candidates.

## Upgrades and rollback

Version the control DB and catalog format separately. A migration must back up mutable identity/job state with SQLite’s backup API, not copy a live WAL main file alone. Build new-format catalog objects before switching readers. A previous binary may not understand a new control schema; record the supported rollback procedure and restore a matching backup when necessary.

A new binary encountering an unknown future schema should fail clearly without mutation. Rerunning a completed migration is a no-op. Source parser changes may replay cached raw data locally without re-downloading it.

## Later activation

The main Codex prompt ends with tested software and no production dataset. The operator then installs it with a production preset; bootstrap begins automatically on that installed runtime. `prompts/06-RUNTIME-ACTIVATION-LATER.md` covers the first real bulk run and a separate crawler decision. This separation prevents the implementation session from exhausting disk, crawling retailers or altering the user’s running Unraid data.
