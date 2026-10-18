# Tower V1 deployment — 18 October 2026

This is a separately authorized deployment and live bulk-source activation after the 17 October offline implementation. The owner explicitly authorized logging into Tower, committing/pushing this API, building/publishing an image and configuring the environment. The historical implementation-only evidence in `V1-VERIFICATION.md` remains dated evidence, not a claim that activation never subsequently occurred.

## Installed release and configuration

- Application commit: `67c19463ebfe567658813b37a81f5920a0c6ff36`.
- Pinned image: `ghcr.io/callum-baillie/bord-food-api:sha-67c19463ebfe567658813b37a81f5920a0c6ff36`.
- Published multi-platform manifest digest: `sha256:b5d4b8f1ad6a518549900b016cc2e8d09a1c5b648da9ec3b13c8a5a3439755e5`.
- [GitHub CI and AMD64/ARM64 publication](https://github.com/callum-baillie/bord-food-api/actions/runs/39102394398): succeeded. Local full regression: **213 passed**, one upstream Starlette/httpx warning, 7.58 seconds. Ruff, formatting and generated OpenAPI checks passed; CI also passed its synthetic Docker smoke.
- Tower's existing `tower-productivity` project recreates only `bord-food-api`. The container runs supervised `run`, with read-only root, UID/GID 99:100, dropped capabilities, no-new-privileges, two CPUs and 2 GiB memory. Existing private Docker networking and read key are retained; no host port is added.
- Operator policy is mounted read-only at `/config/food-policy.json`, with `BORD_FOOD_CONFIG` set in the service. Automatic USDA and selected ATP bulk checks are enabled, approximately daily with jitter; managed refresh of the adopted local USDA catalog is explicitly enabled. One heavy job runs at a time. Data quota: 50 GiB; free-space reserve: 5 GiB.
- No additional source API key was required. SNAP, OFF, Open Prices, FoodKeeper, retailer crawlers, map downloads/rehosting and paid providers remain disabled.

Bòrd's existing legacy URL remains `http://bord-food-api:8080/fdc/v1`; its native client uses `http://bord-food-api:8080`. Keys remain server-side and were never printed or copied into source. Native companion configuration/UI/migration work belongs to its separate session.

## Live evidence

Checked at `2026-10-18T06:04:54.059225+00:00`. Current generation: `g_dde791271e1143488b60c5a59e39deb7`. Both required packs (`usda`, `stores`) are available.

USDA successfully downloaded its four configured bulk artifacts, built privately and published **469,046 foods**. Job transfer count: 222,191,867 bytes, including discovery. A subsequent explicit source check succeeded with `no_change`, reused the same generation/object and transferred only 160,418 discovery bytes. There was no second catalog rebuild.

All four selected ATP partitions succeeded and published **8,646 store entities and 22 chain/banner entities**. Total ATP job transfer count: 10,235,767 bytes, including discovery. Source output run: `2026-10-10-13-32-41` for each selected partition; the 18 October check time is not a newer retailer verification date. Counts describe imported source rows and are not a national census or a guarantee of complete chain coverage.

| ATP partition | Imported store entities |
|---|---:|
| `aldi_sud_us` | 2,750 |
| `kroger_us` | 2,393 |
| `target_us` | 2,026 |
| `walmart_us` | 1,477 |

Actual API checks returned HTTP 200 for `/live`, `/ready`, legacy `/health`, native system status/capabilities, chains, stores, Iowa-filtered stores, a bounded nearby-store search, legacy apple search and food details 167512/167513/167514. Missing-key requests to both legacy and native protected routes returned 401.

Before migration, representative health/search/detail JSON responses were captured and hashed. All five response fingerprints still match after live refresh. The original `foods.sqlite` remains byte-identical to its pre-upgrade backup; SHA-256: `3544db363ba08027a1f9fff67b73091dc0fcb835cc4c81c4fec988f2ba4ab97c`. The native store pack passed SQLite `quick_check`.

From the actual running Bòrd container, existing-key legacy food search, native store search, chain search and readiness all returned 200. These are transport checks, not companion UI/migration acceptance. No household data was modified.

Final observed runtime: healthy, worker health passed, zero restarts and no OOM kill. Idle sample: approximately 272 MiB of the 2 GiB limit and 0.09% CPU. Application data was 3.7 GiB with about 442 GiB free on Tower's cache filesystem. These are samples from this corpus, not national-scale benchmarks. The kernel reports swap-limit accounting unavailable; the 2 GiB memory limit is active.

Recorded next checks in UTC: usda_fdc: 2026-10-19T06:05:31.765138+00:00; all_the_places: 2026-10-19T08:46:06.224211+00:00. These are durable scheduler observations, not promises that an upstream source will publish new data then.

## Backup, fixes and boundaries

A protected timestamped host backup includes the original catalog/downloads, Compose source, existing protected environment and container metadata; the original image is retained with a rollback tag. Backup SHA-256 verification and SQLite `quick_check` passed with 469,046 foods. Exact recovery paths and operator commands are recorded in Tower's private `operational/19-bord-food-api.md`. No live rollback or restore was performed; deterministic crash/restore tests remain the restoration evidence.

The first GitHub build caught Python 3.12 versus 3.14's default OpenAPI 422 reason phrase. Commit `b40c64a` explicitly stabilized that native response description, with contract checks passing under both runtimes. Initial ATP acquisition then correctly blocked an unregistered cross-origin delivery redirect. The [official discovery endpoint](https://data.alltheplaces.xyz/runs/latest.json), its observed HTTPS redirect and the [upstream website repository's delivery-host example](https://github.com/alltheplaces/alltheplaces.xyz/issues/90) established `alltheplaces-data.openaddresses.io` as the published-output host. Commit `67c1946` registered that exact origin and validated its dated run/partition paths, adding four offline regression cases. Arbitrary redirect origins remain denied. After deploying the fix and retrying the blocked job, all partitions succeeded.

Tower's general state collector was attempted, but its development-VM leg could not reach the VM from this workstation. The partial inventory output was not adopted; prior local inventory was preserved. Unraid was inspected directly, and Tower repository validation returned valid with zero violations. No development-VM service was changed.

No retailer crawler, paid/authenticated retail provider, map asset acquisition or companion deployment was performed. Optional-source live behavior, broader coverage, source-level retailer accuracy and companion T36–T39 remain unverified here. Unrelated local setup-guide edits and Tower work were preserved and excluded from the API release commits. The final image stays pinned to the tested application commit even if later documentation-only commits update this record.
