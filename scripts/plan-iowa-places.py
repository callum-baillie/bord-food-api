"""Corroborate retained Iowa SNAP grocery candidates with an attributed place extract.

Offline by default. --publish appends only new, exact-address/name matched SNAP +
Overture groceries after existing nearby/identity holds. No lone place/AI additions.
"""

import argparse
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from bord_food_api.domain import content_hash
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.store_discovery import (
    EXCLUDED_NAMES,
    SOURCE,
    address_key,
    catalog_stores,
    entity_names_compatible,
    reconcile,
    specialist_name,
)
from bord_food_api.store_sources import place_candidate


def prepare(existing, retained, places):
    snap = defaultdict(list)
    for candidate in retained:
        if (
            candidate["source"] == "usda_snap_arcgis"
            and candidate["category"] != "exclude"
            and (key := address_key(candidate["payload"]))
        ):
            snap[key].append(candidate)
    additions = []
    for row in places:
        candidate = place_candidate("overture_places", row)
        payload = candidate["payload"]
        name = payload.get("name") or ""
        if (
            candidate["category"] == "exclude"
            or EXCLUDED_NAMES.search(name)
            or specialist_name(name)
            or row.get("operating_status") == "permanently_closed"
        ):
            continue
        if str(payload.get("country")).upper() != "US" or str(
            payload["address"].get("region")
        ).lower() not in {"ia", "iowa"}:
            continue
        if re.search(
            r"\b(?:pharmacy|fuel|gas|optical|hearing|photo|garden center|money center|auto care|distribution)\b",
            name,
            re.IGNORECASE,
        ):
            continue
        if re.search(r"\b(?:bakery|deli|floral)\b", name, re.IGNORECASE) and not re.search(
            r"grocer", name, re.IGNORECASE
        ):
            continue
        matches = [
            s
            for s in snap.get(address_key(payload), [])
            if entity_names_compatible(payload, s["payload"])
        ]
        if len(matches) != 1 or not row.get("_retrieved_at") or not row.get("_source_url"):
            continue
        payload.update(
            source_url=row["_source_url"],
            license="CC0-1.0 / CDLA-Permissive-2.0 / Apache-2.0 per provider",
            source_observed_at=row["_retrieved_at"],
            attribution="Overture Maps Foundation and record providers",
            open_status="unknown",
        )
        additions.append(
            {
                **candidate,
                "source_key": "overture:" + candidate["source_key"],
                "category": "include",
                "reason": "snap_corroborated_grocery_place",
            }
        )
    plan = reconcile(existing, retained + additions)
    new_keys = {r["proposed_key"] for r in plan["crosswalk"] if r["state"] == "new"}
    records = [
        r
        for r in plan["records"]
        if r["source_key"] in new_keys
        and {"overture_places", "usda_snap_arcgis"}
        <= {s["source_id"] for s in r["payload"].get("discovery_sources", [])}
    ]
    return {
        **plan,
        "records": records,
        "corroborated_new_records": len(records),
        "qualified_place_assertions": len(additions),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--snap-candidates", type=Path, required=True)
    parser.add_argument("--places", type=Path, required=True)
    parser.add_argument("--places-sha256", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    with args.places.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != args.places_sha256:
            raise ValueError("retained_place_extract_changed")
    with heavy_lock(args.data_dir):
        platform = Platform(args.data_dir)
        current = platform.current()
        existing = catalog_stores(args.data_dir, state="IA")
        retained = [
            json.loads(l) for l in args.snap_candidates.read_text().splitlines() if l.strip()
        ]
        places = (json.loads(l) for l in args.places.read_text().splitlines() if l.strip())
        plan = prepare(existing, retained, places)
        records = plan.pop("records")
        args.run_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(
            args.run_dir / "plan.json",
            {
                **plan,
                "base_generation": current["generation"],
                "prepared_at": time.time(),
                "source_requests": 0,
                "paid_calls": 0,
            },
        )
        atomic_json(args.run_dir / "records.json", records)
        if args.publish and records:
            if platform.current()["generation"] != current["generation"]:
                raise ValueError("coverage_base_generation_changed")
            if any(platform.get_by_source("store", SOURCE, r["source_key"]) for r in records):
                raise ValueError("new_source_identity_already_published")
            result = platform.sync(
                SOURCE,
                "iowa-places-corroboration",
                content_hash(records),
                records,
                complete=False,
                parser_version="snap-overture-iowa-v1",
                cursor={"place_extract_sha256": args.places_sha256, "census_complete": False},
            )
            after = platform.current()
            assert all(after["packs"][k] == v for k, v in current["packs"].items() if k != "stores")
            assert {s["id"] for s in existing} <= {
                s["id"] for s in catalog_stores(args.data_dir, state="IA")
            }
            atomic_json(
                args.run_dir / "publication.json",
                {
                    "state": "published",
                    "changed": result["changed"],
                    "generation": after["generation"],
                    "census_complete": False,
                },
            )
        print(
            json.dumps(
                {
                    "new_records": len(records),
                    "qualified_place_assertions": plan["qualified_place_assertions"],
                    "published": args.publish,
                    "network": False,
                }
            )
        )


if __name__ == "__main__":
    main()
