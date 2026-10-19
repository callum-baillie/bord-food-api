"""Explicit Iowa discovery from a pinned, already acquired ATP archive.

No built-in retailer URLs or networking. Unknown banners remain source candidates;
Iowa-only imports are partial and cannot establish absence outside this scope.
"""

import argparse
import json
import re
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile

import ijson

from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import Lease, heavy_lock
from bord_food_api.sources import ATP_DESCRIPTORS, GROCERY_SHOPS, _atp_feature
from bord_food_api.transport import file_hash, validate_zip


def iowa_region(properties):
    explicit = str(properties.get("addr:state") or properties.get("state") or "").strip().upper()
    if explicit:
        return explicit in {"IA", "IOWA"}, False
    # Some published sources supply only a full postal address. Accept its
    # explicit Iowa postal suffix; no geographic/name inference or geocoding.
    full = properties.get("addr:full") or ""
    return bool(re.search(r",\s*(?:IA|Iowa)\s+\d{5}(?:-\d{4})?\s*$", full, re.IGNORECASE)), True


def scan(
    archive, *, progress=lambda _value: None, check=lambda: None, max_member_bytes=2 * 1024**3
):
    members = validate_zip(archive, max_members=10000, max_expanded_bytes=200 * 1024**3)
    seen, scanned, iowa = set(), 0, 0
    with ZipFile(archive) as package:
        for member in members:
            check()
            if member.is_dir() or PurePosixPath(member.filename).suffix != ".geojson":
                continue
            spider = PurePosixPath(member.filename).stem
            if spider in seen:
                raise ValueError("duplicate_scope")
            seen.add(spider)
            if member.file_size > max_member_bytes:
                yield {
                    "spider": spider,
                    "records": [],
                    "unresolved": [],
                    "error": "scope_member_byte_limit",
                }
                continue
            rows, unresolved = [], []
            try:
                with package.open(member) as stream:
                    if next(ijson.items(stream, "type"), None) != "FeatureCollection":
                        raise ValueError("invalid_feature_collection")
                    stream.seek(0)
                    for feature in ijson.items(stream, "features.item", use_float=True):
                        scanned += 1
                        if scanned % 10000 == 0:
                            check()
                        props = feature.get("properties") or {}
                        selected, from_full = iowa_region(props)
                        if not selected:
                            continue
                        country = str(
                            props.get("addr:country") or props.get("country") or ""
                        ).upper()
                        if country not in {
                            "US",
                            "USA",
                            "UNITED STATES",
                            "UNITED STATES OF AMERICA",
                        }:
                            continue
                        iowa += 1
                        if iowa > 50000:
                            raise OverflowError("iowa_candidate_limit")
                        item = _atp_feature(feature, spider, ATP_DESCRIPTORS.get(spider))
                        if item:
                            if from_full:
                                item["payload"]["address"]["region"] = "IA"
                                item["payload"]["address_region_evidence"] = {
                                    "field": "addr:full",
                                    "value": props["addr:full"],
                                }
                            rows.append(item)
                        elif str(props.get("shop", "")).casefold() in GROCERY_SHOPS:
                            unresolved.append(
                                {
                                    "name": props.get("name"),
                                    "ref": props.get("ref"),
                                    "reason": "grocery_source_identity_or_banner_unresolved",
                                }
                            )
                # Reading to EOF verifies each parsed ZIP member's CRC too.
                error = None
            except (ValueError, TypeError, ijson.JSONError) as failure:
                rows = []  # A malformed scope supplies no publication/absence evidence.
                error = type(failure).__name__
            progress(
                {
                    "spider": spider,
                    "features_scanned": scanned,
                    "iowa_features": iowa,
                    "scopes_scanned": len(seen),
                }
            )
            yield {"spider": spider, "records": rows, "unresolved": unresolved, "error": error}


def discover(archive, directory, *, check=lambda: None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    status = {"state": "scanning", "started_at": time.time()}
    path = directory / "discovery-status.json"
    atomic_json(path, status)
    scopes, banners, errors, unresolved = [], {}, [], []
    temporary = directory / "roster.jsonl.part"
    with temporary.open("w") as output:
        for scope in scan(
            archive, progress=lambda value: atomic_json(path, {**status, **value}), check=check
        ):
            spider = scope["spider"]
            if scope["error"]:
                errors.append({"spider": spider, "error": scope["error"]})
            unresolved.extend({"spider": spider, **item} for item in scope["unresolved"])
            if scope["records"]:
                scopes.append({"spider": spider, "stores": len(scope["records"])})
            for row in scope["records"]:
                payload = row["payload"]
                key = payload["chain_key"]
                banner = banners.setdefault(
                    key,
                    {
                        "source_chain_key": key,
                        "name": payload["chain_name"],
                        "spiders": [],
                        "stores": 0,
                        "official_hosts": [],
                        "map_crawl_state": "access_review_required",
                    },
                )
                if spider not in banner["spiders"]:
                    banner["spiders"].append(spider)
                host = urlsplit(payload.get("website") or "").hostname
                if host and host not in banner["official_hosts"]:
                    banner["official_hosts"].append(host)
                banner["stores"] += 1
                output.write(json.dumps({"partition": spider, **row}, allow_nan=False) + "\n")
    temporary.replace(directory / "roster.jsonl")
    report = {
        "state": "discovered",
        "scopes": scopes,
        "banners": list(banners.values()),
        "stores": sum(x["stores"] for x in scopes),
        "errors": errors,
        "unresolved": unresolved,
        "census_complete": False,
        "scope": "Iowa US grocery/superstore/warehouse source assertions",
        "limitations": [
            "ATP coverage may omit independent/affiliated grocers and failed spiders",
            "Source banners remain separate; no name-only merges",
            "Discovery does not authorize retailer access or media acquisition",
        ],
        "roster_sha256": file_hash(directory / "roster.jsonl"),
        "completed_at": time.time(),
    }
    atomic_json(directory / "coverage.json", report)
    atomic_json(
        path,
        {
            **status,
            "state": "finished",
            "completed_at": time.time(),
            "stores": report["stores"],
            "banners": len(banners),
            "errors": len(errors),
        },
    )
    return report


def publish(directory, platform, *, fence=None):
    directory = Path(directory)
    report = json.loads((directory / "coverage.json").read_text())
    if file_hash(directory / "roster.jsonl") != report["roster_sha256"]:
        raise ValueError("roster_hash_mismatch")
    manifest = json.loads((directory / "atp-manifest.json").read_text())
    # Scope-level partial imports preserve existing source IDs and all other states.
    groups = {}
    for line in (directory / "roster.jsonl").read_text().splitlines():
        row = json.loads(line)
        payload = row["payload"]
        if str(payload["address"]["region"]).upper() not in {"IA", "IOWA"}:
            raise ValueError("non_iowa_record")
        payload.update(source_run=manifest["run_id"], source_observed_at=manifest["start_time"])
        groups.setdefault(row.pop("partition"), []).append(row)
    result = []
    for spider, rows in groups.items():
        if fence:
            platform.control.check_fence(fence)
        prior = (platform.current() or {}).get("sources", {}).get(f"all_the_places:{spider}", {})
        prior_run = (prior.get("cursor") or {}).get("source_run")
        if prior_run and str(prior_run) > manifest["run_id"]:
            result.append(
                {"spider": spider, "records": 0, "reason": "newer_scope_already_published"}
            )
            continue
        r = platform.sync(
            "all_the_places",
            spider,
            manifest["run_id"] + ":iowa:" + report["roster_sha256"],
            rows,
            complete=False,
            parser_version="iowa-archive-v1",
            cursor={"source_run": manifest["run_id"], "region": "IA", "complete": False},
            fence=fence,
        )
        result.append({"spider": spider, "records": len(rows), "changed": r["changed"]})
    atomic_json(
        directory / "publication.json",
        {
            "state": "published",
            "scopes": result,
            "generation": platform.current()["generation"],
            "completed_at": time.time(),
        },
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument("--publish", action="store_true")
    publication.add_argument("--publish-only", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    args = parser.parse_args()
    root, directory = args.data_dir, args.directory
    receipt = json.loads((directory / "atp-output.metadata.json").read_text())
    archive = directory / "atp-output.zip"
    if file_hash(archive) != receipt["sha256"]:
        raise ValueError("archive_hash_mismatch")
    platform = Platform(root)
    with heavy_lock(root):
        job_id = platform.control.enqueue(
            "all_the_places",
            "iowa_discovery",
            operation="operator_discovery",
            version=receipt["sha256"],
        )
        job = platform.control.claim("iowa-discovery", ttl=120, job_id=job_id)
        if not job:
            raise ValueError("job_claim_failed")
        with Lease(platform.control, job, 120, 20) as lease:
            try:
                if not args.publish_only:
                    discover(archive, directory, check=lease.check)
                if args.publish or args.publish_only:
                    platform.backup(root / "backups/20261019-pre-iowa")
                    publish(directory, platform, fence=job)
                platform.control.finish(job)
            except BaseException:
                atomic_json(
                    directory / "discovery-status.json",
                    {
                        "state": "failed",
                        "stopped_at": time.time(),
                        "reason": "discovery_or_publication_failed",
                    },
                )
                platform.control.finish(job, state="failed", reason="iowa_discovery_failed")
                raise


if __name__ == "__main__":
    main()
