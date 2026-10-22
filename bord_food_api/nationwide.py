"""Offline, source-backed state crawl staging. No catalog or network side effects."""

import ipaddress
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile

import ijson

from .crawlers import CrawlBlocked, safe_link
from .platform import atomic_json
from .sources import ATP_DESCRIPTORS, GROCERY_SHOPS, _atp_feature
from .transport import PolicyError, approved_url, file_hash, validate_zip

STATES = dict(
    line.split(":", 1)
    for line in """AL:Alabama
AK:Alaska
AZ:Arizona
AR:Arkansas
CA:California
CO:Colorado
CT:Connecticut
DE:Delaware
FL:Florida
GA:Georgia
HI:Hawaii
ID:Idaho
IL:Illinois
IN:Indiana
IA:Iowa
KS:Kansas
KY:Kentucky
LA:Louisiana
ME:Maine
MD:Maryland
MA:Massachusetts
MI:Michigan
MN:Minnesota
MS:Mississippi
MO:Missouri
MT:Montana
NE:Nebraska
NV:Nevada
NH:New Hampshire
NJ:New Jersey
NM:New Mexico
NY:New York
NC:North Carolina
ND:North Dakota
OH:Ohio
OK:Oklahoma
OR:Oregon
PA:Pennsylvania
RI:Rhode Island
SC:South Carolina
SD:South Dakota
TN:Tennessee
TX:Texas
UT:Utah
VT:Vermont
VA:Virginia
WA:Washington
WV:West Virginia
WI:Wisconsin
WY:Wyoming""".splitlines()
)
JURISDICTIONS = {**STATES, "DC": "District of Columbia"}
REGIONS = {key.casefold(): code for code, name in JURISDICTIONS.items() for key in (code, name)}
PROFILE = "public-store-layout-evidence-v1"


def state_region(props):
    """Explicit state field or full postal suffix only; conflicting evidence is held."""
    explicit = [str(props[k]).strip().casefold() for k in ("addr:state", "state") if props.get(k)]
    codes = {REGIONS.get(value) for value in explicit}
    full = props.get("addr:full") or ""
    match = re.search(r",\s*([^,]+?)\s+\d{5}(?:-\d{4})?\s*$", str(full))
    postal = REGIONS.get(match[1].strip().casefold()) if match else None
    if explicit:
        if None in codes or len(codes) != 1:
            return None, "unrecognized_or_conflicting_state"
        code = next(iter(codes))
        if postal and postal != code:
            return None, "conflicting_postal_state"
        return code, "explicit_state"
    return (postal, "postal_suffix") if postal else (None, "state_unknown")


def branch_url(value):
    """Qualify a supplied HTTPS HTML URL without guessing aliases or fetching it."""
    if not isinstance(value, str) or len(value) > 2048:
        return None, "branch_url_missing"
    try:
        parsed = urlsplit(value)
        approved_url(value, [f"https://{parsed.hostname}"])
        safe_link(value, value, allow_query=True)
        if parsed.path in ("", "/"):
            return None, "generic_homepage"
        if re.search(r"\.(?:pdf|png|jpe?g|svg|webp|json|xml)$", parsed.path, re.IGNORECASE):
            return None, "not_branch_html"
        if parsed.hostname in {"localhost"} or "." not in parsed.hostname:
            return None, "non_public_host"
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return value, "needs_live_robots_and_branch_review"
    except (ValueError, PolicyError, CrawlBlocked):
        pass
    return None, "unsafe_or_unsupported_url"


def _write_lines(path, rows):
    with path.open("w") as output:
        for row in rows:
            output.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")


def stage(archive, output, *, source_run, expected_sha256, progress=lambda _: None):
    """Stream one pinned archive once; bad scopes roll back locally, never prove absence."""
    archive, output = Path(archive), Path(output)
    if not source_run or file_hash(archive) != expected_sha256:
        raise ValueError("archive_pin_mismatch")
    members = validate_zip(archive, max_members=10000, max_expanded_bytes=200 * 1024**3)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier reviewed bundle.
    db = sqlite3.connect(output / "roster.sqlite")
    db.execute(
        "CREATE TABLE stores(state,spider,source_key,payload,PRIMARY KEY(spider,source_key))"
    )
    errors, counters, seen, scanned = [], Counter(), set(), 0
    try:
        with ZipFile(archive) as package:
            for member in members:
                if member.is_dir() or PurePosixPath(member.filename).suffix != ".geojson":
                    continue
                spider = PurePosixPath(member.filename).stem
                if spider in seen:
                    raise ValueError("duplicate_source_scope")
                seen.add(spider)
                if member.file_size > 2 * 1024**3:
                    errors.append({"spider": spider, "error": "member_byte_limit"})
                    continue
                db.execute("SAVEPOINT scope")
                scope_counts = Counter()
                try:
                    with package.open(member) as stream:
                        if next(ijson.items(stream, "type"), None) != "FeatureCollection":
                            raise ValueError("invalid_feature_collection")
                        stream.seek(0)
                        for feature in ijson.items(stream, "features.item", use_float=True):
                            scanned += 1
                            props = feature.get("properties") or {}
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
                            if (
                                spider not in ATP_DESCRIPTORS
                                and str(props.get("shop", "")).casefold() not in GROCERY_SHOPS
                            ):
                                continue
                            code, evidence = state_region(props)
                            if not code:
                                scope_counts[evidence] += 1
                                continue
                            row = _atp_feature(feature, spider, ATP_DESCRIPTORS.get(spider))
                            if row is None:
                                scope_counts["format_or_banner_withheld"] += 1
                                continue
                            payload = row["payload"]
                            payload["address"]["region"] = code
                            payload["region_evidence"] = evidence
                            db.execute(
                                "INSERT INTO stores VALUES(?,?,?,?)",
                                (
                                    code,
                                    spider,
                                    row["source_key"],
                                    json.dumps(payload, allow_nan=False),
                                ),
                            )
                            scope_counts["accepted"] += 1
                            if scope_counts["accepted"] > 250000:
                                raise ValueError("scope_candidate_limit")
                    db.execute("RELEASE scope")
                    counters.update(scope_counts)
                except (
                    ValueError,
                    TypeError,
                    AttributeError,
                    ijson.JSONError,
                    sqlite3.IntegrityError,
                ) as failure:
                    db.execute("ROLLBACK TO scope")
                    db.execute("RELEASE scope")
                    errors.append({"spider": spider, "error": type(failure).__name__})
                progress({"scopes_scanned": len(seen), "features_scanned": scanned})
        db.commit()
        result = _plans(db, output, source_run, expected_sha256)
        result.update(
            source_archive_bytes=archive.stat().st_size,
            features_scanned=scanned,
            scopes_scanned=len(seen),
            failed_scopes=errors,
            filter_counts=dict(counters),
        )
        atomic_json(output / "coverage.json", result)
        files = {
            str(p.relative_to(output)): file_hash(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        }
        atomic_json(
            output / "bundle.json", {"version": 1, "status": "staged_not_started", "files": files}
        )
        return result
    finally:
        db.close()


def _plans(db, output, source_run, archive_hash):
    summaries, all_hosts, url_refs = [], set(), {}
    for code, name in JURISDICTIONS.items():
        directory = output / code
        directory.mkdir(exist_ok=True)
        rows, targets, gaps, banners, fields = [], [], Counter(), Counter(), Counter()
        chains = {}
        for spider, key, raw in db.execute(
            "SELECT spider,source_key,payload FROM stores WHERE state=? ORDER BY spider,source_key",
            (code,),
        ):
            payload = json.loads(raw)
            row = {"partition": spider, "kind": "store", "source_key": key, "payload": payload}
            rows.append(row)
            banners[payload["chain_key"]] += 1
            chain = chains.setdefault(
                payload["chain_key"],
                {
                    "source_chain_key": payload["chain_key"],
                    "name": payload["chain_name"],
                    "source_assertions": 0,
                    "spiders": set(),
                    "official_hosts": set(),
                    "identity_status": "candidate_requires_location_reconciliation",
                },
            )
            chain["source_assertions"] += 1
            chain["spiders"].add(spider)
            for field in ("website", "phone", "hours", "latitude", "longitude"):
                fields[field] += payload.get(field) is not None
            for field in ("street", "city", "postal_code", "full"):
                fields["address." + field] += bool(payload["address"].get(field))
            url, reason = branch_url(payload.get("website"))
            if not url:
                gaps[reason] += 1
                continue
            all_hosts.add(urlsplit(url).hostname)
            chain["official_hosts"].add(urlsplit(url).hostname)
            url_refs.setdefault(url, []).append(
                {"state": code, "partition": spider, "source_key": key}
            )
            targets.append(
                {
                    "state": code,
                    "partition": spider,
                    "source_key": key,
                    "source_id": payload["source_id"],
                    "name": payload["name"],
                    "source_website": url,
                    "url": url,
                    "source_address": payload["address"],
                    "source_chain_key": payload["chain_key"],
                    "expected_branch": payload["address"].get("street")
                    or payload["address"].get("full")
                    or payload["name"],
                    "qualification": reason,
                }
            )
        _write_lines(directory / "roster.jsonl", rows)
        _write_lines(directory / "targets.jsonl", targets)
        atomic_json(
            directory / "chains.json",
            [
                {
                    **chain,
                    "spiders": sorted(chain["spiders"]),
                    "official_hosts": sorted(chain["official_hosts"]),
                }
                for chain in chains.values()
            ],
        )
        plan = {
            "version": 1,
            "campaign_id": f"us-{code.lower()}-{source_run}",
            "state": code,
            "name": name,
            "status": "staged_not_started",
            "enabled": False,
            "source_run": source_run,
            "archive_sha256": archive_hash,
            "roster_sha256": file_hash(directory / "roster.jsonl"),
            "targets_sha256": file_hash(directory / "targets.jsonl"),
            "source_assertions": len(rows),
            "candidate_banners": len(banners),
            "targets": len(targets),
            "unique_target_urls": len({t["url"] for t in targets}),
            "gaps": dict(gaps),
            "field_completeness": dict(fields),
            "census_complete": False,
            "collection_profile": PROFILE,
            "capture_policy": {
                "store_details": True,
                "maps": True,
                "aisle_department_evidence": True,
                "product_catalog": False,
                "product_inventory": False,
                "prices": False,
                "product_page_fetches": False,
            },
            "contact": "hello@foldlab.app",
            "limits": {
                "min_spacing": 45,
                "max_pages_day_per_host": 50,
                "host_concurrency": 1,
                "max_batch_targets": 25,
                "max_html_bytes": 524288,
                "automatic_retries": 0,
            },
            "decisions": {
                "provider": "jev",
                "enabled": False,
                "calls": 0,
                "global_cap_nanousd": 5_000_000_000,
                "budget_scope": "shared_existing_ledger",
            },
            "activation_required": [
                "resolve published canonical store IDs and current address snapshot",
                "review exact branch targets and cross-state URL duplicates",
                "fresh live robots.txt, stricter crawl delay and shared host frontier",
                "explicit remaining Jev budget and protected key path",
                "single serial worker, no overlapping Iowa campaign",
            ],
            "excluded": [
                "private household data",
                "login/cart/search",
                "map/image/PDF downloads",
                "automatic product pagination",
                "inferred stock, aisles or route geometry",
            ],
        }
        atomic_json(directory / "plan.json", plan)
        summaries.append(
            {
                k: plan[k]
                for k in (
                    "state",
                    "name",
                    "source_assertions",
                    "candidate_banners",
                    "targets",
                    "unique_target_urls",
                    "gaps",
                    "field_completeness",
                )
            }
        )
    _write_lines(
        output / "host-queue.jsonl",
        [
            {
                "url": url,
                "host": urlsplit(url).hostname,
                "references": refs,
                "qualification": "duplicate_identity_review"
                if len(refs) > 1
                else "needs_live_robots_and_branch_review",
            }
            for url, refs in sorted(
                url_refs.items(), key=lambda item: (urlsplit(item[0]).hostname, item[0])
            )
        ],
    )
    return {
        "status": "staged_not_started",
        "states": summaries,
        "state_count": len(STATES),
        "dc_separate": True,
        "census_complete": False,
        "source": "All The Places",
        "license": "CC0-1.0",
        "source_run": source_run,
        "archive_sha256": archive_hash,
        "unique_hosts": sorted(all_hosts),
        "stores": sum(s["source_assertions"] for s in summaries),
        "targets": sum(s["targets"] for s in summaries),
        "unique_target_urls": len(url_refs),
        "duplicate_target_urls_held": sum(len(refs) > 1 for refs in url_refs.values()),
        "retailer_requests": 0,
        "paid_calls": 0,
        "limitations": [
            "Source assertions are not reconciled unique physical locations or a complete census",
            "Missing/failed source scopes are coverage gaps, never closure evidence",
            "Targets require branch and robots qualification; no generated retailer URLs",
            "No catalog publication, job enqueue, scheduler registration or source activation",
        ],
    }


def verify_bundle(directory):
    directory = Path(directory)
    bundle = json.loads((directory / "bundle.json").read_text())
    if bundle.get("status") != "staged_not_started" or bundle.get("version") != 1:
        raise ValueError("invalid_bundle")
    for name, expected in bundle["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or file_hash(path) != expected:
            raise ValueError("bundle_hash_mismatch")
    for code in JURISDICTIONS:
        plan = json.loads((directory / code / "plan.json").read_text())
        if plan["enabled"] is not False or plan["state"] != code:
            raise ValueError("staging_activation_or_state_mismatch")
    return json.loads((directory / "coverage.json").read_text())
