# Food assistance implementation and source audit — October 21, 2026

Implementation, tests, source samples and deployment receipts are kept separately. See
[operating guide](../../FOOD-ASSISTANCE.md) for scope, routes, refresh and policy details.

## Live source audit performed

Three bounded, unpaid public metadata/sample requests were made from the workstation:

- Feed America Iowa bulk page: HTTP 200, two food-bank records. Both claim January 1, 2025
  verification; no independent verification implied. The Waterloo address differs from the
  Iowa HHS listing. Raw sample in `feed-bulk-iowa.json`.
- Resource types: HTTP 200. This is a multi-category directory, not all pantries; metadata
  `data_license=null`, and record-level upstream sourcing acknowledged. `feed-types.json`.
- HSDS descriptor: HTTP 200; claims CC BY 4.0 and gives upstream entity exports.
  `feed-descriptor.json`. That conflicts with the other metadata's absent license and does
  not establish sublicensing rights for every aggregated upstream. Feed import stays gated.

`source-audit.json` retains URLs, response sizes, types and SHA256 hashes. Browser-based
primary-source inspection also checked OSM, 211, Baltimore County, Philadelphia, Seattle,
Iowa HHS/Iowa Food Bank Association and Feeding America. USDA FNS TEFAP/product-sheet
requests returned 403; no bypass was attempted. No contact message or signup was sent.

## API and dataset implementation

Separate facilities/services/events, optional licensing-separated assistance packs,
spatial/text search, rights filtering, state/type/ZIP filters, generation cursors, dynamic
schedule freshness, retained conflicts and conservative relocation holds. Added OSM and
rights-gated Feed America refresh plus reusable reviewed ArcGIS/Socrata/HSDS export imports.
Updates are hash-based/additive; no disappearance-based closure. Old USDA/store/product
and guidance paths are preserved. Contract exported from FastAPI.

Operator enrichment reuses the shared robots/frontier and fails closed on redirects and
identity ambiguity. Reviewed operator facts retain field evidence; facility hours cannot
become distribution times. Optional Jev is review-only, text-only, under the shared $15 cap.
No product prices/inventory, household data or Bòrd UI changes are included.

## Qualification and activation evidence

`unraid-preflight.json` records a **network-none** run on the actual pinned production image:
66 source/config hashes checked, synthetic assistance site/service publication and HTTP 200
for the new search endpoints plus existing liveness/capabilities. The standalone campaign
plan made zero source/model requests. Synthetic data was confined to the canary's temporary
filesystem and was not imported into production.

Runtime deployment/launch and final checks are recorded in separate receipts when performed.
No national food-assistance completeness, live Feed America/211 import or companion activation
should be inferred from implementation or the synthetic qualification.


## Deployed runtime and October 22 recovery

The API source overlay was deployed October 21; pinned image reused, no image build or Git
push. Direct liveness/readiness/health/products/storage/USDA requests passed. The initial
network-none qualification used synthetic data only. See `deployment.json` and `launch.json`.
The full supermarket controller has now finished with holds, releasing the assistance phase.

The initial assistance import was blocked by the inherited 50 GiB installation quota against
approximately 116 GiB of existing retained data. Idle passes incorrectly hid the outstanding
failure as finished. Fixed persistent source-status reporting, allowlisted safe budget failure
reasons, and an explicit 256 GiB worker quota (5 GiB free reserve, unchanged small source caps).
Regression exercises a real mocked quota failure and verifies it remains visible next pass.

Only the assistance worker was replaced with frozen recovery release `c70c937a…ae6cf83`,
campaign `food-assistance-after-small-states-20261022-r2`. Prior campaign, job and history are
retained. One explicit new job was enqueued. Two one-shot preparation helpers failed without
enqueuing (old package path, then default UID); enqueue succeeded through the worker's UID99.
Source jobs subsequently ran under the new quota. Recovery and rollback are in
`recovery-deployment.json` and the Tower service runbook.

**Actual live result:** Iowa OSM partition published **25 sites and 25 services**, zero dated
events, source clock `2026-10-22T17:37:51Z`. All25 have coordinates,13 structured streets,
5phones,3websites,3raw schedules, no independently verified records. These are sparse OSM
assertions, not a complete pantry census or proof of walk-in availability.23 operator targets
lack required identity/contact details; two eligible targets were held by existing crawl
history without new operator page requests. One duplicate candidate is retained for review.
Jev reservations/answers remain zero for this campaign.

A later state request failed transiently; the source job is `retry_wait`. The background
worker remains healthy with automatic retries and six-hour passes; the other12 states have
not yet published. A primary diagnostic returned502; a single separately reviewed Private.coffee
qualification timed out. No fallback rotation or restricted-source access was activated.

Direct authenticated Iowa assistance search now returns200. USDA/products/storage and existing
health endpoints remain200; unrelated pack refs match the pre-import snapshot and the735Iowa
store count remains. API/Bòrd/history container start times were unchanged during recovery.
See `runtime-verification-20261022.json`, `baseline-quality.json` and source job checkpoints.
Feed America,211 and jurisdiction imports remain rights/profile gated. USDA program metadata,
aggregate food-access analytics, operator moderation and the Bòrd food-assistance UI are not
implemented/activated here. The companion handoff is `docs/BORD-FOOD-ASSISTANCE-HANDOFF.md`.

Final validation: **437 tests passed in30.88s**, one existing Starlette/httpx deprecation warning;
`ruff check .`, OpenAPI check and whitespace check passed.64frozen Python files compiled on the
actual image with network disabled. Tower repository validation passed with existing generated/
sensitive-archive warnings. Isolated audit attempted; development VM unreachable, canonical
inventory untouched. No paid requests during this resume. See `checks.json`.
