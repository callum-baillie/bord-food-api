# Plan implementation status — 18 October 2026

**V1 API implementation is complete. The entire multi-version roadmap is not complete.** V1.1/V2 are later milestones, and live validation/activation of every optional V1 source is separate from delivering its code.

The task ledger contains **35 V1 tasks**: 34 API implementation tasks completed with offline evidence and one completed Bòrd handoff. Its per-task `live_verification=not_performed` fields deliberately preserve the original 17 October implementation record; current runtime evidence belongs in the activation register and the dated deployment/pilot reports. These historical fields are not the current deployment status.

| Area | Current implementation and verification | Remaining work |
| --- | --- | --- |
| P00–P02: compatibility, immutable publication, control/jobs/scheduler and empty startup | Implemented and tested; supervised API/worker deployed on Tower | Broader long-running production observation |
| P03: USDA and stores | USDA and five selected ATP partitions active; 469,046 foods, 8,665 stores, 23 chains at the recorded pilot generation | Coverage expansion/source-fact audits; imported coverage is not a national census |
| Optional SNAP | CSV parsing, provenance and reviewed current-resource override implemented/tested | Official current-resource access unresolved; live import and matching validation unperformed |
| P04: OFF | Streaming JSONL, scope filters, identity/nutrients, delta continuity/reconciliation implemented/tested; full 13.18 GB export downloaded and hashed on Unraid | Full import/capacity rehearsal; proven baseline extraction boundary and live baseline/delta equivalence. A downloaded gzip is not a published product pack |
| Optional Open Prices | Three real exports downloaded; corrected full parser validated 42,822 US observations; 14,136 distinct valid GTINs match USDA | Currency/freshness/location-quality review, reviewed branch crosswalks; no price pack published |
| Optional FoodKeeper | English resolver, cell-array workbook parsing, category integrity, conditions/provenance implemented; isolated synthetic Unraid publication/storage rehearsal passed | Official FSIS artifact returns 403; no live import or current size/count verified |
| P05: crawler/maps | Bounded framework implemented; one two-request Altoona link-discovery run succeeded, then paused | Broader reviewed pilots; media rights/acquisition/rendering and real placement/geometry remain separate. One PDF link is not a routing graph |
| P06: API/Bòrd | Generated contracts and handoff delivered; companion implemented and deployed separately as rc.14 | Full user-facing restore and physical-device/PWA acceptance are not established by the API work |
| P07–P08: deployment, migration, backups and checks | API deployed as immutable SHA image; original USDA preserved; protected backups, SQLite integrity, health/auth/worker checks passed | A live restore exercise, national-volume OFF import benchmark and further operational observation |

Latest API application: `f177b5e1106484c6ca2dffb36fa035c514280d30`. Local regression: **219 passed**, one upstream warning; Ruff, formatting and generated OpenAPI checks passed. GitHub run [39156343117](https://github.com/callum-baillie/bord-food-api/actions/runs/39156343117) also passed all 219 tests and synthetic Docker smoke, then published AMD64/ARM64 images. Documentation-only commits do not change that running image.

Bòrd’s independently deployed companion source is `c472451c7dc8a3e56791bc23ed6e2235e916d013`, release `1.0.0-rc.14`, schema `0067_bord_catalog_links`. It includes native catalog-only reads, reviewed revision snapshots, profile linking and the store directory. Deployment verification covered actual adapter/authenticated routes, household retention and migrations. The independent review also exercised 45 focused tests and isolated browser flows at 320/390/768/1440 widths. A fresh live health read on this follow-up returned rc.14/current migrations. The newer local companion checkout contains other ongoing work; it was not deployed or changed by this OFF download.

The **five later tasks remain not started** in this plan:

- X01, V1.1: Overture release/schema adapter.
- X02, V1.1: OFF Parquet alternate bootstrap.
- X03, V1.1: regional OSM/IndoorEqual geometry.
- I01, V2: private purchase evidence and package-aware planning.
- I02, V2: entitled live retailer and basket scenarios.

No single percentage usefully combines these differently sized milestones with blocked source activation. The useful distinction is: V1 code and companion delivered; core sources live; optional sources progressively validated; later roadmap unimplemented.

Current source measurements, limitations and validation plans are in [SOURCE-PILOT.md](SOURCE-PILOT.md). Original deployment evidence is in [TOWER-DEPLOYMENT.md](TOWER-DEPLOYMENT.md). The activation register records later operations without rewriting the offline implementation history.


## Full OFF artifact now retained on Unraid

The owner’s separately authorized full download completed in **475.56 seconds**. Object version `VILumlWXh8J9mlPCmokEeMpO11A6lEpI`, ETag `"395f715cf569f60f5f72ad119cdc9087-786"`, Last-Modified 18 October 2026 06:41:48 UTC. Exact compressed bytes: **13,179,356,850** (13.18 GB; 12.27 GiB). Local SHA-256: `1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37`.

The artifact is in the food API’s `downloads/open_food_facts/` cache on the actual Unraid cache-backed data volume, with native metadata/provenance sidecars. The version-pinned transport checked the expected length and ETag and generated the local hash; gzip header sanity passed. A complete gzip CRC check, full schema scan, normalized product import and live baseline/delta comparison have **not** been performed. This receipt does not invent an extraction boundary or advance a source cursor.

Final checks: no OFF jobs; source activation still false; generation still `g_39e9f3f5bbe84bb9bf3f2aba0f8f1991`; `/live`, `/ready`, `/health` all 200. Free cache: **466,350,084,096 bytes (~434.3 GiB)**. Acquisition receipts are separate from serving catalogs. No app image, policy, household data, retailer traffic or paid API changed in this follow-up.
