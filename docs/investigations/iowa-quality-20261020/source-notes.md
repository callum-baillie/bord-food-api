# Source and report notes

Audience: product stakeholders. Surface: portable HTML; this runtime has no callable Sites lifecycle or report MCP reader. Executive specification mapped to title, Executive Summary, coverage/segments/identity/freshness/advanced evidence, recommendations, questions and caveats. No parallel rendered surface.

Snapshot acquired with read-only SQLite connections and no application Platform initialization. Manifest unchanged during read. Exact generation and profile captured_at are in profile.json. Raw source selection is SELECT payload FROM entities WHERE kind='store'; Python predicates/filter/aggregations in profile.py materially produced every report metric. The raw snapshot is kept at /tmp/iowa-quality-review/snapshot.json and is not copied into the report. Serving objects remain immutable on Unraid.

Reproduce locally with the project virtualenv and profile.py SNAPSHOT OUTPUT. capture.py SSH_IDENTITY OUTPUT_JSON can explicitly capture a later read-only snapshot; it does not promise the same generation. review.ipynb shows the checks and conclusions. Numeric assertions and profile equality were executed successfully; notebook cells themselves were not executed by a notebook runner.

Chart contract: one native bar chart comparing six field/bundle population fractions across the same 741-record denominator. One observation per field. Single neutral series, no decorative category-color encoding. No trend line: only one snapshot and the previous pilot baseline are available, and the running crawl makes a time trend premature. Exact field counts/verification and seven chain groups use lookup tables with descending sorts. Chart caveats and interpretation adjacent to visual; generation/population/source definitions before use.

Official indexed spot checks, reviewed October 20, 2026:
- https://www.fareway.com/stores/237 : one LeClaire branch, street and phone agree with both candidate records.
- https://www.hy-vee.com/stores/detail.aspx?sc=1262 : Independence Dollar Fresh, address supports candidate alias.
- https://www.hy-vee.com/stores/detail.aspx?sc=7525 : Cumming Fast & Fresh label/address supports scope review.
- https://www.hy-vee.com/stores/store-finder-results.aspx?city=Ankeny&state=IA&zip=50021 : Des Moines Fast & Fresh at5801 Hickman.
- https://www.target.com/sl/dubuque/86 and https://www.hy-vee.com/stores/detail.aspx?sc=1159 : both official pages list3500 Dodge, so same-address match is not a merge decision.

No statistical accuracy rate is claimed from these targeted checks. Duplicate pairs are candidates, not completed identity resolutions. Chain-unmapped is not a proven independent-store category. Public shared contact values are not evidence of distinct or duplicate physical branches by themselves. Rows with all core fields may contain provisional/conflicted data. All-zero closure means unknown everywhere, not all-open.

Broader catalog counts were read separately: USDA455458Branded/363Foundation/7793SRLegacy/5432FNDDS,455332nonemptyGTINs;455458nativeproducts/49guidance/108maps. Nonempty GTIN is not checksum validation or product availability. Nutrients/barcode matches and storage guidance were not deeply audited this turn; acceptability verdict is focused on Iowa stores.
