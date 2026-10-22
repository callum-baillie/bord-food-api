# Iowa identity, addresses and repeatable field review — 20 October 2026

Owner requested Iowa-first identity/scope repair, structured addresses and missing coordinates,
then dependable independent-store phone/hours, reusable chain profiles and a bounded post-pass
OpenAI workflow. Authorized one separate OpenAI pilot up to $2; existing selective Jev ceiling
remains $15 cumulative. Pricing/full inventory remain deferred; other states remain staged.

## Published cleanup

The old field campaign stopped gracefully, retaining its STOP marker, history, actual failures,
request counters and holds. Consistent pack/control/frontier/Jev/history backup:
`/data/backups/20261020-before-iowa-quality-repair` (SQLite quick_check passed).
Network-disabled actual pinned Python 3.12 image preflight passed before scoped API activation.

Quality generation `g_f52eb66ba2894a149ea9190498af0808` retained 9,315 raw store IDs, merged four
reviewed duplicate pairs through redirects and excluded two Hy-Vee Fast & Fresh convenience
formats from ordinary directory/search. Source records remain retained, including direct lookup
of excluded IDs; exclusions do not claim physical closure. The directory now contains **735
canonical in-scope Iowa stores / 9,309 nationally**. This is an observed directory, not a proven
complete active-grocery census. Ambiguous formats and unresolved identity candidates need review.

All 735 Iowa addresses have explicit street/city/region/postcode, parsed from retained source
text without guessing. **695/735 (94.6%) have coordinates**, versus 616/741 raw rows before this
repair. Exact identity/address-bound retained SNAP/OSM/Overture points filled gaps; a reviewed
same-branch alias preserved one existing point. Forty canonical stores remain without points,
including conflicting provider points held rather than arbitrarily selected. Points carry
provider precision/lineage/clocks, not an entrance/rooftop guarantee or independent verification.

Six reusable versioned profile families cover Hy-Vee/Dollar Fresh, Fareway, ALDI, Walmart, Target
and Albertsons/Safeway/Jewel, plus a conservative independent fallback. They apply on future
source imports/extraction in other US states; no other-state rewrite/crawl occurred. Rules retain
original values, separate main/pharmacy contacts and store/department hours, identify known chain
contact numbers and never relax robots, rights, pacing or source-binding gates. Independent exact
address contact panels are supported; navigation/footer/nearby-store panels are excluded.

One accidental duplicate publication invocation was rejected by the stale-generation guard after
the first succeeded. It did not publish twice. Four alias reviews are payload-bound and survive
subsequent source imports. Alias registry updates precede serving publication under the existing
identity design; the catalog itself is replaced and atomically published.

## Coverage at the final read-only check

| Field | Canonical Iowa stores | Coverage |
| --- | ---: | ---: |
| Structured street/city/state/postcode | 735 | 100% |
| Coordinates | 695 | 94.6% |
| Phone present | 498 | 67.8% |
| Website present | 474 | 64.5% |
| Normalized weekly hours + derived timezone | 311 | 42.3% |
| Derived IANA timezone | 735 | 100% |
| Provisional branch emails | 84 | 11.4% |
| Departments / accessibility | 11 / 10 | 1.5% / 1.4% |
| Pickup / delivery link | 1 / 1 | both unverified |
| Dated holiday exceptions / reviewed entrances / aisle mappings | 0 / 0 / 0 | unresolved |

Presence is not dependable independent verification. For the same surviving 735-store cohort,
phone/website/hours presence was already 498/474/311 before this repair. The lower totals versus
the previous 741-row report reflect aliases/exclusions, not six newly lost stores. This pass has
not yet increased these three presence counts. There are 218 retained conflict entries across
183 stores. Among 336 independent/unmapped stores, only 140 have phones, 107 websites and 16
normalized schedules. This remains the priority quality gap; no claim it is fixed statewide.

## Iowa continuation: running, not complete

Worker `bord-food-iowa-quality-continuation-20261020` started **20:16:59 UTC**, healthy process
with zero restarts/OOM, first actual requests/Jev review/publication observed. Config accounts
for all 735: **197 pending/deferred URLs / 64 hosts**, **258 explicit URL gaps**, **280 preserved
prior outcomes**. Independents go first. Earlier successes, blocked and interrupted targets are
not silently retried. Final snapshot: one publication, three host blocks, two review holds,
190 pending and one active request. These are point-in-time values; consult status files.

500 attempts/day/hostname, 45 seconds plus random 0–45 seconds or stricter robots; shared
frontier/history/lease/budget, conditional caching and bounded HTML. Selective Jev remains within
its independent $15 cumulative ceiling (366 answered reservations / $3.66 ledger reservation at
check; not measured billing, prior pilot allowance is also charged by policy). No images,
assets, product inventory, price collection or IP rotation. Other states stay inactive.

Parent `/data/crawl-campaigns/iowa-quality-continuation-20261020/status.json`; child suffix
`-primary/status.json`. Stop this worker only:

```sh
touch /mnt/cache/appdata/bord-food-api/crawl-campaigns/iowa-quality-continuation-20261020/STOP
```

API/Bòrd/history should remain running. Old campaign's STOP stays in place. The continuation's
optional post-pass hook prepares a review plan once, without submitting another paid job.

## OpenAI pilot: completed and imported

One Batch job, **nine actual inference requests**, pinned `gpt-5.4-mini-2026-03-17`, no tools,
images or external searches. It covered 195 store records; 16 were explicitly deferred by request
caps, and 524 had no eligible source evidence. This does not fetch unknown facts about those
524 stores. The key stayed at the viewer's original workstation env-file path, in memory only;
it was not copied to Unraid/browser/catalog/config/logs.

The separate $2 pilot reserved **$0.586806 conservatively**, using standard rather than discounted
prices and upper bounds. This is a reservation, not actual billed spend. All 9 requests completed
with zero provider failures. A bounded collector downloaded the existing job's results, then a
network-disabled actual-image importer published generation
`g_6eb2c482429e4ffea718312cca563593` after taking the normal worker lock.

**26 store records changed:** 13 phone, 12 website and one weekly-hours evidence extraction.
**19 proposals held:** 10 quotation mismatches, three invalid values, three unbound documents or
fields, two incomplete weekly schedules and one changed store. Accepted evidence retained source
identity/lineage/clocks; the model did not add an independent vote. Existing conflicts remain.
These updates mostly improved retained evidence, not the aggregate missing-field counts above.

Exact quote membership, store/document/field binding, unchanged revision/name/address,
normalization/value equivalence, contact scope and seven-day hours gates apply before publication.
No invented coordinates, holiday exceptions, physical closure or identity merges. Results and the
reservation ledger are retained under protected workstation state
`~/.local/state/bord-food-api/openai/` (0700 directories/0600 files), and public-source results on
Unraid under `/data/operator-imports/openai-IA-quality-pilot-20261020`. No additional paid pass
is automatically activated or submitted. Lifecycle and extensibility: [operator guide](../../STORE-QUALITY-PROFILES.md).

## Reproducible releases and preservation

Existing pinned image unchanged:
`sha256:169264bb538c8add672750b01d0124489237e1cc7379c24975915466a8e3ded3`.
No new image publication/Git commit/push.

- API read-only quality modules: `f0ac4749fec92c64764c1681f22a5716117d4e5d558620b7479704192d687dac`.
- Active continuation frozen profile runtime: `ddd091a124469eb90bc716cafa9a7880227238044193b7fb2c66ca57128017fd`.
- Future/replay frozen release: `393dc6d9a10d4a0ef3c03ebd19c83766beebe1657e155e9a34b802a684aa81f4`.

The latest release labels profile-aware extraction `branch-fields-v7`; the active frozen runtime
already contains the functional profile parser before that metadata-only label bump. Eight
previously approved retained pages replayed with original clocks/hashes, zero HTTP/model calls:
Jewel, Save A Lot and Hy-Vee changed; three others unchanged; Wheatsfield/Earlham ambiguous and
held. Earlier approved matching outcomes were not automatically carried over to ambiguous pages.

Final checks proved all 9,315 raw IDs and original source_records/source_refs retained, all 8,574
non-Iowa payloads identical, four old-ID redirects correct, two excluded direct lookups retained,
all non-store pack references unchanged. Live/ready/health/stores/products/storage-guidance/legacy
FDC search returned200; missing key401. An initial operator probe used nonexistent `/v1/guidance`
and correctly returned404; corrected documented `/v1/guidance/storage` returned200. API/Bòrd/history
healthy, zero restarts/OOM; only API recreated, Bòrd/history start times unchanged.

No companion implementation/deployment here. Viewer collector now excludes scope-excluded rows
from dashboard denominators; no frontend deployment or key-file edit. Products455,458, official
chart guidance49 and USDA foods469,046 unchanged. OFF retained worker failed Duplicate source key
after597,000 selected before publication; full FoodKeeper403 remains unresolved. Neither repaired
here. No pricing connector, nationwide activation or live geocoding request.

## State sources and remaining work

Official source research is recorded in [state-sources.json](state-sources.json). Iowa DIAL/SAFHER
food-establishment licensing is the highest-value next identity/classification denominator, but
no reviewed complete bulk export was acquired. Iowa WIC and liquor-license data can corroborate
format/identity with clear temporal limits; inactive benefit/alcohol authorization is not store
closure. A found WIC PDF is July2022, not proof of current membership. State/county address points
and Census batch geocoding are coordinate fallbacks requiring approximation metadata; no live
Census request was sent. NY/Michigan license sources are research only, not activated adapters.

Missing independent branch URLs, authoritative licensing scope, conflicting coordinates and
holiday/access/aisle evidence remain open. The evidence-only AI design cannot replace acquisition
of missing facts. Crawl failures/holds persist for future runs and states.

## Actual validation

`.venv/bin/python -m pytest`: **388 passed, one upstream Starlette warning, 16.31s**.
Ruff check and 195-file format check passed; generated OpenAPI and git diff checks passed.
Tests use synthetic fixtures/mocked transports. Actual-image isolated publication preflight passed.
Viewer: six Node/eight Python tests, production build, Prettier check and 13 browser tests passed
(browser21.6s); collector/test Ruff passed (format with project's existing100-column style).
Plan package, Tower validator, isolated audit and Forgejo receipts are recorded in checks.json.
The audit's VM-unreachable exit255 did not modify canonical inventory. No claim of full census
coverage or completed statewide crawl is made.
