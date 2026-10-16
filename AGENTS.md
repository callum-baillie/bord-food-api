# Project guidance

- Keep the service small: Python, FastAPI, SQLite FTS5, and streaming JSON imports.
- Preserve USDA FDC IDs, nutrient units/amounts, dataset attribution, and import provenance.
- Build a replacement database and atomically publish it; never mutate the serving catalog.
- Keep optional API keys out of logs and responses.
- Routine tests use synthetic fixtures and mocked downloads. Live dataset tests are explicit.
- Verify changes with `python -m pytest` and `ruff check .`.
- Do not claim Docker or Unraid deployment success without direct evidence.
