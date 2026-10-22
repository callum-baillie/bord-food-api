"""Read-only Unraid snapshot. Run through an authorized SSH/container session."""

import hashlib
import json
import pathlib
import sqlite3
from datetime import UTC, datetime

root = pathlib.Path("/data")
manifest_bytes = (root / "current.json").read_bytes()
manifest = json.loads(manifest_bytes)
entities = {}
for pack in ("stores", "maps"):
    with sqlite3.connect((root / manifest["packs"][pack]).as_uri() + "?mode=ro", uri=True) as db:
        entities[pack] = [
            {"kind": kind, "source": source, "source_key": key, "payload": json.loads(raw)}
            for kind, source, key, raw in db.execute(
                "SELECT kind,source,source_key,payload FROM entities"
            )
        ]
ia_ids = {
    row["payload"]["id"]
    for row in entities["stores"]
    if row["kind"] == "store"
    and str((row["payload"].get("address") or {}).get("region", "")).upper() == "IA"
}
entities["stores"] = [
    r for r in entities["stores"] if r["kind"] == "chain" or r["payload"]["id"] in ia_ids
]
campaigns = []
for path in sorted((root / "crawl-campaigns").glob("*/status.json")):
    try:
        status = json.loads(path.read_text())
    except (ValueError, OSError):
        continue
    evidence = []
    for f in sorted((path.parent / "evidence").glob("*.json")):
        evidence.append({"file": f.name, "payload": json.loads(f.read_text())})
    campaigns.append({"directory": path.parent.name, "status": status, "evidence": evidence})
discovery = root / "discovery/iowa-20261020-r2"
files = {}
checksums = {}
for name in (
    "bundle.json",
    "publication.json",
    "candidates.jsonl",
    "crosswalk.jsonl",
    "reviews.jsonl",
    "excluded.jsonl",
):
    raw = (discovery / name).read_bytes()
    checksums[name] = hashlib.sha256(raw).hexdigest()
    files[name] = (
        [json.loads(x) for x in raw.splitlines()] if name.endswith(".jsonl") else json.loads(raw)
    )
assert (root / "current.json").read_bytes() == manifest_bytes, (
    "Serving generation changed; recapture"
)
print(
    json.dumps(
        {
            "captured_at": datetime.now(UTC).isoformat(),
            "manifest": manifest,
            "entities": entities,
            "campaigns": campaigns,
            "discovery": files,
            "sha256": checksums,
        }
    )
)
