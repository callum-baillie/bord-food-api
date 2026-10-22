# Rough state grocery-store targets

Created October 21, 2026. These are **AI-assisted, low-confidence planning estimates**
for all 50 states, not verified censuses or results of 50 model searches. Codex selected
an inspectable estimation rule from independent public anchors; no paid AI call was made.

[Open the report](report.html), [CSV](estimates.csv), or [machine-readable JSON](estimates.json).
The report contains a smaller-state comparison chart and a searchable state table.

## Scope and sources

Count physical general-line groceries and supermarkets, including independents, grocery
supercenters and warehouse clubs. Exclude convenience stores, dollar stores, standalone
pharmacies and specialist meat/produce shops. Source classifications approximate this scope.

- [Census 2023 State Business Patterns archive](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip):
  NAICS 445110 and 452311; use **only `lfo=-` totals**, never add legal-form subtotals.
  Downloaded October 21, 2026 without credentials; retained selected totals and archive SHA256
  in `census-state-counts.json`. All 51 jurisdictions validate against published national
  totals of 62,947 groceries and 7,961 clubs/supercenters. Excluding DC gives 70,728 combined.
  [Industry definitions](https://ers.usda.gov/data-products/food-environment-atlas/documentation).
  Census API returned a missing-key HTML page, so it was not used as data; the public bulk
  archive supplied the validated figures.
- [USDA FNS SNAP retailer service](https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0):
  reuse the retained, validated October 20 aggregate acquisition in
  `../small-states-20261020/ranking.json`; 61,369 grocery-format records across 50 states.
  These omit nonparticipating groceries and may include out-of-scope formats.
- `catalog-snapshot.json`: read-only, manifest-stable Unraid catalog snapshot at
  **October 21, 2026, 00:22:47 CDT**; generation recorded in file. Contains 9,554 canonical
  records across 50 states (DC excluded from comparisons). These are not all crawled,
  deduplicated, in-scope operating stores or field-verified records.

## Estimation and interpretation

For each state, let C = Census grocery + club/supercenter establishments and S = SNAP
records in grocery-format classes. Point = nearest 10 to `(2*C+S)/3`; lower scenario =
`floor(0.85*min(C,S)/10)*10`; upper scenario = `ceil(1.20*max(C,S)/10)*10`.
The closer Census industry definition gets more weight; newer SNAP counts provide a
cross-check. Weights and buffers are explicit judgment, **not calibrated statistical
confidence intervals**, validated growth estimates, or estimates of SNAP participation.
Both source clocks are retained. No extrapolated 2026 growth factor is asserted.

Results: **67,630** summed point targets, **51,770–85,270** summed scenarios. Iowa's
point is **710**, range **590–860**, versus **735** catalog records; 49 other states
are below their lower planning scenarios in this snapshot. Alaska, Vermont and New York
have material source disagreements (anchor ratio at least 1.4), warranting source/scope
review. Rounding is deliberate: precise-looking counts would overstate the evidence.

Catalog counts never enter the estimate calculation. Thus discovery success cannot
inflate the denominator to manufacture coverage. `catalog_to_target_ratio` is a count
comparison, **not verified coverage**; it is allowed to exceed 1. All rows retain
`census_complete=false`. Do not call `target - catalog` an exact missing-store count.

## Use in repeatable checks

Use the CSV/JSON as a versioned **soft investigation baseline**:

1. Below lower scenario: inspect missing counties, chain branches and independent stores;
   expand state licensing/inspection, SNAP and OSM discovery with correct format filters.
2. Within scenario: reconcile addresses, co-located identities, closed stores and scope;
   count agreement alone cannot establish completeness.
3. Above upper scenario: review duplicates, excluded formats and anchor undercoverage.
4. Track distinct operating stores and unresolved/closed/excluded records separately;
   report source overlaps and phone/hours/timezone completeness independently.
5. Refresh independent anchors periodically and retain previous estimate versions.

These files do not alter the API schema, live viewer, serving catalog, worker configuration,
state activation, host limits, evidence acceptance or budgets. The existing scan continues.
No deploy, Git push, retailer request, new OpenAI submission or Jev request was performed
for this analysis. Do not automatically use these values as crawl stop conditions.

## Reproduction and verification

Run `python docs/investigations/state-coverage-estimates-20261021/build-estimates.py` from
any directory with the correct path. It uses retained inputs only, checks 50 unique states,
102 unique Census jurisdiction/industry totals, national totals and range ordering,
and regenerates CSV/JSON and the report input. `analysis.ipynb` records the same computation.
The HTML is packaged from `artifact.json` through the analytics report renderer. Exact
runtime and test results are recorded in `checks.json` when complete.

Actual checks: **412 passed**, one existing Starlette/httpx warning, 148.03 seconds;
Ruff and diff whitespace checks passed. The first test run had four disk-reserve failures
on the small `/tmp` filesystem; the full rerun used a fresh disk-backed test directory.
Report input validation and packaging passed. Browser QA found an **8px horizontal
overflow in the shared renderer top bar**; the report remains readable, but browser
layout verification is not claimed to pass. This is recorded in `checks.json`.
