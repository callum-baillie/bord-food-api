# Suggested additive repository guidance

Merge only compatible statements into the actual AGENTS file; do not overwrite its existing instructions.

- The expansion plan lives in `plans/food-data-platform/README.md`; implementation scope is V1 P00–P08.
- Production starts without chain/store/product examples. `examples/` and `reference/` are documentation/fixtures, never automatic seeds.
- Routine tests and implementation runs use offline source transports. No live crawler, bulk acquisition, paid call, deployment or push is implied by an implementation task.
- API serving snapshots stay immutable; control/jobs/identities are mutable only in the separate control DB. Publish a compatible generation and recover checkpoint state after crashes.
- Differentiate native deltas, complete snapshots, semantic changes and source absence. Do not close a store merely because a source missed it.
- Keep actual source attribution independent of local API transport. Missing nutrients, prices, stock, map rights and field verification remain unknown.
- Bòrd owns household data and transactions. Preserve its review, actor, privacy and idempotency boundaries.
- Test evidence must distinguish offline implementation, live source verification and deployment. Update the progress ledger with actual results.
