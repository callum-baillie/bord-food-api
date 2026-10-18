# Implement the Bòrd Food API expansion — main Codex prompt

You are working in `callum-baillie/bord-food-api`. Implement V1 of the expansion specified by `plans/food-data-platform/README.md` and the documents it links. This is an implementation task, not another high-level planning response.

## First actions

Read the actual root and nested `AGENTS.md` instructions, current branch/HEAD, worktree status, runtime/config/CLI/catalog/importer code and existing tests. Inspect this plan’s repository audit, scope, architecture, synchronization and acceptance matrix. The recorded SHAs are review references, not reset targets. Preserve all unrelated and uncommitted user work. Do not overwrite a newer implementation just to resemble the earlier plan.

Create a brief execution plan mapped to `progress/tasks.json`, then implement dependency-ordered phases P00–P08. Update task status only with evidence. Keep a running `progress/verification-log.md` and `progress/decisions.md`. Do not repeatedly ask the user to reconfirm design choices already resolved by the package. Make reasonable documented implementation decisions within scope.

## Scope and permissions

Implement source acquisition code, durable scheduling, nonblocking empty startup, immutable publication, safe incremental updates, API contracts and integration handoff. **Do not execute retailer crawlers, live source downloads/imports, authenticated retail calls, paid requests, deployments, Git pushes or production database changes during this implementation run.** Use synthetic fixtures and mocked transports; a loopback fixture server is allowed. Documentation reads and ordinary dependency installation are distinct from source acquisition, but respect the current environment’s network permissions. No source-network traffic in routine tests/CI.

The resulting installed system must start with schemas and **zero business data**, then automatically bootstrap and update its configured bulk sources at runtime. Never auto-load `examples/`, the 120+180 chain research records, or any hand-authored Walmart facts into production. Default runtime networking is bulk-only for explicitly configured core sources. Crawlers and paid providers are independently disabled until an operator enables a reviewed source policy later.

Do not interpret “incremental” as “ignore existing stores forever.” Poll release/roster metadata cheaply, apply native deltas only when valid, compare normalized hashes for snapshots, and fetch detail pages only for new/missing/changed/due evidence. Stable address/coordinates use low-frequency audits and explicit change triggers. Hours, closures, prices and stock have independent validity/freshness. Source absence never proves closure.

## Architectural invariants

Keep Python, FastAPI, SQLite FTS5 and streaming ingestion. Preserve `/fdc/v1` payload/auth/error behavior, source IDs, nutrient values/units, null-versus-zero semantics and existing install conventions. Maintain legacy `/health` semantics and add independent `/live`, `/ready` and `/v1/system/status`.

Never mutate a serving catalog. Write changed data into private staging snapshots and atomically publish a consistent manifest. Use a durable control DB for identities, jobs, source cursors, policy and recovery. Requests bind to one published generation/crosswalk. Checkpoints advance only when the matching publication is visible; recover the filesystem/control two-phase boundary after crashes. Fence stale workers; make at-least-once execution produce idempotent effects. Do not hardlink a serving DB and mutate the link.

Preserve stable chain/store/product IDs across source changes. Source, transport, identity, retailer listing, price, stock and map are distinct concepts. Unknown stays unknown. Do not average nutrition conflicts, merge products by name alone, claim a retailer tag means branch stock, or claim a map image is a route graph.

Bòrd retains household recipes, pantry quantities, private receipts, purchase intake, profile preferences, shopping deficits, user confirmations and Instacart handoff. Do not reimplement these in the food API.

## Implementation sequence

P00 freezes compatibility and network boundaries. P01 implements durable state/publication before source complexity. P02 implements empty-start roles/scheduler/CLI. P03 delivers USDA/ATP and optional SNAP parsing, roster diff and store APIs. P04 delivers optional OFF JSONL/deltas, products/measures and optional Open Prices/FoodKeeper. P05 builds the disabled crawler framework and synthetic Woodman’s map pilot. P06 generates authoritative OpenAPI and Bòrd handoff. P07 covers migration, Docker/Unraid, resource policies and restore. P08 runs final checks.

Source adapters must implement real documented parsing/synchronization behavior, not placeholder downloads. A SNAP resource resolver blocked by the live environment can remain explicitly unresolved with local/override ingestion tested; do not invent a URL. OFF delta continuity/gaps/deletions require actual logic and fixtures. Optional activation is not permission to omit required V1 adapter code. Overture, Parquet alternate bootstrap and OSM geometry are explicitly later-phase work, not required stubs.

Use repository-native test tools. Share cross-language identifier fixtures and generated contracts with Bòrd. Inspect `our-recipes` only when accessible; if it is not an authorized writable checkout, finish the API and deliver the companion prompt/contract instead of pretending the application UI changed. When authorized, use `prompts/04-BORD-COMPANION.md` for those changes in the correct repository.

## Execution discipline

Prefer small testable increments. Reuse existing code where correct; do not perform broad aesthetic rewrites. Parallel agents, if supported, can own independent modules after shared contracts stabilize; one agent owns schema/publication. Reuse context and perform targeted reviews rather than launching an expensive general review after every small edit. Do not assume any model name, agent feature or “Goal mode” exists in this environment.

When blocked, record a precise limitation, complete independent work, and retain honest disabled/unverified status. Do not mark production deployment, live data quality or paid API access as tested based on mocks. Do not weaken a security boundary to make a test pass.

## Completion

Run the applicable existing tests, new matrix tests, lint/format, schema/contract checks and available offline container/integration smoke tests. Review empty production images and all network activation defaults. Verify crash/rollback/checkpoint tests, especially publication after a simulated interruption. Update operator documentation and evidence logs.

Your final report must state implemented phases/tasks, files changed, actual commands/results, migration/compatibility decisions, live activation gates, Bòrd companion status and remaining limitations. V1 implementation complete and live-source verified are separate claims. Do not stop at a plan, scaffolding-only implementation, or assertions unsupported by tests.
