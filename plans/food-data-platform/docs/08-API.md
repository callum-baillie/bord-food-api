# 08 — API and compatibility contracts

All new paths below are **proposed**. Implement Pydantic schemas and generate the authoritative OpenAPI from FastAPI. `contracts/openapi.blueprint.json` is a planning contract, not an implemented endpoint claim.

## Existing interface stays valid

Keep GET/POST `/fdc/v1/foods/search`, GET `/fdc/v1/food/{fdcId}`, `X-Api-Key`, USDA field shapes, validation bounds, exact barcode lookup behavior, missing nutrients and data types. Unknown source IDs stay 404 when the USDA pack is available; an unavailable pack stays 503. `/health` retains its USDA-catalog readiness semantics for existing callers. `/status` retains its legacy USDA provenance response when available. Document intentionally changed **startup timing**, not a silent schema break. [R03–R06]

## Operational/read endpoints

| Endpoint | Semantics |
|---|---|
| `GET /live` | 200 when API process/control layer can respond; independent of catalog completeness; no secrets |
| `GET /ready` | 200 when configured required packs are usable, otherwise 503 with safe per-pack reasons; stale last-good packs remain usable with warnings |
| `GET /v1/system/status` | Read-key protected sanitized catalog/source/job summary, including empty/bootstrap state |
| `GET /v1/capabilities` | Implemented/enabled/available/stale/rights-blocked per source and feature; not one blanket healthy flag |
| `GET /v1/catalog/generations/current` | Active business manifest ID, source versions, attribution and schema version |
| `GET /v1/catalog/changes?after=...` | Published entity/version changes; cursor-scoped, no household/private payloads |

Control/status routes must not depend on a USDA DB connection. A disabled optional pack does not make `/ready` fail. Default required packs are `usda` and `stores`; liveness stays true while either is bootstrapping. A source failure after prior publication does not erase the pack.

## Business routes

| Route | Parameters and bounds | Behavior |
|---|---|---|
| `GET /v1/chains` | `country=US`, `min_stores=2`, `limit<=100`, cursor | Source-scoped reported and observed counts; no fake census ranking |
| `GET /v1/chains/{chain_id}` | opaque ID | Chain identity, published coverage, source/link/capability references |
| `GET /v1/stores` | text/state/chain filters; paired lat/lon; radius 0.1–100 km; limit<=100 | Deterministic generation-bound cursor, exact geodesic filter after spatial candidates |
| `GET /v1/stores/{store_id}` | opaque ID | Store detail, evidence and unknown fields; aliases resolve transparently with redirect metadata |
| `GET /v1/foods/{source_id}/{record_id}` | optional exact `revision` | Underlying food record, never a fabricated merged USDA result |
| `GET /v1/foods/{source_id}/{record_id}/measures` | optional form/basis | Available portions/conversion evidence; unresolved stays unresolved |
| `GET /v1/products` | query/category/brand, limit<=100 | Local product candidates with distinct source records |
| `GET /v1/products/{product_id}` | opaque ID | Canonical identifiers and source alternatives |
| `POST /v1/products/resolve` | 1–100 typed identifiers | Per-item status: exact/candidates/invalid/not_found; no implicit live fan-out |
| `GET /v1/products/{product_id}/retail-evidence` | optional store/channel | Dated association/price/placement evidence, independent capability flags |
| `POST /v1/shopping/enrich` | <=100 line IDs with optional product/store IDs | Pure local enrichment; no pantry, cart, receipt or purchasing side effects |
| `GET /v1/stores/{store_id}/maps` | optional floor | Discovery/rights/asset status; unavailable maps do not disable store use |
| `GET /v1/maps/{map_id}/assets/{variant}` | fixed variant enum | Only entitled existing assets; safe media response, no arbitrary URL proxy |
| `GET /v1/guidance/storage` | bounded query/form/storage state | Source-backed guidance, no individual safety guarantee |

In V1 product/evidence routes do not perform remote provider calls in request handling. Future demand-driven live lookups use a separate explicit operation/permission, not an unnoticed fallback. A public read key cannot start crawlers or change source policy.

## Envelope

```json
{
  "schema_version": "1.0.0",
  "data": {},
  "meta": {
    "catalog_generation": "g_example_only",
    "source_refs": [],
    "warnings": [],
    "next_cursor": null
  }
}
```

`data` is an object for detail, an array for collection. `catalog_generation` is null in an example/uninitialized operational response, not a fake production ID. Error envelope:

```json
{
  "error": {
    "code": "CATALOG_NOT_READY",
    "message": "The store catalog has not been published yet.",
    "retryable": true,
    "details": {"pack": "stores"}
  }
}
```

Use 422 invalid inputs, 401 missing/invalid configured read key, 403 rights/permission denied, 404 entity/asset not in a usable catalog, 409 expired cursor or selection revision/conflict, 429 query budget, 503 pack unavailable/source unavailable. A filtered query with zero matches from a usable catalog is 200 + empty array. A missing catalog is **not** successful zero stores. Errors expose no URLs with tokens, filesystem paths or raw upstream bodies.

## Generation, identity and revision

Expose `ETag` from generation + canonical response/query hash. Preserve per-record `content_revision` so unchanged records remain identifiable across generation switches. Pinned selection must either return the exact record revision or a `REVISION_EXPIRED`/review-required result. Never silently substitute a newer formulation after the user reviewed nutrition.

Cursors bind filters, sort key, generation and expiry. Prefer signed opaque tokens using installation secret or persisted cursor records; prevent unbounded offset queries. Change-feed retention is proposed 30 days, versioned and monotonic; return `409 CHANGE_CURSOR_EXPIRED` with full-refresh guidance rather than omit lost events. Event IDs are committed only for published generations, with transactional-outbox recovery as described in Architecture.

## Request security and limits

Preserve the 16 KiB body cap for legacy routes. New batch routes have a separate explicit 64 KiB cap and <=100 items; never raise every route’s limit just to accommodate a batch. Bound query strings, Unicode normalization, search tokens, joins and wall time. Continue parameterized SQL/FTS token handling and 5s absolute query deadline as an upper guard; benchmark lower targets separately.

The API is internal by default. Read keys are required when exposed beyond a trusted container/LAN deployment. Operational write controls are CLI-only in V1. Do not give the browser source credentials or connect Bòrd to catalog SQLite files.

## Unknown retail result

If a product exists but no branch evidence was imported, return `assortment_status=unknown`, `availability=unknown`, `offers=[]`, `placements=[]`, and a specific reason. An OFF chain tag may appear as chain-level evidence only. Do not copy an example aisle or synthetic price into a real Coralville response.
