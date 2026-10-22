# Iowa coverage investigation — supporting analysis

The reader-facing findings are in `findings.md`; `artifact.json` preserves the complete canonical report input. The selected HTML report export was attempted but failed the packaged browser verifier with `horizontal_overflow` at 1440px, including after one targeted table-width correction. No HTML report was released and no custom reader was substituted. Supporting findings remain available as Markdown and JSON. No application, catalog, crawler or production configuration was changed.

`audit.py` replays all 14 Iowa-contributing scopes in the already downloaded ATP archive, verifies its SHA-256 and checks exact equality of eligible source IDs against the captured serving directory. It requires the existing ignored `data/nationwide-staging/` and `data/iowa-coverage-investigation-20261019/` evidence inputs. It writes only these investigation artifacts. `capture-live.py` was executed read-only inside the existing API container; it prints whitelisted aggregate results and store source IDs, never secrets, raw model prompts or household data.

`analysis.ipynb` preserves the Python checks and archive string-search code. Its cells are not marked executed in the notebook; the corresponding scripts were actually run and their results saved as `source-audit.json`, `live-summary.json` and `archive-name-search.json`.

Upstream Walmart statistics are pinned to ATP run `2026-10-10-13-32-41` in `walmart-upstream-stats.json`. `references.json` records bounded official-directory checks. The source-export archive SHA-256 is `174b0a4836f88185d5c7fbe96228814da61141e65c2330b522644dc56d8665d7`.

The archive name probe scanned all 5,641 members / 27,992,816,145 expanded bytes in 160.1 seconds. New Pioneer and Bender’s tested name/domain spellings had no matches. The Hometown Foods domain match belongs to a Georgia IGA store, not the western Iowa group. Untested aliases and Unicode spellings remain a limitation. No statewide missing-location total is established by these checks.


Report QA: source/artifact validation and packaging completed, but enhanced HTML browser QA failed. The failure receipts and screenshots are retained in the ignored investigation data directory. The canonical report uses an exact outcomes bar chart and scope comparison table; no timeframe trend or statewide completeness percentage is asserted.

Validation: `.venv/bin/python -m pytest -q` passed 289 tests (one upstream Starlette warning) in 9.54s. `ruff check .`, the 122-file format check and `git diff --check` passed. The live read-only capture initially assumed source_key was in payload; corrected to select it from entities, then recaptured successfully. Source audit and archive search completed; report export blockers are recorded above.
