# Iowa phone and hours improvements — 2026-10-20

Implemented and published retained-source improvements; live contact discovery and a small
pilot completed. Wider crawling is **held**, not running. Shared helpers and fixtures cover
other states, which remain staged. No Bòrd companion or viewer changes were made in this pass.

## Published result

The same 735 canonical Iowa stores before/after repair, using the backed-up serving generation:

| Field presence | Before | After | Gain |
|---|---:|---:|---:|
| Phone | 502 | 508 | 6 |
| Website | 474 | 479 | 5 |
| Opening hours | 312 | 365 | 53 |
| Complete seven-day schedules after repair | — | 351 | — |

These are presence counts, not a claim of 508 independently verified direct branch phones.
Fifty selected legacy phone contacts are explicitly marked non-direct; their retained evidence
and contact scope are available to consumers. All 735 stores have a structured address and
derived timezone; 695 have coordinates. The independent/unmapped cohort remains weak:
336 stores, 142 phones, 108 websites and only 18 hours records. There are still 255 unresolved
URL gaps in the staged missing-field plan. Holiday exceptions, entrances and reviewed aisle
category mappings remain empty. This is progress, not complete Iowa coverage.

Two immutable retained-data publications:

- `publication.json`: generation `g_84e5924b7f2942b5bc1309161acfdddf`, 735 metadata updates,
  504 phones / 475 websites / 343 hours / 329 complete weeks.
- `tail-publication.json`: generation `g_181575524c2f4786ba0a581d6eeb727c`, 24 further updates,
  508 phones / 479 websites / 365 hours / 351 complete weeks. This adds the exact retained OSM
  joins after address cleanup. Each publication made zero source or paid requests.

The original optimistic `offline-plan.json` is superseded by `revised-offline-plan.json`:
preflight caught chain customer-service/toll-free contacts that must not inflate branch gains.
Seven Sam's Club schema schedules became parseable, but conflicting hours remain held; they are
not seven extra accepted schedules. Compatible partial/full reports retain their conflicts and
source clocks and do not falsely corroborate unreported days.

Backup: `/data/backups/20261020-before-contact-improvements`, including the prior generation,
control/frontier/history/Jev ledgers. The compact `before.json` records its original workstation
snapshot hash; the full catalog remains recoverable on Unraid.

## Reusable changes

See [the operator workflow](../../STORE-CONTACT-IMPROVEMENTS.md). Implemented shared schema
meridiem parsing, source-specific OSM daily semantics, compatible partial-week reconciliation,
covered/unknown-day metadata, phone scope handling, exact retained source joins, official-site
candidate queues and observed contact follow-ups. Reviewed contact panels handle nested branches,
single-premise footers, full state names and identical duplicated schedules. Wrong branches,
administrative office contacts, hidden text and unsupported weekdays remain excluded.

Evidence version is `store-field-evidence-v4`; the latest parser is `branch-fields-v9`.
The field-plan controller requires accepted missing-field gains before advancing phases, with
state/campaign checks, STOP propagation and an optional second pilot gain gate. These are reusable
mechanisms; the current execution runner remains Iowa-only. No national campaign was activated.

## Actual live tests and retained failures

The previous `iowa-quality-continuation-20261020` was stopped gracefully before offline repair.
Its final primary outcomes remain 22 published, 15 review, 26 blocked hosts, one interrupted,
133 pending and 258 URL gaps. The STOP, histories, counter ledgers and actual failures remain.

Directory discovery requested four public directory documents over the approved transport:
NCG, IGA, Hartley civic and a later NCG parsing check. Existing robots, 500 attempts/host/day,
45–90-second randomized spacing or stricter robots delay apply. Two earlier source-paused
preflights failed before HTTP and are retained in `directory-preflight-failures.json`.
The NCG document yielded four exact-address website candidates; HTTP leads were preserved rather
than silently rewritten to HTTPS. IGA's first directory page was not an Iowa census. Hartley's
civic and retailer address/hours disagreement stayed unresolved; no address was guessed.

`iowa-contact-pilot1-20261020` fetched five branch pages and used five Jev decisions:

- Earlham control published a fresh phone/website/hours observation, without a new presence gain.
- Oneota, Wheatsfield and New Pioneer Coralville had exact extracted branch evidence but low
  Jev confidence, so were held.
- Valley Fresh had a confident model answer but no deterministic exact-address panel, so was
  held. A model cannot replace that binding.

The pilot exposed a review-context defect: footers accepted by the bound parser became empty
text in the general model excerpt. Fixed in v9; nested branch phone selection and hidden-footer
negative fixtures were added. A single explicit re-review of three unchanged retained pages
used the corrected source context, without another retailer request. Confidence improved to
0.66 Oneota / 0.64 Wheatsfield / 0.16 Coralville, still below 0.8. All three remained held. No
threshold was lowered, source retrieval clock refreshed, failure erased or identical model
question repeatedly retried. `context-review-result.json` records both reviews.

Eight new Jev requests reserved $0.08. The durable ledger has 389 answered reservations totaling
$3.89, plus the existing $0.0001 prior-pilot allowance, below the owner's cumulative $15 cap.
Reservations are conservative ceilings, not measured provider billing. No OpenAI request was
made; the previous $2 pilot remains separate. No images, inventories or prices were collected.

The second 15-store pilot and six-target wider missing-field pass passed actual-image offline
configuration validation and are staged. The larger plan accounts for 735 stores as six URL
targets, 255 explicit URL gaps and 474 preserved prior/pilot/already-complete outcomes.
The network-disabled controller check returned `held_requires_review / pilot_gain_gate_not_met`
with zero accepted new phone/full-week-hour gains from the first pilot. Neither follow-up phase
was launched. The next work is reviewed official contact/location evidence for independents,
plus current licensing/WIC/address sources where useful; another broad retry would not resolve
the missing-source and model-review gaps.

## Direct verification and limits

`live-verification.json`: all 9,315 raw IDs, original source records and source refs retained;
8,574 non-Iowa payloads identical; unrelated pack refs unchanged; four redirects and two scope
exclusions preserved. Live/ready/health/stores/products/storage guidance/legacy FDC returned 200;
missing API key returned 401. The serving generation was stable across verification.

Only the API was recreated to load its reviewed v4 reconciliation modules, on the existing pinned
image. Bòrd and history starts are unchanged, healthy, zero restarts/OOM. API activation receipt
identifies its frozen source release; pilot v8, corrected re-review v9 and latest staged source
releases are separately recorded. There was no Git commit/push, image publication, companion
deployment, viewer deployment or environment-key change.

Actual local verification: 403 tests passed in 74.83 seconds, with one existing Starlette
deprecation warning; latest retained-state fixture tests passed separately (2/2). Ruff check
and 207-file format check passed. Final OpenAPI/diff/package/Tower checks are in `checks.json`.
Routine tests use fixtures and mocked transports; the live actions above are separate evidence.

Tower audit ran from an isolated copy: VM `192.168.0.30` was unreachable, exit 255. Canonical
inventory was preserved. Forgejo issue creation returned HTTP 502, so TWR-056 is recorded locally
and no remote issue is claimed. Existing OFF duplicate-source-key and full FoodKeeper 403 issues
remain separate; product, USDA and storage guidance publications were preserved.
