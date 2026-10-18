# 17 — Example data and research provenance

## What is included

`examples/reference-v0.1/` preserves the two previously supplied JSON files byte-for-byte. They are **dated real-world examples** from the earlier review, not a current live branch feed. The reference Walmart chain record reports 4,615 Walmart U.S. segment units on 31 July 2026, with mixed-format scope and separate directory coverage. The Coralville record identifies store #2827 at 2801 Commerce Dr; unverified coordinates, map, prices and stock remain null/unknown. [S15]

`examples/real/` wraps those same data objects in the proposed native envelope. It does not improve verification status. An example metadata flag and null catalog generation make clear that no runtime import occurred. Embedded provider/format counts are historical assertions, not runtime bootstrap values. Source dates and qualifiers survive unchanged.

`reference/chain-research/` preserves the prior 120-ranked/180-candidate registry JSON and ranked CSV. These are research attachments supplied earlier in this conversation. Count dates and scopes differ; candidate names/URLs may be wrong or no longer active. They are not crawler targets or business seeds without separate validation. The original JSON retains its 164-source ledger and limitations. The input inventory records hashes of the supplied material.

`examples/synthetic/` contains empty-start status, a deterministic roster change, continuous/gapped delta cases, typed identifier cases and synthetic map-link HTML. `.test` domains and synthetic IDs avoid pretending a real Walmart has a new price, aisle or store. Synthetic data is only for isolated test directories.

## Production exclusion

Production Docker builds copy only application code and reviewed source-policy descriptors, not these folders or the research CSV. The installer creates schemas with zero chain/store/product/source-record rows. Registering an adapter in configuration is not importing its chain data. Test loaders require explicit fixtures and an isolated temporary data root; there is no production `seed demo` path invoked by startup.

If a real example is used in a UI preview it must be labeled “reference example” and excluded from search/published counts. Do not geocode its missing coordinates or crawl its page as a side effect of tests. Never promote example `reviewed_on` into a recent `source_observed_at`.

## Example migration

The 0.1 example uses descriptive internal IDs such as `walmart-us-2827`; the V1 schema treats IDs as opaque strings and therefore accepts these for illustration. Runtime ID allocation must come from the persistent identity registry rather than regenerating a slug on every source import. External store number `2827` remains a string in a retailer-scoped namespace. An `example` flag belongs to the envelope, not an authoritative source assertion.

The chain example includes untested retailer API documentation links. These are capability research, not configured credentials or executable request templates. The new policy registry must enforce its own source, account, retention and cost gates before any such interface is used.
