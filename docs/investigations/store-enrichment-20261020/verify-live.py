"""Explicit read-only live verification; no source downloads, crawls or paid calls."""

import hashlib
import json
import os
import shutil
import sqlite3
import time
import urllib.request
from collections import Counter
from pathlib import Path

root = Path("/data")
before = json.loads((root / "backups/20261020-before-products-enrichment/current.json").read_text())
after = json.loads((root / "current.json").read_text())


def entities(manifest):
    with sqlite3.connect(
        (root / manifest["packs"]["stores"]).resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        return {
            (kind, identity): (raw, json.loads(raw))
            for kind, identity, raw in db.execute("SELECT kind,id,payload FROM entities")
        }


a, b = entities(before), entities(after)
assert a.keys() == b.keys()
assert all(raw == b[key][0] for key, (raw, row) in a.items() if key[0] == "chain")
for key, (raw, row) in a.items():
    if key[0] == "store":
        assert row.get("source_record") == b[key][1].get("source_record")
        assert row.get("source_refs") == b[key][1].get("source_refs")
for pack in ("usda", "maps"):
    assert before["packs"][pack] == after["packs"][pack]
fields = [
    "phone",
    "email",
    "website",
    "opening_hours",
    "hours",
    "timezone",
    "hours_exceptions",
    "pickup_links",
    "delivery_links",
    "departments",
    "accessibility",
    "entrances",
    "aisle_category_mappings",
]
counts = {}
for scope in ("all", "IA"):

    def included(row, selected_scope=scope):
        return selected_scope == "all" or (row.get("address") or {}).get("region") == "IA"

    aa = [row for (kind, _), (raw, row) in a.items() if kind == "store" and included(row)]
    bb = [row for (kind, _), (raw, row) in b.items() if kind == "store" and included(row)]
    counts[scope] = {
        "stores": len(bb),
        "fields": {
            field: {
                "before_present": sum(bool(row.get(field)) for row in aa),
                "after_present": sum(bool(row.get(field)) for row in bb),
                "currently_verified": sum(
                    row.get("field_provenance", {}).get(field, {}).get("status")
                    in {"corroborated", "reviewed"}
                    and (row.get("field_provenance", {}).get(field, {}).get("verified_until") or 0)
                    >= time.time()
                    for row in bb
                ),
            }
            for field in fields
        },
        "field_statuses": dict(
            Counter(
                meta["status"] for row in bb for meta in row.get("field_provenance", {}).values()
            )
        ),
        "stores_with_conflicts": sum(bool(row.get("field_conflicts")) for row in bb),
        "dataset_link_sources": dict(
            Counter(link["source_id"] for row in bb for link in row.get("dataset_links", []))
        ),
        "permanently_closed": sum(row.get("permanently_closed") is True for row in bb),
    }
packs = {}
for name, relative in after["packs"].items():
    with sqlite3.connect((root / relative).resolve().as_uri() + "?mode=ro", uri=True) as db:
        packs[name] = {
            "bytes": (root / relative).stat().st_size,
            "counts": dict(db.execute("SELECT kind,count(*) FROM entities GROUP BY kind"))
            if name != "usda"
            else {
                "food": int(
                    db.execute("SELECT value FROM metadata WHERE key='totalFoods'").fetchone()[0]
                )
            },
        }
http = {}
for path in (
    "/health",
    "/ready",
    "/fdc/v1/foods/search?query=apple&pageSize=1",
    "/v1/stores?state=IA&limit=1",
    "/v1/products?query=apple&limit=1",
    "/v1/guidance/storage?limit=100",
):
    request = urllib.request.Request(
        "http://127.0.0.1:8080" + path, headers={"X-Api-Key": os.environ["API_KEY"]}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
        body = json.loads(raw)
        http[path] = {
            "http": response.status,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "returned_records": len(body["data"]) if isinstance(body.get("data"), list) else None,
        }
print(
    json.dumps(
        {
            "checked_at": time.time(),
            "generation": after["generation"],
            "packs": packs,
            "fields": counts,
            "http": http,
            "preservation": {
                "store_chain_ids": True,
                "chain_payloads": True,
                "store_source_records_and_refs": True,
                "usda_object": True,
                "maps_object": True,
            },
            "cache_free_bytes": shutil.disk_usage(root).free,
            "source_network_requests": 0,
            "paid_calls": 0,
        },
        indent=2,
    )
)
