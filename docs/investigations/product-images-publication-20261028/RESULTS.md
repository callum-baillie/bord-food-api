# Published image deployment — 28 October 2026

The barcode repair and OFF image cache are committed to `main` on both
[GitHub](https://github.com/callum-baillie/bord-food-api/commit/405278132cf364ec01270f1dc1839dc5f60d0597)
and [Forgejo](https://git.tower/callum/bord-food-api/commit/405278132cf364ec01270f1dc1839dc5f60d0597).
The implementation commit is **405278132cf364ec01270f1dc1839dc5f60d0597**. It builds on the existing
0.2.0 release and preserves structured logging. Unrelated work in the original checkout was not
included. The release was prepared in an isolated Git worktree.

[CI run 40735932907](https://github.com/callum-baillie/bord-food-api/actions/runs/40735932907)
passed tests, Ruff, formatting, OpenAPI comparison and the synthetic Docker smoke, then published
AMD64 and ARM64 images. Local regression: 461 tests passed with one upstream Starlette warning.
The existing notebook's trailing source newline was fixed to unblock formatting. The Docker
smoke now gives its six-record fixture an 8 MiB staging/16 MiB data budget and zero free-space
reserve; production budgets are unchanged.

Tower now uses `ghcr.io/callum-baillie/bord-food-api:sha-405278132cf364ec01270f1dc1839dc5f60d0597`.
Registry digest: `sha256:cfd30a9008884df056439eddc72e0e1263805146b62c6eae76749366150dfe3d`.
Installed AMD64 image ID: `sha256:4bd62b6d489b548b4c5bfce0d1051232fe9203b0da23eabbe15120fc24678ea0`.
The label and every installed Python module hash match the committed source. The former application
code bind mount was removed; code and Pillow are supplied by the published image.

Only `bord-food-api` was recreated, at **2026-10-28T17:32:06.325711461Z**. Bòrd rc.27, the scanner
companion and history retain their task-baseline image IDs/start times. API/Bòrd/history report
healthy, the scanner remains running without a configured Docker healthcheck, and none report OOM.
The worker heartbeat is alive. No household or scanner writes were made by verification.

The serving catalog pointer and external policy are byte-identical before/after activation:
469,046 foods, generation `g_3d03aef2ba8745718bde0e9dac73fc13`. The 41 cached images/879,362 JPEG
bytes survived. Live requests from Bòrd returned cached images in about 7 ms, ETag 304, valid
metadata/license/hash and zero additional source requests. The two Aldi barcodes resolve exactly
in 13.59 ms total. `/live`, `/ready`, `/health`, USDA search/details, missing-key 401 and invalid
GTIN 422 passed, as did workstation HTTPS health using the Tower CA. No new ASGI/interrupted
errors were observed. The published image also passed a network-disabled synthetic image/API
preflight on Tower before activation, with no production volume mounted.

Compose/policy backup: `/mnt/cache/backups/bord-food-api/20261028-published-4052781/`.
The predecessor local image and immutable module release remain available. For rollback, restore
only this API service's former image/module-mount fields from the protected Compose backup, preserve
any subsequent unrelated configuration, validate Compose, and recreate only `bord-food-api`.
Catalog and cache need no rollback for this code-only change.

Source/live configuration changes are restricted to the API image/module mount. The canonical
operations repository also records the existing proxy network membership and enabled image policy.
Only the private Forgejo operations repository receives infrastructure records. The full image
collection is still not downloaded; the earlier bulk pilot and fallback limits remain applicable.

Receipts: `ci.json`, `deployment.json`, `published-image-preflight.json`, `live-verification.json`,
`checks.json`, and before/scanner baselines. Standard audit was attempted before changes in an
isolated copy; DevBox was unreachable, so canonical inventory was preserved. The canonical Tower
repository validator passed with its existing archive/generated findings.
