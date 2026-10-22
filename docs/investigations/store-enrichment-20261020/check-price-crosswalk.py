"""Read-only exact native OSM-ID match against retained US Open Prices observations."""

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

root = Path("/data")
manifest = json.loads((root / "current.json").read_text())
directory = root / "discovery/iowa-20261020-r2"
with sqlite3.connect((root / manifest["packs"]["stores"]).as_uri() + "?mode=ro", uri=True) as db:
    stores = {
        identity: json.loads(raw)
        for identity, raw in db.execute("SELECT id,payload FROM entities WHERE kind='store'")
    }
links = defaultdict(set)
for identity, row in stores.items():
    for key in row.get("discovery_keys", []):
        if key.startswith("osm:"):
            links[key.removeprefix("osm:")].add(identity)
    if row.get("source_url", "").startswith("https://www.openstreetmap.org/"):
        links[row["source_url"].removeprefix("https://www.openstreetmap.org/")].add(identity)
for line in (directory / "crosswalk.jsonl").open():
    row = json.loads(line)
    if row.get("canonical_id") in stores and row["source_key"].startswith("osm:"):
        links[row["source_key"].removeprefix("osm:")].add(row["canonical_id"])
counts = Counter()
matched = Counter()
observed_locations = set()
matched_locations = set()
for line in (root / "validation/20261018-pilot/open-prices-us-raw.jsonl").open():
    row = json.loads(line)
    key = str(row.get("location_osm_type", "")).lower() + "/" + str(row.get("location_osm_id"))
    observed_locations.add(key)
    counts["retained_us_observations"] += 1
    ids = links.get(key, set())
    if len(ids) == 1:
        identity = next(iter(ids))
        matched[identity] += 1
        matched_locations.add(key)
        counts["exact_branch_observations"] += 1
    elif len(ids) > 1:
        counts["ambiguous_branch_observations"] += 1
print(
    json.dumps(
        {
            "generation": manifest["generation"],
            "counts": dict(counts),
            "retained_us_osm_locations": len(observed_locations),
            "reviewed_iowa_osm_crosswalk_keys": len(links),
            "exact_matching_osm_locations": len(matched_locations),
            "exact_matching_canonical_stores": len(matched),
            "match_semantics": "native OSM type/id only; no banner/proximity inference; historical observations do not establish current stock",
            "source_network_requests": 0,
            "paid_calls": 0,
        },
        indent=2,
    )
)
