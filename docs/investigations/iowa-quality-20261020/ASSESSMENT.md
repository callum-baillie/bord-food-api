# Iowa dataset assessment — October 20, 2026

**Acceptable for a clearly labelled directory beta. It needs improvement before dependable
shopping assistance, open-now claims or aisle navigation.** This is a review of the serving
Iowa store dataset, not a statistical accuracy audit of every source or the nutrition packs.

Snapshot: 2:38 p.m. CDT, immutable generation `g_764fdcbc95194f3999643aa4b203f6d4`.
All 741 Iowa records were profiled read-only; the manifest stayed unchanged during capture.
The authorized statewide crawler was running, so these figures describe that snapshot.

| Information | Records | Share of 741 |
| --- | ---: | ---: |
| Coordinates | 616 | 83.1% |
| Phone | 503 | 67.9% |
| Website | 480 | 64.8% |
| Normalized weekly hours plus timezone | 314 | 42.4% |
| Phone, website, hours, timezone and coordinates together | 164 | 22.1% |
| Email | 84 | 11.3% |
| Known operating status | 0 | 0% |

These are field-presence figures, not measured accuracy. Only 252 phones, 116 websites and
10 weekly schedules are currently corroborated or reviewed. Timezones are derived. Only 63
records have the full core bundle and no field conflict anywhere on the record; even those
records are not necessarily independently verified in every field.

## What is already good

No missing/duplicate canonical IDs, missing names, missing attribution/licenses/source references,
invalid Iowa coordinate bounds or orphan chain references were found. All addresses can be
normalized to an address key, including full-text addresses. No provisional fields falsely
carry nonnull verification dates. No repeated emails remain in canonical branch email fields.
Conflicts, source lineage, unknown values and failure history are retained, making correction
possible without hiding evidence. These structural checks do not prove factual accuracy.

## Findings that matter for the app

1. **High — identity and scope need review; high confidence in the observed anomalies.**
   Four likely duplicate pairs: Fareway Le Claire/LeClaire, Fareway North Liberty with a PO-box
   suffix, Fareway Winterset with a multi-valued street, and Dollar Fresh Independence with
   Three Elms/Three Elms Park address variants. The last pair shares a branch URL. Official
   Fareway #237 and Independence Dollar Fresh pages strengthen these suspicions. Two Fast & Fresh
   records also carry supermarket format despite the agreed convenience-store exclusion.
   These are review candidates, not completed merges or a corrected physical-store count.
   Do not publish 741 as an audited count of distinct active stores.

2. **High — independent/unmapped coverage is much weaker; high confidence.**
   Of 337 records without a chain mapping, 140 have phones, 108 websites and just 15 normalized
   hours (4.5%). This category can include unmapped chains, not only independents. Hy-Vee hours
   are present for 115/126 and Fareway for 107/124. Statewide averages conceal this gap.
   Prioritize these sparse stores over repeatedly enriching already-complete chains.

3. **High — operational accuracy is unproven; high confidence in missingness.**
   Every operating status is unknown, 125 stores lack coordinates and 427 lack normalized hours.
   Zero dated holiday exceptions exist. This cannot support guaranteed open-now or active-only
   results. Unknown must remain visible; do not treat absent closure evidence as proof of open.

4. **Medium to high — conflicts affect one-quarter of records; high confidence.**
   There are 217 conflicts across 182 stores (24.6%): 154 website, 34 hours, 29 phone. Some URL
   conflicts may be harmless aliases; phone/hours conflicts can directly mislead a shopper.
   Retain both sides but prioritize resolution by impact. A conflicted value must not acquire
   a verified label just because a canonical field remains populated.

5. **Medium — contact and address normalization need another pass; high confidence.**
   One Hy-Vee phone field combines main and pharmacy numbers and fails single-phone normalization.
   Fifteen ALDI records share a toll-free number: label this as a chain contact until branch
   scope is established. Another 125 records contain full postal text but no structured street
   or city, and also lack coordinates. Preserve source text while adding structured fields.

6. **High for advanced features — insufficient evidence; high confidence.**
   Departments appear on 11 records, accessibility on 10, and pickup/delivery links on one each,
   still unverified. Dated holidays, reviewed entrances and aisle/category mappings are zero.
   The current data cannot support dependable aisle guidance or accessibility-route promises.
   These fields should remain optional and visibly unknown until supported.

7. **Medium — source freshness needs clearer separation; high confidence in dates, accuracy unknown.**
   Of 2,187 eligible core-field assertions, 904 have observation dates 30–180 days old and 584 have
   no observation date. Counts are assertions, not stores or known errors. A recent acquisition
   date is not proof the source fact was recently checked. Refresh the high-impact facts first.

## Recommended order

Resolve identity/scope candidates, normalize full-text addresses and label chain contacts first.
Then prioritize coordinates, phones, official branch URLs and hours for sparse independent/unmapped
records. Resolve phone/hours conflicts before cosmetic URL aliases. Keep reported, corroborated,
conflicted, stale and unknown values visibly distinct. Validate a stratified sample across chains,
independents/unmapped stores and urban/rural areas before claiming measured accuracy. Reconcile an
authoritative active grocery/license roster before claiming complete Iowa coverage. More AI
extraction alone will not resolve the denominator, identity precision or stale business facts.

For a beta, basic name/address search with source links and correction feedback is reasonable.
For dependable trip planning, I would first aim for roughly 95% coordinate coverage and 90% useful
contact/website coverage, with much broader checked weekly hours. Those are proposed product
quality goals, not guarantees or an external standard. Holiday and closure correctness need
separate checks. Do not hold a beta solely for low email or aisle coverage when those features
can be omitted safely.

## Broader catalog limits

The nutrition/reference catalog is separate: USDA has 455,458 Branded, 363 Foundation, 7,793
SR Legacy and 5,432 FNDDS rows; 455,332 have nonempty GTIN fields. Native products contain
455,458 rows and guidance contains 49 official chart rows. Nonempty GTIN is not checksum validation
or evidence of store stock. Nutrient/barcode accuracy was not exhaustively re-audited this turn.
OFF import remains failed after duplicate source keys; full FoodKeeper is not published. Pricing
was deliberately deferred. These limitations should be separate from the Iowa store assessment.

## Evidence and limitations

[Profile](profile.json), [reproducible checks](profile.py), [notebook](review.ipynb) and
[source notes](source-notes.md) retain definitions, candidate records, segments and clocks.
The raw snapshot remains at `/tmp/iowa-quality-review/snapshot.json`. No corrections, policy
changes, new crawls, source imports or paid calls were performed by this assessment.

Targeted official spot checks: [Fareway LeClaire](https://www.fareway.com/stores/237),
[Independence Dollar Fresh](https://www.hy-vee.com/stores/detail.aspx?sc=1262),
[Cumming Fast & Fresh](https://www.hy-vee.com/stores/detail.aspx?sc=7525).
Same address alone is insufficient for merging: both official
[Target Dubuque](https://www.target.com/sl/dubuque/86) and
[Hy-Vee Dubuque](https://www.hy-vee.com/stores/detail.aspx?sc=1159) list 3500 Dodge Street.

The canonical HTML report payload is retained in artifact.json. The packaged report renderer
failed its desktop horizontal-overflow check, including after one targeted table-width correction.
No HTML report was published or claimed verified. The analytical profile and invariant checks
passed; rendering failure does not change the underlying findings. The notebook code was executed
directly through profile.py/invariant checks, not through a notebook runner. No application code
changed, so routine application tests were not rerun for this read-only assessment.
