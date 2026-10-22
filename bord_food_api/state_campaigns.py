"""Small-state planning and retained-roster preparation; no source transports."""

import copy
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .crawl_history import prior_holds
from .domain import content_hash
from .nationwide import PROFILE, REGIONS, STATES, branch_url
from .store_quality import clean_store, location_key, same_brand
from .transport import file_hash

GROCERY_TYPES = frozenset(
    {
        "Grocery Store",
        "Supermarket",
        "Super Store",
        "Large Grocery Store",
        "Medium Grocery Store",
        "Small Grocery Store",
    }
)


def rank_states(reference, *, roster_counts=None, catalog_counts=None):
    """One row per state; SNAP grocery formats are a workload proxy, not a census."""
    counts, seen = Counter(), set()
    for row in reference["groups"]:
        key = row["State"], row["Store_Type"]
        value = row["store_count"]
        if key in seen or key[0] not in STATES or type(value) is not int or value < 0:
            raise ValueError("invalid_state_reference_group")
        seen.add(key)
        if key[1] in GROCERY_TYPES:
            counts[key[0]] += value
    if (
        set(counts) != set(STATES)
        or sum(r["store_count"] for r in reference["groups"])
        != reference["reference_rows_all_formats"]
    ):
        raise ValueError("state_reference_incomplete")
    return [
        {
            "rank": index,
            "state": state,
            "name": STATES[state],
            "snap_grocery_format_records": count,
            "retained_roster_assertions": (roster_counts or {}).get(state),
            "published_stores_before": (catalog_counts or {}).get(state),
            "census_complete": False,
        }
        for index, (state, count) in enumerate(
            sorted(counts.items(), key=lambda item: (item[1], item[0])), 1
        )
    ]


def group_states(ranked, *, count=12, capacity=650, max_states=3):
    selected = [r for r in ranked if r["state"] != "IA"][:count]
    batches, current = [], []
    for row in selected:
        if current and (
            len(current) == max_states
            or sum(r["snap_grocery_format_records"] for r in current)
            + row["snap_grocery_format_records"]
            > capacity
            or row["snap_grocery_format_records"] > 2.2 * current[0]["snap_grocery_format_records"]
        ):
            batches.append(current)
            current = []
        current.append(row)
    if current:
        batches.append(current)
    return [
        {
            "batch": i,
            "states": [r["state"] for r in rows],
            "snap_reference_workload": sum(r["snap_grocery_format_records"] for r in rows),
        }
        for i, rows in enumerate(batches, 1)
    ]


def new_roster_records(platform, bundle, state):
    """Only new native ATP identities; existing or co-located assertions stay untouched."""
    if state not in STATES or state == "IA":
        raise ValueError("explicit_new_state_required")
    directory = Path(bundle) / state
    plan = json.loads((directory / "plan.json").read_text())
    if plan["state"] != state or file_hash(directory / "roster.jsonl") != plan["roster_sha256"]:
        raise ValueError("state_roster_binding_invalid")
    current = list(platform.iter_records("store"))
    locations = defaultdict(list)
    for store in current:
        if key := location_key(store):
            locations[key].append(store)
    records, held, seen = [], [], set()
    source_time = (
        datetime.strptime(plan["source_run"], "%Y-%m-%d-%H-%M-%S").replace(tzinfo=UTC).timestamp()
    )
    for line in (directory / "roster.jsonl").read_text().splitlines():
        row = json.loads(line)
        key = row["source_key"]
        if key in seen:
            raise ValueError("duplicate_roster_identity")
        seen.add(key)
        p = clean_store(copy.deepcopy(row["payload"]))
        if REGIONS.get(str((p.get("address") or {}).get("region", "")).casefold()) != state:
            raise ValueError("roster_wrong_state")
        if platform.get_by_source("store", "all_the_places", key):
            held.append({"source_key": key, "reason": "existing_native_identity_preserved"})
            continue
        if p.get("directory_scope", {}).get("status") == "excluded":
            held.append({"source_key": key, "reason": "excluded_store_format"})
            continue
        location = location_key(p)
        if not location:
            held.append({"source_key": key, "reason": "structured_premises_required"})
            continue
        if any(same_brand(s, p) for s in locations[location]):
            held.append({"source_key": key, "reason": "possible_duplicate_requires_review"})
            continue
        p["address"]["region"] = state
        p.update(
            source_run=plan["source_run"],
            source_observed_at=source_time,
            source_snapshot_complete=False,
            source_scope="retained_partial_state_roster",
            census_complete=False,
        )
        records.append({"kind": "store", "source_key": key, "payload": p})
        locations[location].append(p)
    return {
        "state": state,
        "records": records,
        "held": held,
        "source_roster_assertions": len(seen),
        "release": content_hash(records),
        "source_run": plan["source_run"],
        "archive_sha256": plan["archive_sha256"],
    }


def prepare_targets(platform, state):
    targets, gaps, seen = [], [], set()
    all_rows = list(platform.iter_records("store"))
    owners = defaultdict(set)
    for row in all_rows:
        if row.get("website"):
            owners[row["website"]].add(row["id"])
    rows = [
        r
        for r in all_rows
        if REGIONS.get(str(r.get("address", {}).get("region", "")).casefold()) == state
    ]
    for store in rows:
        url, reason = branch_url(store.get("website"))
        target = {
            "store_id": store["id"],
            "name": store["name"],
            "chain_id": store.get("chain_id"),
            "spider": store.get("spider"),
            "url": url,
            "source_website": store.get("website"),
            "source_address": store.get("address"),
            "expected_branch": (store.get("address") or {}).get("street") or store["name"],
        }
        if url and not location_key(store):
            reason, url = "structured_premises_required", None
        holds = prior_holds(platform.root, target) if url else []
        shared = url and len(owners[url]) > 1
        if not url or url in seen or holds or shared:
            gaps.append(
                {
                    "store_id": store["id"],
                    "source_address": store.get("address"),
                    "reason": "prior_history_hold"
                    if holds
                    else "shared_url_identity_review"
                    if shared
                    else "duplicate_branch_url"
                    if url in seen
                    else reason,
                    "retry_policy": "manual_review",
                }
            )
            continue
        seen.add(url)
        targets.append(target)
    # Rotate hosts so each pilot covers several retailers when possible.
    hosts = defaultdict(list)
    by_id = {row["id"]: row for row in rows}
    for t in sorted(
        targets,
        key=lambda t: (bool(by_id[t["store_id"]].get("opening_hours")), t["url"]),
    ):
        hosts[urlsplit(t["url"]).hostname].append(t)
    ordered = []
    while any(hosts.values()):
        for host in sorted(hosts):
            if hosts[host]:
                ordered.append(hosts[host].pop(0))
    return {"state": state, "directory_stores": len(rows), "targets": ordered, "gaps": gaps}


def field_config(state, targets, *, campaign_id, directory_stores, pilot=False):
    scopes = {}
    for target in targets:
        host = urlsplit(target["url"]).hostname
        scopes[host] = {
            "state": "approved",
            "review_evidence": "Owner-authorized smaller-state public branch scan; robots, exact source identity and prior holds still required",
            "crawl": {
                "global_enabled": True,
                "adapter_enabled": True,
                "source_authorized": True,
                "owner_public_robots_authorized": True,
                "terms_reviewed": False,
                "robots_reviewed": True,
                "contact": "hello@foldlab.app",
                "allowed_host": host,
                "scope_prefix": "/",
                "max_pages_run": 3,
                "max_pages_day": 500,
                "max_bytes": 2097152,
                "max_total_bytes": 6291456,
                "min_spacing": 45,
                "spacing_jitter_seconds": 45,
                "max_run_seconds": 600,
                "robots_ttl_seconds": 3600,
                "allow_exact_target_queries": True,
                "can_store_raw": True,
                "page_cache_enabled": True,
                "report_redirects": True,
            },
        }
    return {
        "campaign_id": campaign_id,
        "activation_enabled": True,
        "state": state,
        "collection_profile": PROFILE,
        "field_focus": True,
        "capture_prices": False,
        "capture_product_inventory": False,
        "capture_product_catalog": False,
        "targets": targets,
        "scopes": scopes,
        "duration_seconds": 2 * 3600,
        "directory_stores": directory_stores,
        "missing_branch_urls": 0,
        "coverage_gaps": [],
        "decisions": {
            "max_calls": 100,
            "budget_nanousd": 1000000000,
            "global_budget_nanousd": 15000000000,
            "key_file": "/run/secrets/jev-api-key",
            "retain_branch_html": True,
            "review_every_page": pilot,
        },
        "canonical_followup_enabled": True,
        "post_pass_review": {"enabled": False},
    }
