# Repeatable store phone and hours enrichment

The October 20 [execution report](investigations/iowa-contact-improvements-20261020/RESULTS.md)
records actual Iowa publications, pilot holds and unperformed activation. These changes extend
the [chain quality profiles](STORE-QUALITY-PROFILES.md); they do not establish a complete census.

## Order of operations

1. Preserve the current immutable generation, control identities, frontier, history and model
   reservation ledger. Stop an older writer gracefully before repairing the same cohort.
2. Reconcile retained source assertions before requesting more pages. Prepare with
   `python scripts/enrich-retained-stores.py --data-dir /data --state IA --run-dir /operator/retained-plan`.
   Check the CLI help for retained provider inputs and the separate `--publish` switch.
   Publication is generation-fenced under the normal worker lock and replaces the store pack.
3. Resolve missing official URLs using exact-address source panels. The offline discovery CLI is
   `python scripts/discover-store-sites.py --data-dir /data --state IA --html /operator/directory.html --source-id ncg --source-url https://www.ncg.coop/find-co-op --retrieved-at SOURCE_ACQUISITION_EPOCH --output /operator/candidates.json`.
   The epoch must be the real acquisition time, not the time of reparsing. Acquisition itself
   must use the reviewed source transport, robots policy, shared counters and pacing.
4. Review candidate websites, site scope and exact premises. A directory link is a lead, not a
   published website, branch match, single-store-site declaration or crawl permission. Retain
   observed HTTP URLs as HTTP until an actual redirect or official review supports a change.
5. Run a small explicit field campaign. Inspect saved source evidence, extraction, Jev decisions,
   branch identities and accepted field gains. Fix parsers with offline positive and wrong-branch
   fixtures before testing another group. Preserve every real failure and history hold.
6. Activate a wider missing-field pass only after useful pilot gains. The optional
   `scripts/run-store-field-plan.py` serial controller requires an explicit plan and `--run`;
   it gates on new accepted phone/full-week hours, supports another per-phase gain gate and
   propagates operator STOP to an active child. Its default invocation is staging only.

The current Iowa staged plan is held because the live pilot added no accepted **missing** phone
or full-week schedule. A successful existing-store refresh alone does not pass that gate. Do not
clear the hold or repeatedly submit identical model questions to make the pass proceed.

## Parsing and field meaning

- Explicit schema times such as `9am` and `8pm` normalize without guessing ambiguous clocks.
  Dayless OSM time selectors have OSM's daily meaning; dayless retailer text does not.
- A full-week source can fill unknown days when every partial report agrees on its covered days.
  This remains `source_reported` for the full schedule. Partial sources do not independently
  verify days they never reported. Actual disagreement remains a conflict.
- Hours provenance exposes `covered_days`, `unknown_days` and `complete_week`. Existing evidence,
  conflict history, lineage, source observation/acquisition clocks and raw source records survive
  reparsing. An import time is not a new verification date.
- Known ALDI customer-service numbers remain chain contacts. Other ambiguous ALDI toll-free
  contacts are held from new branch promotion. `contact_channels` retains numbers and scope;
  `contact_channels.phone.direct_branch_contact=false` marks selected legacy routing contacts.
  A provider pharmacy/fuel/vision/garden phone does not become a supermarket main phone.
- Explicit daily/weekday text and identical repeated weekly rows are supported. Conflicting
  duplicate schedules, unsupported day semantics and bare opening/closing ranges stay unresolved.
- Generic corporate/nearby/footer data remain excluded. A reviewed single-premise contact footer
  or reviewed multi-branch footer panel needs an exact store/address-bound proof. Nested panels
  can supply one branch's phone; another branch or administrative office cannot supply its facts.
  Hidden text remains excluded. Jev receives the actual selected source panel and raw title,
  including an explicitly selected footer, rather than an empty excerpt or invented identity.
- Jev helps decide branch consistency; it neither invents field values nor independently verifies
  them. A low-confidence result remains held even if the deterministic parser found valid fields.

## Carryover to other states

The normalization, compatible-schedule rule, contact-scope rules, reviewed HTML panel parser and
`public_contact_panels` / `awg_public_locations` platform classification are shared code. Existing
versioned chain profiles continue to choose main-store contacts and separate department hours.
Full state names work in exact address panels; Nebraska fixtures exercise the behavior outside
Iowa. Retained OSM records can rejoin a uniquely name-compatible, normalized exact premises after
address cleanup, without creating another store or claiming a reviewed crosswalk. An explicitly
selected state's bundle is not hidden by a later-staged different state's bundle.

Discovery supports retained NCG, IGA and operator-reviewed civic directories. It requires a
distinctive name token and exact street/city/postcode binding and emits source/path/hash evidence.
Observed same-origin contact/location/about links are retained as a bounded review queue; they
are not followed automatically. A chain homepage and a store-specific URL remain distinct.

For each next state, obtain and review current licensing/WIC/directory sources, source reuse
terms, taxonomy and a denominator; then prepare its own candidate review and pilot. The shared
helpers do not activate a state, fetch an unreviewed source or establish that a license/benefit
record is a current operating supermarket. See the existing
[state source research](STORE-QUALITY-PROFILES.md#state-level-source-priorities).

Iowa retains 500 attempts per hostname per day, 45–90 seconds randomized spacing or stricter
robots delay, the existing contact identity and cumulative $15 Jev reservation ceiling. There
are no product inventories, prices, images or another OpenAI submission in this change. Other
states require their own activation. The original execution was explicitly Iowa-only; the
subsequent owner-authorized [small-state scans](SMALL-STATE-SCANS.md) extend the shared runner
to explicitly selected states, with the same per-branch validation and policy gates.
