# Smaller-state scans — October 20 CDT / October 21 UTC, 2026

**Running on Unraid.** The first Wyoming branch passed Jev and published source-backed fields;
the serial controller will qualify and scan the remaining planned states. These are startup
receipts, not completed state coverage. Iowa's prior holds/STOP and all unrelated services remain.

## Ranked workload and scope

The owner requested states ranked by grocery-store workload. USDA FNS SNAP aggregate acquisition
validated publisher/schema, unique state/type keys, a stable source clock and 50-state completeness.
360 grouped rows sum to the independently queried 248,622 SNAP records across all included formats.
The grocery-format subset uses Grocery Store, Supermarket, Super Store and Large/Medium/Small
Grocery Store classifications. The counts below are **planning proxies**, before retailer-name
exclusions and reconciliation, not all physical groceries or a verified census. Non-SNAP shops
and broad/ambiguous source classifications limit them. DC/territories are excluded.

| Selected state (smallest first) | SNAP grocery-format records | Retained ATP assertions | Published canonical stores before |
|---|---:|---:|---:|
| Wyoming | 91 | 43 | 15 |
| Alaska | 135 | 54 | 17 |
| Vermont | 151 | 61 | 6 |
| North Dakota | 185 | 43 | 12 |
| Delaware | 197 | 83 | 17 |
| South Dakota | 221 | 46 | 18 |
| Montana | 246 | 82 | 19 |
| Rhode Island | 255 | 47 | 14 |
| New Hampshire | 256 | 140 | 28 |
| Hawaii | 283 | 77 | 10 |
| Idaho | 290 | 133 | 35 |
| West Virginia | 297 | 138 | 79 |

Full [50-state CSV](ranking.csv), [JSON ranking](ranking.json), [executed notebook](sizing.ipynb)
and [frozen plan](plan.json). The notebook reproduces all 50 ranks, aggregate totals and batches
without network calls, mutation or activation. Acquisition raw bodies/hashes and five bounded,
contact-identified source requests are retained under
`/data/operator-imports/small-states-20261020/ranking/`. No retailer requests or paid calls were
needed for ranking. Source: [USDA FNS SNAP retailer layer](https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0).
The layer's actual data clock and acquisition time are preserved in `snap-groups.json`.

**Quality assessment:** high-confidence source-grain counts, suitable for initial scheduling;
not suitable as an exact all-grocery denominator. Retained ATP's missing independent grocers,
partial/failed spiders and different inclusion rules explain much of the count difference.
Do not subtract the columns to claim exact missing locations or use them as comparable coverage
percentages. Next remediation is per-state SNAP/OSM/license reconciliation and official URL
acquisition; none is implied by the aggregate ranking. Scope classification and branch identities
remain checked during import/crawl. The snapshot is dated, not a real-time operating-status audit.

## Five serial batches

At most three similarly sized states and approximately 650 reference records per batch; twelve
states total. A single worker executes them serially, sharing host counters and model reservations.

| Batch | States | SNAP reference workload |
|---|---|---:|
| 1 | WY, AK, VT | 377 |
| 2 | ND, DE, SD | 603 |
| 3 | MT, RI | 501 |
| 4 | NH, HI | 539 |
| 5 | ID, WV | 587 |

Initial scan input is the **already retained** pinned ATP archive roster: 947 source assertions
across these states. No new full ATP/SNAP/OSM retailer-location download was performed. Existing
canonical/source data, source-format exclusions and identity holds mean actual accepted records
and crawl targets differ. No branch URLs, phones, hours, closure or missing stores were invented.

## Implemented execution

[Operator guide](../../SMALL-STATE-SCANS.md). Shared field runners now accept an explicit state,
with exact source/address binding on every target. Existing Iowa configs and policy remain valid.
The Alaska/other states do not receive a guessed state-wide timezone where multiple zones exist.
Generic profiles, evidence-v4 reconciliation, parser-v9 contact panels and corrected Jev excerpts
carry over. No new model API or image pipeline was added.

The controller preserves a consistent backup, imports **only new native ATP identities** with
partial-scope provenance and no absence/closure evidence, then reconciles selected-state fields.
Existing/co-located/uncertain assertions are retained as review items. Canonical IDs/native keys
stay stable on replay. Original source properties, dates, attribution and existing source records
remain intact. Each state gets a host-diverse <=5-page Jev-reviewed pilot before <=25-page chunks.
If no pilot page publishes, the rest of that state is held and other planned states can proceed.
Jev is selective after qualification. Budget exhaustion pauses the whole controller.

Persistent history holds, failures, interrupted attempts and per-state gaps survive. URL reuse
between identities is held. One bounded canonical redirect follow-up still requires fresh robots
and exact identity. No automatic blocked-host retry, blanket redirect relaxation or IP rotation.
Operator STOP propagates to an active child. The worker does not restart automatically; resuming
requires explicit `--run --resume` with the same plan and shared data. The latest staged resume
release additionally rejects incomplete backup directories and incomplete state-phase summaries; the running initial release created
a fresh backup, which was independently verified complete before this report.

Pacing: 500 attempts/day/hostname shared across states, 45 seconds plus uniform 0–45 seconds or
stricter robots, contact hello@foldlab.app, bounded HTML. The **existing $15 cumulative Jev cap**
applies to all states together; no extra budget was authorized or configured. The first new Jev
reservation was $0.01 (prior ledger $3.89). Reservations are not provider billing. No OpenAI job,
images/PDF downloads, full inventory, product pagination or prices. Map/aisle/department/contact
source evidence is retained where present; reviewed mappings and independent media rights keep
their existing gates.

## Actual startup and publication

Container `bord-food-small-states-20261020` started **2026-10-21 00:29:23 UTC** (October20 CDT),
UID99:100, 1 CPU/1GiB, read-only root/source/config, existing pinned image and protected read-only
Jev key mount. API/Bòrd/history were not restarted or reconfigured. The initial running source
release is `a1a566edb7e2e8e6b6794b12903a180761a3a6d0b4b2ad4a2cb944af8ae80a35`.
The latest future/resume source is separately recorded in `latest-staged-release.json` and Tower's
`config/small-states-20261020/release.json`; running immutable code is not overwritten in place.

Consistent backup: `/data/backups/before-small-states-20261020`, with original catalog/control,
frontier, history and Jev SQLite snapshots. Network-none verification checks current pack paths,
required schema tables and SQLite integrity; passed. A future resume does not assume that an
empty/half-written backup directory is complete.

Wyoming's first partial import added **27 new native stores**, retained16 existing/uncertain
source assertions, and reconciled42 canonical Wyoming stores. It prepared30 eligible branch URLs
and12 held/missing-URL records. Generation `g_3aa3d89073f34ceda13a94d842e6f2cb` preceded the first
live page; generation `g_ad8764b3f78141dba153fea5e48f1443` captured the first branch publication.
The first pilot checkpoint had one published, one running and three pending, with one answered
Jev decision. This is proof of live requests/model use/publication, not a claim of full-pilot or
all-state completion. A later checkpoint confirms Wyoming's pilot completed with three published/two host-blocked and the 25-target chunk started. Subsequent results remain in the durable live statuses.

Parent: `/data/crawl-campaigns/small-states-20261020/status.json`. State import/target/gap/config
receipts are underneath it; each child campaign has durable page evidence and per-target outcomes.
Other states outside these twelve remain staged. Source/API modules and frozen plans are on
Unraid and mirrored to Tower; no Git commit/push/image publication was performed.

## Verification

412 offline tests passed in72.35s with one existing Starlette deprecation warning. Tests cover
ranking grain/count reconciliation, batch bounds, old native IDs/co-located holds, publication
preservation/replay, cross-state source identity/shared URL holds, failed-pilot continuation,
backup completeness and unchanged 500/day gates. Full suite uses fixtures/mocked sources; the
explicit live actions above are separate. Ruff/format, unchanged OpenAPI, plan/Tower and diff
checks are recorded in `checks.json`; both notebook cells executed and reproduced the plan.
Actual pinned-image network-none preflight passed for all twelve states, with zero source/model
calls or publication. Earlier local planning/import-loader mistakes were corrected before the
worker launch; the preflight/launch artifacts record the successful validated input.

At the live checkpoint, all original9,315 raw IDs/source_records/source_refs remained, 9,039
non-selected-state payloads were identical, including all735 Iowa stores; unrelated pack refs
were unchanged. API live/ready/health, Wyoming stores, products, storage guidance and legacy FDC
returned200. API/Bòrd/history healthy, original starts retained, zero restarts/OOM; worker running
with no OOM/restarts. See `live-verification.json` and `runtime-verification.json` for exact clocks.

Tower audit was isolated: development VM unreachable exit255, canonical inventory not replaced.
Forgejo TWR-057 creation returned HTTP502; no remote issue was created. The issue remains in Tower ISSUES.md. No companion/viewer changes,
whole-US activation, new licensed source, extra OpenAI job, OFF repair or FoodKeeper activation.
