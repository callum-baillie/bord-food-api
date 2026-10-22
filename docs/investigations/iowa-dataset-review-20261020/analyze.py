"""Reproducible offline profile of a read-only Iowa crawl/directory snapshot."""

import collections
import gzip
import json
import math
import pathlib
from datetime import UTC, datetime

from bord_food_api.store_discovery import address_key


def present(value):
    return value not in (None, "", [], {}, "unknown", "unverified")


def percent(count, total):
    return round(100 * count / total, 1) if total else None


def analyze(v):
    stored = [r for r in v["entities"]["stores"] if r["kind"] == "store"]
    stores = {r["payload"]["id"]: r["payload"] for r in stored}
    ids_by_key = {
        r["source_key"]: r["payload"]["id"] for r in stored if r["source"] == "iowa_store_discovery"
    }
    discovery = v["discovery"]
    candidates = {r["source_key"]: r for r in discovery["candidates.jsonl"]}
    aliases = {}
    for row in discovery["crosswalk.jsonl"]:
        key = row["source_key"]
        canonical = row.get("canonical_id") or ids_by_key.get(row.get("proposed_key"))
        assert canonical in stores, "Crosswalk target missing from current Iowa generation"
        assert key not in aliases, "Native key appears twice"
        aliases[key] = canonical
    linked = collections.defaultdict(set)
    for key, canonical in aliases.items():
        linked[candidates[key]["source"]].add(canonical)
    pilot = next(c for c in v["campaigns"] if c["directory"] == "iowa-chains-20261019")
    pilot_completed = {
        t["store_id"] for t in pilot["status"]["completed"] if t["state"] == "published"
    }
    state = next(c for c in v["campaigns"] if c["directory"] == "iowa-statewide-20261019")
    targets = state["status"]["targets"]
    evidence = [e["payload"] for e in state["evidence"]]
    evidence_ids = {e["store_id"] for e in evidence}
    exact = [e for e in evidence if e["branch_match"] == "exact_address"]
    completed_ids = evidence_ids | pilot_completed
    fetched_ids = completed_ids | {
        key for key, t in targets.items() if t.get("reason") == "page_review"
    }
    assert len(evidence_ids) == len(evidence) == 95
    assert all(key in stores for key in targets)
    snap = [r for r in candidates.values() if r["source"] == "usda_snap_arcgis"]
    osm = [r for r in candidates.values() if r["source"] == "openstreetmap"]
    types = collections.Counter(r["payload"]["source_record"]["Store_Type"] for r in snap)
    raw_osm = [r["payload"]["source_record"] for r in osm]
    source_rows = []
    for name, rows in [("usda_snap_arcgis", snap), ("openstreetmap", osm)]:
        source_keys = {r["source_key"] for r in rows}
        linked_ids = linked[name]
        reviewed = [r for r in discovery["reviews.jsonl"] if r["source"] == name]
        excluded = [r for r in discovery["excluded.jsonl"] if r["source"] == name]
        outcomes = collections.Counter(
            r["state"] for r in discovery["crosswalk.jsonl"] if r["source_key"] in source_keys
        )
        assert sum(outcomes.values()) + len(reviewed) + len(excluded) == len(rows)
        source_rows.append(
            {
                "source": name,
                "raw_assertions": len(rows),
                "new_primary_records": sum(
                    r["source"] == "iowa_store_discovery" and r["source_key"] in source_keys
                    for r in stored
                ),
                "matched_assertions": sum(n for k, n in outcomes.items() if k != "new"),
                "review_assertions": len(reviewed),
                "excluded_assertions": len(excluded),
                "linked_directory_stores": len(linked_ids),
                "linked_saved_crawl_pages": len(evidence_ids & linked_ids),
                "linked_completed_crawl_stores": len(completed_ids & linked_ids),
                "completed_crawl_denominator": len(completed_ids),
                "saved_crawl_denominator": len(evidence_ids),
                "both_source_linked_stores": len(
                    linked["usda_snap_arcgis"] & linked["openstreetmap"]
                ),
            }
        )
    fields = {
        "Name": lambda x: present(x.get("name")),
        "Usable postal address": lambda x: address_key(x) is not None,
        "Structured street and city": lambda x: (
            present((x.get("address") or {}).get("street"))
            and present((x.get("address") or {}).get("city"))
        ),
        "Coordinates": lambda x: all(
            type(x.get(k)) in (float, int) and math.isfinite(x[k])
            for k in ("latitude", "longitude")
        ),
        "Website": lambda x: present(x.get("website")),
        "Phone": lambda x: present(x.get("phone")) or present(x.get("telephone")),
        "Hours": lambda x: (
            present(x.get("hours"))
            or present(x.get("openingHours"))
            or present(x.get("openingHoursSpecification"))
        ),
        "Timezone": lambda x: present(x.get("timezone")),
        "Known opening or closure status": lambda x: (
            present(x.get("open_status")) or x.get("closed") in (True, False)
        ),
    }
    field_rows = [
        {
            "field": name,
            "present": sum(check(x) for x in stores.values()),
            "total": len(stores),
            "percent": percent(sum(check(x) for x in stores.values()), len(stores)),
        }
        for name, check in fields.items()
    ]
    crawl_fields = []
    for name, rawkeys in [
        ("Address", ["address"]),
        ("Phone", ["telephone"]),
        ("Hours", ["openingHours", "openingHoursSpecification"]),
        ("Coordinates", ["geo"]),
        ("Departments", ["department"]),
    ]:
        count = sum(
            any(present(e["store_candidates"][0]["fields"].get(k)) for k in rawkeys) for e in exact
        )
        crawl_fields.append(
            {
                "field": name,
                "pages": count,
                "saved_pages": len(evidence),
                "percent_saved": percent(count, len(evidence)),
                "directory_records": len(stores),
                "percent_directory": percent(count, len(stores)),
                "acceptance": "review_required",
            }
        )
    crawl_by_chain = collections.defaultdict(lambda: collections.Counter())
    for key, t in targets.items():
        chain = stores[key].get("chain_name") or "Unknown chain"
        crawl_by_chain[chain][t["state"]] += 1
    for e in evidence:
        crawl_by_chain[stores[e["store_id"]].get("chain_name") or "Unknown chain"][
            "exact_branch_match"
        ] += e["branch_match"] == "exact_address"
    maps = [x["payload"] for x in v["entities"]["maps"]]
    ia_maps = [
        m for m in maps if m.get("store_id") in stores or m.get("intended_store_id") in stores
    ]
    all_campaign_summary = []
    for c in v["campaigns"]:
        s = c["status"]
        all_campaign_summary.append(
            {
                "campaign": c["directory"],
                "state": s.get("state"),
                "status_keys": sorted(s),
                "evidence_files": len(c["evidence"]),
            }
        )
    enrichment_opportunities = {}
    for label, missing, candidate in [
        (
            "Missing coordinates with linked SNAP coordinates",
            lambda p: p.get("latitude") is None or p.get("longitude") is None,
            lambda c: (
                c["source"] == "usda_snap_arcgis"
                and c["payload"].get("latitude") is not None
                and c["payload"].get("longitude") is not None
            ),
        ),
        (
            "Missing phone with linked OSM phone",
            lambda p: not (p.get("phone") or p.get("telephone")),
            lambda c: (
                c["source"] == "openstreetmap"
                and bool(
                    c["payload"]["source_record"].get("phone")
                    or c["payload"]["source_record"].get("contact:phone")
                )
            ),
        ),
        (
            "Missing hours with linked OSM hours",
            lambda p: not p.get("hours"),
            lambda c: (
                c["source"] == "openstreetmap"
                and bool(c["payload"]["source_record"].get("opening_hours"))
            ),
        ),
        (
            "Missing website with linked OSM website",
            lambda p: not p.get("website"),
            lambda c: c["source"] == "openstreetmap" and bool(c["payload"].get("website")),
        ),
    ]:
        enrichment_opportunities[label] = len(
            {
                canonical
                for key, canonical in aliases.items()
                if missing(stores[canonical]) and candidate(candidates[key])
            }
        )
    address_counts = collections.Counter(address_key(row) for row in stores.values())
    chain_ids = {row["payload"]["id"] for row in v["entities"]["stores"] if row["kind"] == "chain"}
    quality_checks = {
        "unique_directory_ids": len(stores) == len(stored),
        "unique_native_candidate_keys": len(candidates) == len(discovery["candidates.jsonl"]),
        "all_crosswalk_targets_resolve": all(key in stores for key in aliases.values()),
        "orphan_chain_links": sum(
            bool(row.get("chain_id")) and row["chain_id"] not in chain_ids
            for row in stores.values()
        ),
        "shared_normalized_address_groups": sum(n > 1 for key, n in address_counts.items() if key),
        "coordinates_outside_iowa_rectangle": sum(
            row.get("latitude") is not None
            and not (40.3 <= row["latitude"] <= 43.6 and -96.8 <= row["longitude"] <= -90)
            for row in stores.values()
        ),
    }
    out = {
        "quality_checks": quality_checks,
        "captured_at": v["captured_at"],
        "generation": v["manifest"]["generation"],
        "definitions": {
            "source_assertion": "A native record; sources overlap and include out-of-scope formats.",
            "saved_crawl_page": "Unique statewide campaign store ID with a retained evidence JSON file, regardless of acceptance.",
            "exact_branch_match": "One JSON-LD candidate matches the expected street and postal code or city/state; not a current operational audit.",
            "field_present": "Published top-level field is populated; provenance can be bulk rather than crawler.",
            "accepted_enrichment": "An evidence item promoted from review_required to accepted; none in this snapshot.",
        },
        "directory_records": len(stores),
        "directory_keys_unique": len(stores) == len(stored),
        "raw_source_counts": {"snap": len(snap), "osm": len(osm)},
        "snap_types": dict(types),
        "snap_broad_grocery_types_before_exclusions": sum(
            types[k] for k in ["Grocery Store", "Supermarket", "Super Store"]
        ),
        "source_reconciliation": source_rows,
        "crawl": {
            "completed_iowa_stores_all_campaigns": len(completed_ids),
            "unique_stores_reaching_page_review_all_iowa": len(fetched_ids),
            "completed_share_of_current_directory": percent(len(completed_ids), len(stores)),
            "target_count": len(targets),
            "saved_evidence_pages": len(evidence),
            "share_of_current_directory_saved": percent(len(evidence_ids), len(stores)),
            "share_of_original_directory_saved": percent(len(evidence_ids), 362),
            "target_outcomes": dict(collections.Counter(t["state"] for t in targets.values())),
            "review_reasons": dict(
                collections.Counter(
                    t.get("reason") for t in targets.values() if t["state"] == "review_required"
                )
            ),
            "exact_branch_pages": len(exact),
            "ambiguous_multi_candidate_pages": sum(
                len(e["store_candidates"]) > 1 for e in evidence
            ),
            "no_matching_structured_candidate_pages": sum(
                not e["store_candidates"] for e in evidence
            ),
            "accepted_evidence_pages": sum(e["acceptance_status"] == "accepted" for e in evidence),
            "visible_text_excerpts": sum(bool(e.get("visible_text_excerpt")) for e in evidence),
            "excerpts_at_limit": sum(
                len(e.get("visible_text_excerpt", "")) >= 4500 for e in evidence
            ),
            "interior_map_candidates": sum(len(e["interior_map_candidates"]) for e in evidence),
            "item_placement_candidates": sum(len(e["item_placement_candidates"]) for e in evidence),
            "geographic_map_links": sum(len(e["geographic_map_links"]) for e in evidence),
            "department_evidence_pages": sum(bool(e["layout_evidence"]) for e in evidence),
            "retrieved_from": datetime.fromtimestamp(
                min(e["retrieved_at"] for e in evidence), UTC
            ).isoformat(),
            "retrieved_to": datetime.fromtimestamp(
                max(e["retrieved_at"] for e in evidence), UTC
            ).isoformat(),
            "missing_urls_original_directory": state["status"]["missing_branch_urls"],
            "state": state["status"]["state"],
        },
        "published_directory_fields": field_rows,
        "crawler_fields_single_branch": crawl_fields,
        "enrichment_opportunities": enrichment_opportunities,
        "osm_shop_types": dict(
            collections.Counter(c["payload"]["source_record"].get("shop") for c in osm)
        ),
        "raw_osm_fields": {
            "hours": sum(bool(x.get("opening_hours")) for x in raw_osm),
            "website": sum(bool(x.get("website") or x.get("contact:website")) for x in raw_osm),
            "phone": sum(bool(x.get("phone") or x.get("contact:phone")) for x in raw_osm),
            "wheelchair": sum(bool(x.get("wheelchair")) for x in raw_osm),
        },
        "crawl_by_chain": [
            {"chain": k, **dict(counts)} for k, counts in sorted(crawl_by_chain.items())
        ],
        "iowa_map_records": len(ia_maps),
        "iowa_map_status": dict(collections.Counter(m.get("discovery_status") for m in ia_maps)),
        "iowa_validated_maps": sum(m.get("layout_validated") is True for m in ia_maps),
        "iowa_display_permitted_maps": sum(m.get("display_permitted") is True for m in ia_maps),
        "all_regions_map_status": dict(
            collections.Counter(m.get("discovery_status") for m in maps)
        ),
        "campaign_inventory": all_campaign_summary,
        "checksums": v["sha256"],
    }
    return out


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("input", type=pathlib.Path)
    p.add_argument("output", type=pathlib.Path)
    args = p.parse_args()
    snapshot = json.loads(gzip.decompress(args.input.read_bytes()))
    profile = analyze(snapshot)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: profile[k]
                for k in [
                    "directory_records",
                    "raw_source_counts",
                    "snap_broad_grocery_types_before_exclusions",
                    "source_reconciliation",
                    "crawl",
                    "published_directory_fields",
                    "crawler_fields_single_branch",
                    "raw_osm_fields",
                    "iowa_map_status",
                ]
            },
            indent=2,
        )
    )
