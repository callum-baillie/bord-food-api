"""Explicit Iowa bulk discovery. Default is offline inspection, never acquisition.

--acquire fetches public SNAP + optional OSM directories into a versioned run.
--publish atomically adds reconciled rows, preserving existing catalog identities.
"""

import argparse
import fcntl
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import Lease, heavy_lock
from bord_food_api.store_discovery import (
    OSM_ENDPOINT,
    OSM_QUERY,
    SOURCE,
    PublicJSON,
    acquire_snap,
    apply_reviews,
    catalog_stores,
    osm_candidates,
    reclassify,
    reconcile,
    snap_candidates,
)


def acquire(directory, contact, *, include_osm=False, fetch=None):
    directory = Path(directory)
    if (directory / "bundle.json").exists():
        raise ValueError("discovery_run_already_acquired")
    directory.mkdir(parents=True, exist_ok=True)
    fetch = fetch or PublicJSON(directory / "artifacts", contact)
    status = {
        "state": "acquiring",
        "started_at": time.time(),
        "paid_calls": 0,
        "retailer_requests": 0,
    }
    atomic_json(directory / "status.json", status)
    try:
        rows, metadata = acquire_snap(fetch)
        candidates = snap_candidates(rows, metadata)
        blockers = []
        if include_osm:
            try:
                document = fetch(OSM_ENDPOINT + "?" + urlencode({"data": OSM_QUERY}))
                candidates.extend(osm_candidates(document))
            except Exception as error:  # noqa: BLE001 -- optional-source failure remains explicit.
                blockers.append(
                    {
                        "source": "openstreetmap",
                        "state": "failed",
                        "error_type": type(error).__name__,
                        "http_status": getattr(error, "status", None),
                    }
                )
        else:
            blockers.append({"source": "openstreetmap", "state": "not_requested"})
        artifact = directory / "candidates.jsonl"
        with artifact.open("w") as output:
            for row in candidates:
                output.write(json.dumps(row, allow_nan=False) + "\n")
        bundle = {
            "state": "IA",
            "profile": "all-grocery-stores-v1",
            "census_complete": False,
            "metadata": metadata,
            "source_blockers": blockers,
            "candidate_assertions": len(candidates),
            "candidate_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "source_types": dict(Counter(r["Store_Type"] for r in rows)),
            "snap_counties": sorted({r["County"] for r in rows if r.get("County")}),
            "acquired_at": time.time(),
        }
        atomic_json(directory / "bundle.json", bundle)
        atomic_json(
            directory / "status.json",
            {
                **status,
                "state": "acquired",
                "completed_at": time.time(),
                "summary": {"candidate_assertions": len(candidates), "source_blockers": blockers},
            },
        )
        return bundle
    except BaseException as error:
        atomic_json(
            directory / "status.json",
            {
                **status,
                "state": "failed",
                "error_type": type(error).__name__,
                "http_status": getattr(error, "status", None),
                "completed_at": time.time(),
            },
        )
        raise


def prepare(directory, root):
    directory, root = Path(directory), Path(root)
    bundle = json.loads((directory / "bundle.json").read_text())
    path = directory / "candidates.jsonl"
    if (
        bundle.get("state") != "IA"
        or bundle.get("profile") != "all-grocery-stores-v1"
        or hashlib.sha256(path.read_bytes()).hexdigest() != bundle["candidate_sha256"]
    ):
        raise ValueError("discovery_bundle_binding_invalid")
    candidates = [json.loads(line) for line in path.read_text().splitlines()]
    candidates = reclassify(candidates, bundle["metadata"])
    reviews_path = directory / "format-decisions.json"
    if reviews_path.exists():
        candidates = apply_reviews(
            candidates, json.loads(reviews_path.read_text()), bundle["candidate_sha256"]
        )
    existing = catalog_stores(root)
    result = reconcile(existing, candidates)
    manifest = json.loads((root / "current.json").read_text())
    for field in ("records", "crosswalk", "reviews", "excluded"):
        with (directory / (field + ".jsonl")).open("w") as output:
            for row in result[field]:
                output.write(json.dumps(row, allow_nan=False) + "\n")
    plan = {
        **result["summary"],
        "base_generation": manifest["generation"],
        "candidate_sha256": bundle["candidate_sha256"],
        "format_decisions_sha256": hashlib.sha256(reviews_path.read_bytes()).hexdigest()
        if reviews_path.exists()
        else None,
        "record_sha256": hashlib.sha256((directory / "records.jsonl").read_bytes()).hexdigest(),
        "scope": "All grocery stores, chains and independents; supermarkets, grocery supercenters and warehouse clubs; no convenience/pharmacy/dollar/specialist formats",
        "source_blockers": bundle["source_blockers"],
        "snap_reference_rows": bundle["metadata"]["reference_rows"],
        "snap_counties": len(bundle["snap_counties"]),
        "license_reference": "Iowa DIAL USFS/SAFHER transition; statewide licensing denominator not established",
        "prepared_at": time.time(),
    }
    atomic_json(directory / "plan.json", plan)
    return plan


def publish(directory, root):
    directory, root = Path(directory), Path(root)
    with (directory / "publication.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with heavy_lock(root):
            platform = Platform(root)
            platform.recover()
            # Reconcile again at the current generation, so concurrent core
            # imports cannot invalidate the operator's source-backed identities.
            plan = prepare(directory, root)
            path = directory / "records.jsonl"
            if hashlib.sha256(path.read_bytes()).hexdigest() != plan["record_sha256"]:
                raise ValueError("discovery_plan_changed")
            before = platform.current()
            old_stores = {r["id"]: r for r in platform.records("store") if r.get("id")}
            if not path.stat().st_size:
                result = {"no_change": True, "changed": 0}
            else:
                job_id = platform.control.enqueue(
                    SOURCE, "IA", operation="operator_discovery", version=plan["record_sha256"]
                )
                job = platform.control.claim("iowa-expansion", job_id=job_id, ttl=120)
                if not job:
                    raise ValueError("discovery_job_claim_failed")
                try:
                    with Lease(platform.control, job, 120, 20) as lease:
                        result = platform.sync(
                            SOURCE,
                            "IA",
                            plan["record_sha256"],
                            (json.loads(line) for line in path.read_text().splitlines()),
                            complete=False,
                            parser_version="iowa-discovery-v2",
                            cursor={
                                "state": "IA",
                                "candidate_sha256": plan["candidate_sha256"],
                                "complete": False,
                            },
                            fence=job,
                        )
                        lease.check()
                        platform.control.finish(job)
                except BaseException:
                    platform.control.finish(
                        job, state="failed", reason="discovery_publication_failed"
                    )
                    raise
            after = platform.current()
            current = {r["id"]: r for r in platform.records("store")}
            # Existing other-source facts are byte-for-byte retained. Our own
            # source can refresh corroborated fields under its stable identity.
            preserved = all(
                current.get(key) == value
                for key, value in old_stores.items()
                if not any(r.get("source_id") == SOURCE for r in value.get("source_refs", []))
            )
            if not preserved:
                raise ValueError("existing_store_preservation_failed")
            if before["packs"].get("usda") != after["packs"].get("usda") or before["packs"].get(
                "maps"
            ) != after["packs"].get("maps"):
                raise ValueError("unrelated_pack_preservation_failed")
            receipt = {
                "state": "published",
                "generation": after["generation"],
                "previous_generation": before["generation"],
                "plan": plan,
                "iowa_records_after": len(catalog_stores(root)),
                "existing_other_source_stores_preserved": preserved,
                "usda_unchanged": True,
                "maps_unchanged": True,
                "changed": result.get("changed", 0),
                "published_at": time.time(),
                "census_complete": False,
            }
            atomic_json(directory / "publication.json", receipt)
            return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--contact", default="hello@foldlab.app")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--include-osm", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.acquire:
        acquire(args.directory, args.contact, include_osm=args.include_osm)
    result = (
        publish(args.directory, args.data_dir)
        if args.publish
        else prepare(args.directory, args.data_dir)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
