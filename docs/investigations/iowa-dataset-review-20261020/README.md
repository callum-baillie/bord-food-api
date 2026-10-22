# Iowa dataset review

Read [findings.md](findings.md). [profile.json](profile.json) contains the computed counts; [analysis.ipynb](analysis.ipynb) is an inspectable replay and [analyze.py](analyze.py) is the executed analysis.

The read-only Unraid capture is retained locally at data/iowa-review-20261020/input.json.gz (ignored source data); source-native ledgers and original page evidence remain on Unraid. No crawler/source acquisition, paid call, deployment or serving-data mutation was performed.

The canonical [artifact.json](artifact.json) passed source/schema packaging after its queries were bound to executable SQLite JSON transformations. HTML delivery remains blocked: the packaged report renderer failed horizontal-overflow verification at 1440px, including after one targeted table-sizing correction. No unverified report.html is released. Failure screenshots are retained in the ignored data/qa directory. The complete Markdown findings and all canonical report sections/datasets are preserved.

Validation:317 tests passed (one upstream warning,13.13s); Ruff,134-file format and diff checks passed. Offline reconciliation and notebook cell replay assertions passed. This is dataset analysis, not new live source or companion integration validation.
