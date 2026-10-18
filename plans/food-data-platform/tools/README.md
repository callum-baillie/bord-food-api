# Offline package validation

Run `python tools/validate_package.py` from this plan directory. It reads local planning files and exercises the illustrative DDL in in-memory SQLite only. It never downloads, crawls, installs dependencies, changes application files or starts the API. Python and a locally installed `jsonschema` package are required.

Optional `--report PACKAGE-QA.json` writes an artifact check report. This is not proof of application implementation, TypeScript compilation, full OpenAPI semantics or live source/deployment health. Generate the SHA-256 manifest after the report, then rerun without `--report` for final read-only verification.
