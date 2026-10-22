# Small-state grocery scans

The owner authorized smaller-state activation on October 20, 2026. The current campaign is
`small-states-20261020` on Unraid, separate from the stopped/held Iowa campaigns. Its
[ranking and run evidence](investigations/small-states-20261020/RESULTS.md) distinguish the
reference counts, retained source coverage, actual requests, publications and remaining gaps.

## Sizing and batching

Rank the 50 states by USDA SNAP records classified as Grocery Store, Supermarket, Super Store,
Large/Medium/Small Grocery Store. This counts SNAP-participating grocery-format records before
brand-level exclusions, not every physical grocery or a reviewed census. Nonparticipating
independents are absent; some prohibited retailer formats can still appear in a broad source
classification. DC and territories are outside this state list. Keep ATP assertions and the
published canonical directory as separate columns; never subtract these mixed sources to claim
an exact missing-store count.

The source acquisition verified FNS publisher identity/schema, a stable data clock, unique
state/type groups, all 50 states and aggregate totals against an independent count query.
Raw request receipts are on Unraid at
`/data/operator-imports/small-states-20261020/ranking/`. The
[executed sizing notebook](investigations/small-states-20261020/sizing.ipynb),
[50-state CSV](investigations/small-states-20261020/ranking.csv) and frozen activation plan make
the ranking reproducible without further source requests.

The first 12 smallest states form groups of at most three states, approximately 650 reference
records per group and no more than a 2.2-fold size difference within a group. The worker scans
states and groups **serially**; grouping is workload planning and reporting, not concurrent
requests or separate host quotas.

## What the worker does

`scripts/run-small-states.py PLAN` only inspects the explicit plan. `--run` activates it;
`--resume` is additionally required to continue an existing campaign. It does not choose more
states later, extend budgets or start on a timer. The plan is limited to 12 explicitly selected
states, excludes Iowa, and pins the retained nationwide source bundle/archive hash.

Before the first write, a consistent catalog/control backup and SQLite snapshots of the shared
frontier/history/Jev ledger are retained under `/data/backups/before-small-states-20261020`.
Each state's source roster is hash checked. Only new native ATP identities are imported;
existing native records remain untouched by roster import. Co-located compatible candidates,
missing structured premises and excluded formats remain review items. These are partial,
additive imports under `all_the_places:operator-small-state-STATE`; `complete=false`, original
spider/native IDs, CC0 attribution, raw source properties and the dated source run are retained.
They do not certify the ATP spiders as complete or infer absence/closure.

Selected-state fields then use the shared chain profiles, structured-address cleanup,
contact scopes and evidence-v4 hours reconciliation. Source-run clocks do not become current
survey/verification dates. Split-zone states do not receive a guessed state-wide timezone.
Every import checks existing native records, unrelated states and unrelated pack preservation;
publication replaces immutable catalog packs under the normal worker lock.

Eligible source-supplied HTTPS branch pages are selected from the canonical directory. Generic
homepages, missing addresses, URLs shared between identities and durable prior holds stay gaps.
Each state starts with up to five host-diverse pages, with Jev review on each. A pilot with no
accepted published page holds the rest of that state and proceeds to the next planned state.
The remaining branch queue runs in chunks of at most 25. Jev remains selective after the pilot
(ambiguous/new proof cases and deterministic sampling); confidence and exact-address gates are
unchanged. Observed canonical redirects may get one bounded separately checked follow-up;
other denied/blocked requests and historical holds are not retried automatically.

The latest shared field runner accepts an explicit state; the legacy `run-iowa-*.py` filenames
are retained for compatibility. State identity validation still applies to every branch and
gap; the old Iowa configs are not rewritten or restarted by this activation.

## Persistent state and policy

- One shared data root: host `/mnt/cache/appdata/bord-food-api`, mounted `/data`.
- One serial controller, 500 attempts/day/hostname shared across all states and runs, 45 seconds
  plus random 0–45 seconds between requests or stricter robots delay. Existing counters remain.
- Real operator contact `hello@foldlab.app`; fail-closed robots, public address pinning, scoped
  source URLs, no login/endpoint guessing/IP rotation. Owner public-page authorization is
  separate from retailer terms or permission for media reuse.
- Existing cumulative **$15 Jev reservation ceiling**, not $15 per state or group. Each child
  also has bounded call/reservation limits. Exhaustion pauses the whole plan without increasing
  the budget. Reservations are not actual billing. No OpenAI submission or image analysis.
- Store details, contact/hours, department/accessibility and map/aisle evidence where present.
  No full inventory, product pagination, prices, image/PDF downloads or inferred aisle mappings.
- Persist parent/state/child status, per-target histories, review holds, source evidence and
  HTML only where retention is allowed. An accepted page is not proof of complete field coverage.

Parent status: `/data/crawl-campaigns/small-states-20261020/status.json`. Each state has a source
review, publication receipt, explicit target/gap list and frozen child configs beneath that
directory. Child campaigns have their own durable target outcomes and evidence. Source and
published-store gaps remain distinguishable, including states held after their pilot.

To stop gracefully, create `/data/crawl-campaigns/small-states-20261020/STOP` in the shared
data root; the controller propagates it to its active child. The worker has no automatic
restart policy. A restart/replacement retains data but does not implicitly resume requests.
Explicit resume uses the same plan/release/shared mounts with `--run --resume`; the parent
STOP must have been deliberately reviewed, and historical target holds remain intact.

Use the latest recorded operator release for an explicit resume. It validates required backup
files, schema tables and SQLite integrity, rather than treating an interrupted backup directory
as complete, and checks that every planned chunk completed before skipping a state. The initial running release created a fresh backup; a separate network-disabled
check verified it. Active and latest staged release hashes remain distinct in the receipts.

No new API image or Bòrd deployment is needed: the existing API reads the atomically published
store pack. The current operator release/config is recorded in Tower's
`stacks/productivity/config/small-states-20261020/`; do not launch an older frozen container
to obtain the new methods. The other states remain staged and inactive.

## Independent rough coverage targets

The October 21 [50-state planning estimates](investigations/state-coverage-estimates-20261021/README.md)
combine independent Census grocery/club establishment counts with the retained SNAP
aggregates. The [CSV](investigations/state-coverage-estimates-20261021/estimates.csv)
and [JSON](investigations/state-coverage-estimates-20261021/estimates.json) retain point
estimates, wide scenarios, both source counts and a dated catalog comparison. These are
AI-assisted, low-confidence investigation targets. They do not change the frozen activation
plan or running worker; reaching a count never establishes completeness or stops discovery.
Use address-level reconciliation, open-status checks, source overlaps and county/chain gaps
to assess actual coverage. Catalog counts are not inputs to the estimate calculation.
