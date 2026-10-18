# 15 — Architecture decisions, risks and recovery choices

## Decisions adopted by this plan

| ADR | Decision | Reason and trade-off |
|---|---|---|
| ADR-01 | Extend existing Python/FastAPI/SQLite repository | Reuses working compatibility and deployment. Independent database/search infrastructure requires measured need. |
| ADR-02 | Immutable serving snapshots plus durable control DB | Honors root AGENTS and safe replacement; requires a carefully tested filesystem/control recovery protocol. |
| ADR-03 | One manifest defines a compatible generation | Prevents mixed-source/crosswalk responses; unchanged object files can be reused. |
| ADR-04 | Automatic bulk-only runtime; no development acquisition | Meets empty-start auto-update goal without accidental crawls, bills or production data in source control. |
| ADR-05 | Prefer upstream bulk output to crawling retailers | Minimizes maintenance and request load. Full source snapshot transfer may still be unavoidable. |
| ADR-06 | Volatility-aware refresh with periodic audits | Avoids recrawling unchanged addresses while retaining correction/relocation detection. |
| ADR-07 | Public evidence and household state stay separate | Keeps API reusable and preserves Bòrd’s transaction/privacy guarantees. |
| ADR-08 | Native API alongside USDA-compatible subset | Unified domains without mislabeling OFF as USDA or breaking current provider consumers. |
| ADR-09 | Source/transport/identity are different | Attribution and cache semantics remain accurate through local mirrors. |
| ADR-10 | Counts are dated assertions, not primary-key identity | Mixed corporate/banner/territory scopes cannot destabilize IDs or inflate observed coverage. |
| ADR-11 | CLI operator controls in V1 | Smaller security surface. Bòrd gets read-only health/progress until authenticated admin design is separately approved. |
| ADR-12 | Optional sources have implementation and activation states | Missing credentials or legal review cannot masquerade as broken core readiness or tested live integration. |

## Material risks

**Provider drift:** formats, URLs and country/category fields change. Pin adapters, reject incompatible schemas, retain raw hashes, provide bounded official resolver/operator override and local import. Never guess a resource ID. A failure keeps last-good data.

**Stale successful data:** a server 200 or ATP successful-output redirect may be old. Track source date separately; warn by pack/field. A cheap 304 means resource unchanged, not independent confirmation of real-world truth.

**Delta incompleteness:** OFF’s export script is not a guaranteed deletions feed. Require continuous intervals and a compatible baseline; perform periodic full reconciliation. Gap recovery consumes more bandwidth but avoids silent stale state.

**False entity merges:** brand aliases, subsidiaries, common names and colocated departments are hard. Exact source crosswalks and reviewed overrides win; ambiguity stays explicit. Merge/split history is reversible. A small distance never proves the same store.

**Publication split brain:** filesystem atomic replacement and SQLite commit are separate. One publisher, fencing tokens, prepared generations and deterministic recovery are required. Source watermark advancement before visible publication is prohibited.

**Excessive resources:** private snapshot copies and bulk gzip processing can consume disk. Preflight and runtime quotas pause jobs; checkpoint optional heavy work; do not mutate serving data to save space. Efficient logical diff does not guarantee small downloads or file writes.

**Legal/licensing exposure:** open code, open data, API terms and map/image rights differ. Store operational policy evidence and review obligations; separate files are not a license exemption. Restricted sources remain disabled/link-only until allowed. No circumvention to increase coverage.

**Private data leakage:** Bòrd recipes/receipts/products can expose household habits. Avoid request payload logs and automatic public contributions. Watch lists are explicitly configured minimal store IDs, not uploaded location histories.

**Integration drift:** Bòrd’s current main is newer than the earlier plan. Reinspect current schema/auth/config/tests; generate a companion patch only against the actual checkout. Preserve review and idempotency regardless of file refactors.

**Unknown source access/costs:** no authenticated retail requests were tested. Unknown prices/permissions remain null; a documented API may be supplier-only. V1 core does not depend on a retail contract.

## Questions deliberately resolved without blocking implementation

Use 50 states + D.C. scope, separate territories, no assumed national completeness; SQLite initially; no required cloud/SaaS; automatic core bulk runtime; independent opt-in crawlers; original real examples are fixtures only. Whether to enable ODbL product packs, particular live providers, or a crawler is an operator activation choice, not an excuse to leave the core undefined.

Record justified deviations in `progress/decisions.md`, including downstream schema/test changes. Do not quietly change these policies while implementing convenience features.
