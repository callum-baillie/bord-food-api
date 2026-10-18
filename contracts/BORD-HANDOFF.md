# Bòrd API integration handoff

**Historical handoff — 17 October.** The companion was subsequently implemented and deployed separately on 18 October as rc.14. See [current implementation status](../docs/PLAN-STATUS.md) and the private Tower operational record. The unperformed statements below describe the original API-only handoff, not the current companion deployment.

API repository work only. The accessible `our-recipes` checkout was inspected read-only at the configuration, food-data domain/provider/service seams. Its existing USDA provider passed the synthetic loopback compatibility smoke in `scripts/smoke-bord-offline.py`. No companion code, household database, UI or migrations were changed; companion implementation tests, deployment and live activation remain unperformed. Follow `plans/food-data-platform/prompts/04-BORD-COMPANION.md` in an authorized companion work session.

The existing `USDA_FDC_BASE_URL`, `USDA_FDC_API_KEY` and `USDA_FDC_ENABLED` continue to target `/fdc/v1` with existing USDA source semantics. Startup now permits liveness before data; `/health` still requires a USDA catalog. `scripts/verify-bord.mts` retains the real Bòrd provider compatibility check and requires an explicitly selected API target.

`openapi.json` is generated from the installed FastAPI application. `bord-catalog-client.ts` is a reviewed server-only starter with injected fetch, five-second deadlines, redirect refusal, configured read key, and no remote fallback. It is not an installed companion provider. Native records use `id`, `content_revision`, and `source_refs`; USDA source details retain the original payload under `data`. Resolve is a typed identifier batch; native GTIN validation is stricter than legacy padded search. Shared GTIN fixtures are exported beside this handoff.

Proposed companion server configuration:

```dotenv
BORD_FOOD_API_BASE_URL=http://bord-food-api:8080
BORD_FOOD_API_KEY=<server-side read key>
FOOD_DATA_MODE=catalog_preferred
FOOD_DATA_ALLOW_REMOTE_FALLBACK=false
STORE_DIRECTORY_ENABLED=true
```

Companion work must actually validate these settings and pass them through Compose. None is `NEXT_PUBLIC_*`. Preserve `provider=usda_fdc` or `provider=open_food_facts`; record `transport_id=bord_food_api` separately. Cache identities need endpoint/config fingerprint, catalog generation, normalizer and locale. Native selection must carry `content_revision`; an unavailable exact revision returns `409 REVISION_EXPIRED` requiring review. Bòrd owns durable reviewed nutrition snapshots, recipe/pantry changes, purchases and user confirmation.

Store links are nullable associations to existing profile UUIDs with immutable selected metadata snapshots. Preserve user notes, aliases, sections, aisle ordering, routing and shopping relationships through link/unlink and official metadata refresh. Household override takes precedence over usable branch placement, then reviewed department mapping, existing category route and Unassigned. Source absence is not closure. No OFF banner tag or public historical price implies branch stock. Unknown offers and placements are empty with explicit unknown availability. Map discovery can remain usable as an official link while asset display rights are pending.

Distinguish initializing/503, unavailable, disabled, stale, partial and rights-blocked. Keep manual stores and existing household records usable during outages. Native lookup and enrichment are pure reads; no stock, cart or purchase is created. No household receipt or watchlist is uploaded by V1.

Required companion evidence remains unperformed: actual repository lint/type/unit/integration/release gates; profile migration/link/unlink/override retention; exact revision confirmation; transport/generation cache isolation; catalog-only egress denial including images and fallback; actor/origin guards and purchase idempotency. Generate a bounded synthetic API fixture service for these tests. Live source verification, retailer crawling, map permission review, paid connectors, deployment and Git push require separate activation.
