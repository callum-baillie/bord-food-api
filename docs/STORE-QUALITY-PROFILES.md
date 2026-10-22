# Repeatable store quality and post-pass review

Every future store source sync now applies versioned US chain rules from
`bord_food_api/chain_profiles.py`. Iowa cleanup is the first explicit publication;
other states have not been crawled or rewritten by this operation. Profiles are
extraction/normalization hints, never crawl permission or an independent source.

## Reusable profiles

Profiles cover Hy-Vee/Dollar Fresh, Fareway, ALDI, Walmart, Target and the
Albertsons/Safeway/Jewel family, with a conservative independent-store fallback.
They declare name/spider/domain matches, brand aliases, excluded formats, explicit
main-store phone labels, competing department-hours boundaries and known chain
contact numbers. Domain matches do not override robots, rights, host allowlists,
request budgets, branch binding or review holds. A new profile needs synthetic
cross-state examples and negative cases for other branches, departments and footers.

Common logic structures explicit full US postal addresses, retaining original text;
normalizes mailing suffixes/city spacing for matching; separates main/pharmacy phones;
and labels known chain contacts. Missing components are not guessed. Scope-excluded
convenience/pharmacy/specialist formats stay retained but disappear from normal store
lists and nearby search. Direct ID lookup still explains the exclusion. Exclusion
never establishes physical closure. The viewer's completeness denominator applies
these same scope exclusions.

Duplicate candidates require strong same-brand evidence. Shared corporate homepages,
chain phone numbers or co-located addresses alone cannot merge records. Publishing an
alias requires a review bound to both current payloads, a reviewer and reason. Existing
canonical IDs are preferred, losing IDs redirect, and native source assertions remain
retained. Existing identity registry decisions survive subsequent imports. The serving
catalog stays immutable: replacement stores SQLite, updated FTS and spatial indexes,
atomic generation switch. Stale plans fail their generation check. Other packs stay
unchanged. Out-of-scope/identity changes are distinct from permanent closure.

Coordinates are filled only from retained source assertions with exact name/address
binding and source clocks. Conflicting points over 150 m remain held. Existing points
are not replaced. Provider-reported points and reviewed-alias transfers carry source
IDs/URLs/clocks and precision, with null verification dates; they are not entrances or
rooftop measurements. No postal centroid, model coordinate guess or paid geocoder is used.

## Offline quality pass

```sh
PYTHONPATH=. python scripts/quality-stores.py --state IA --data-dir /data \
  --run-dir /data/operator-imports/quality-IA-PASS \
  --candidates /data/discovery/RELEASE/candidates.jsonl \
  --places overture_places=/data/discovery/RELEASE/places.jsonl
```

Default prepares `plan.json` without network/model calls. Review current bound duplicate
pairs, create an array of `{from,to,binding,reviewer,reason}`, and rerun explicitly with
`--reviews FILE --publish` against the same generation. The exclusive worker lock must
be free. Pause a crawler before changing its source-bound addresses/identities, then
prepare a continuation with fresh bindings. Never silently edit a running config or
reset shared request counters/holds. Historical completed, blocked and interrupted
attempts remain available; pending continuation does not recrawl prior successes.

Source refreshes preserve enriched fields, coordinate provenance and alias decisions.
Address parsing and profile rules apply to the next imports in every US state. A source
report still does not become independently verified merely because it is normalized.
Retained approved pages can be replayed without new HTTP/Jev requests after a structurally
parsed address change, only if normalized physical identity and the other binding checks
remain unchanged. Parser v7 adds profile-aware phone/hours and independent contact panels;
footer/nav/nearby content is excluded. The active continuation's earlier frozen profile
runtime remains reproducible by release hash; future/replayed v7 evidence records its version.

## OpenAI: bounded review after deterministic work

The selected approach is an evidence audit, not asking a model to invent a completed
state directory. Collect public data with bulk sources/permitted crawls first. Then
prepare **at most nine actual inference requests** in a single OpenAI Batch job. One
Batch submission containing thousands of requests would not meet this requirement.
No built-in web-search tool, per-store model loop, image request or unbounded automatic
retry is enabled. A later separate source-discovery step can propose research leads;
those still need acquisition and verification before publication.

Batch preparation focuses on missing/conflicted phone, website, email and weekly hours,
prioritizes independent/unmapped stores, and sends bounded source fragments with native
IDs, observation clocks and per-store revision/address bindings. It records both stores
without usable evidence and those deferred by byte/request caps. Large states carry an
explicit queue into a later authorized pass; no coverage is silently omitted.

Output must match a strict JSON schema and quote an exact retained source fragment.
Import independently checks document/store membership, unchanged record revision/name/
address, quotation, allowed field, normalization and value equivalence to the quotation.
Department phone ambiguity is held; weekly hours must describe all seven days. No model
coordinate, permanent closure, holiday invention, identity merge or new unfetched URL is
accepted. The retained underlying source remains the provenance family; the model is
recorded as extraction assistance, never another corroborating vote. Existing conflicts
remain conflicts. Unsupported, refused, partial, missing and stale outputs are retained
as holds. Publication uses the ordinary fenced replacement stores pack.

Use the explicit lifecycle:

```sh
PYTHONPATH=. python scripts/state-batch.py prepare --state IA --pass-id PASS \
  --data-dir /data --directory /data/operator-imports/IA-PASS-review \
  --completed-pass /data/crawl-campaigns/PASS/status.json
# submit/collect require an explicitly configured key and approved budget:
PYTHONPATH=. python scripts/state-batch.py submit --directory REVIEW_DIR --env-file KEY_ENV
PYTHONPATH=. python scripts/state-batch.py collect --directory REVIEW_DIR --env-file KEY_ENV
PYTHONPATH=. python scripts/state-batch.py import --directory REVIEW_DIR --data-dir /data
```

`prepare` requires a completed crawl or published quality-pass receipt. Optional
`post_pass_review.enabled=true` on the Iowa campaign prepares once after its terminal
pass, with `submitted=false`; it never starts a paid job by itself. The same helper can
be called by other state controllers when they are explicitly activated. The current
Iowa continuation has this preparation hook enabled; other state activation remains off.

The first Iowa pilot has a separate **$2 maximum**, using the existing key at the user's
viewer `.env.local` path on the workstation. It is not copied into browser variables,
logs, config, catalog responses or Unraid. Model: pinned `gpt-5.4-mini-2026-03-17`.
Each body is at most 50,000 UTF-8 bytes and output at most 6,000 tokens, without tools.
Durable reservations use conservative synchronous prices (rather than relying on the
Batch discount) and a byte-based input upper bound plus framing allowance. The ledger
reserves before submission; duplicate/unknown submission outcomes require reconciliation,
not automatic inference retry. Reservations are not measured billed spend. No additional
paid pass is activated by an offline post-pass plan.

Batch responses can arrive out of order, so results bind by custom_id. A bounded local
collector polls the single existing job, then transfers only plan/output/status files to
an isolated network-disabled Unraid importer. It never resubmits inference. Only unchanged,
validated results may publish; all other findings are retained for review. Until its
receipt says import_completed, do not claim the returned AI data has been imported.

Official references reviewed October 20, 2026:
[Batch API](https://developers.openai.com/api/docs/guides/batch),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
Batch supports Responses JSONL, unique custom_id and an asynchronous 24-hour window;
schema conformance does not establish factual accuracy.

## State-level source priorities

The research registry is
[here](investigations/iowa-quality-repair-20261020/state-sources.json). These are source
candidates, not automatically activated connectors or a fabricated nationwide census.

- **Iowa DIAL/SAFHER:** best next authority for licensed establishment IDs, premises and
  classification. The official portal is live; no reviewed complete bulk export was
  obtained. It mixes retail food, restaurants and other facilities. Licensing/inspection
  status and an absent license do not establish physical closure.
- **Iowa WIC:** useful for grocery-format corroboration and benefit-acceptance evidence.
  The public older roster found is dated July 2022 and cannot prove current membership.
  The official current vendor criteria help classify grocery format, not specific stock.
- **Iowa liquor licenses:** another identity/address/geospatial cross-check, with many
  out-of-scope businesses. An inactive liquor permit is not a closed supermarket.
- **New York Agriculture & Markets retail-food roster:** a useful state-specific license
  source when NY is activated. Review agency reuse limitations and establishment types;
  convenience/deli records are not automatically supermarkets.
- **Michigan MDARD:** retail-food licensing is potentially useful, but includes gas,
  warehouses and other formats. A reviewed export and taxonomy are required first.
- **State/county address points and Census batch geocoder:** useful next coordinate
  fallback. Census documents address-range interpolation and possible nonexistent
  structure numbers. Store its approximation separately from a provider branch point
  or reviewed entrance. No live geocoding request was made in this implementation.

[Execution results](investigations/iowa-quality-repair-20261020/RESULTS.md) distinguish live
publication, active crawls, AI processing and source work that remains unperformed.

## Phone and hours follow-up research

The [October 20 diagnostic](investigations/iowa-phone-hours-20261020/FINDINGS.md) separates missing-source, URL-discovery, schedule-representation and true conflict gaps. The subsequent [contact improvement workflow](STORE-CONTACT-IMPROVEMENTS.md) implements retained-source repair, exact-address website discovery and reviewed contact panels across states. Its [execution report](investigations/iowa-contact-improvements-20261020/RESULTS.md) distinguishes published Iowa improvements from held pilot pages and staged follow-up crawls.
