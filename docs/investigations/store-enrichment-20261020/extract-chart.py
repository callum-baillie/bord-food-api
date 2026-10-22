"""Reproduce a conservative reviewed extract from the retained official page text.

Only complete visible rows are selected. Rowspan-ambiguous fish and multiline egg
rows remain explicitly excluded; no time, temperature or condition is invented.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).parent
path = root / "cold-storage-source.txt"
raw = path.read_text()
rows = []
excluded = []
category = None
for match in re.finditer(r"^L(\d+): (.*)$", raw, re.MULTILINE):
    line = int(match[1])
    text = match[2].strip()
    if not 19 <= line <= 74:
        continue
    if line in {45, 46, 55, 56, 57, 58, 59}:
        excluded.append(
            {
                "line": line,
                "text": text,
                "reason": "rowspan_or_multiline_cells_require_full_html_review",
            }
        )
        continue
    cells = [v.strip() for v in text.split("|")]
    if len(cells) == 4:
        category, kind, fridge, freezer = cells
        if line == 32:
            category = "Ham"
    elif len(cells) == 3 and category:
        kind, fridge, freezer = cells
    else:
        excluded.append({"line": line, "text": text, "reason": "incomplete_explicit_cells"})
        continue
    rows.append(
        {
            "food": category,
            "type": kind,
            "refrigerator": fridge,
            "freezer": freezer,
            "source_line": line,
        }
    )
document = {
    "source_url": "https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts",
    "source_title": "Cold Food Storage Chart",
    "source_last_reviewed": "2023-09-19",
    "retrieved_at": datetime.now(UTC).isoformat(),
    "source_snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "extraction_method": "reviewed_complete_visible_table_rows_v1",
    "source_conditions": "Refrigerator 40°F (4°C) or below; freezer 0°F (-18°C) or below. Freezer durations are quality only; continuously frozen food can be kept indefinitely.",
    "rows": rows,
    "excluded_rows": excluded,
    "complete_foodkeeper_dataset": False,
}
(root / "official-cold-storage-chart.json").write_text(
    json.dumps(document, indent=2, ensure_ascii=False) + "\n"
)
print({"selected_rows": len(rows), "excluded_lines": len(excluded)})
