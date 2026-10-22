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
