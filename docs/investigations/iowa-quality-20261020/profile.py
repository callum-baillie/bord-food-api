import collections
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from bord_food_api.store_discovery import (
    EXCLUDED_NAMES,
    address_key,
    distance,
    entity_names_compatible,
    specialist_name,
    valid_coordinates,
)
from bord_food_api.store_enrichment import normalize


def profile(s):
    rows = s["stores"]
    now = s["captured_at"]
    n = len(rows)
    chains = {r["id"]: r for r in s["chains"]}
    fields = [
        "phone",
        "website",
        "opening_hours",
        "timezone",
        "email",
        "departments",
        "pickup_links",
        "delivery_links",
        "accessibility",
        "hours_exceptions",
        "entrances",
        "aisle_category_mappings",
    ]
    result = {
        "captured_at": now,
        "generation": s["generation"],
        "stores": n,
        "all_stores": s["all_store_count"],
        "manifest_stable": s["manifest_unchanged_during_read"],
        "fields": [],
    }
    for f in fields:
        present = [r for r in rows if r.get(f)]
        status = collections.Counter(
            r.get("field_provenance", {}).get(f, {}).get("status", "missing_metadata")
            for r in present
        )
        valid = []
        invalid = []
        for r in present:
            try:
                normalize(f, r[f])
                valid.append(r["id"])
            except (ValueError, TypeError, KeyError, AttributeError):
                invalid.append({"id": r["id"], "name": r["name"], "value": r[f]})
        verified = [
            r
            for r in present
            if r.get("field_provenance", {}).get(f, {}).get("status")
            in {"corroborated", "reviewed"}
            and (r["field_provenance"][f].get("verified_until") or 0) > now
        ]
        result["fields"].append(
            {
                "field": f,
                "present": len(present),
                "coverage": len(present) / n,
                "status": dict(status),
                "current_independent_or_reviewed": len(verified),
                "normalizes": len(valid),
                "invalid_count": len(invalid),
                "invalid_examples": invalid[:6],
            }
        )
    basic = {
        "id_missing": sum(not r.get("id") for r in rows),
        "id_duplicate_count": n - len({r["id"] for r in rows}),
        "name_missing": sum(not r.get("name") for r in rows),
        "source_refs_missing": sum(not r.get("source_refs") for r in rows),
        "attribution_missing": sum(not r.get("attribution") for r in rows),
        "license_missing": sum(not r.get("license") for r in rows),
        "chain_orphans": sum(bool(r.get("chain_id")) and r["chain_id"] not in chains for r in rows),
        "address_key_missing": sum(address_key(r) is None for r in rows),
        "postcode_missing": sum(
            not (
                r.get("address", {}).get("postal_code")
                or re.search(r"\b\d{5}(?:-\d{4})?\b", r.get("address", {}).get("full", ""))
            )
            for r in rows
        ),
    }
    coords = [r for r in rows if r.get("latitude") is not None and r.get("longitude") is not None]
    basic.update(
        coordinates_present=len(coords),
        invalid_coordinates=sum(not valid_coordinates(r) for r in rows),
        closed_status=dict(collections.Counter(r.get("operating_status", "missing") for r in rows)),
        permanently_closed_true=sum(r.get("permanently_closed") is True for r in rows),
        excluded_name_candidates=[
            {"id": r["id"], "name": r["name"]} for r in rows if EXCLUDED_NAMES.search(r["name"])
        ],
        specialist_name_candidates=[
            {"id": r["id"], "name": r["name"]} for r in rows if specialist_name(r["name"])
        ],
    )
    result["basics"] = basic
    address = collections.defaultdict(list)
    phones = collections.defaultdict(list)
    webs = collections.defaultdict(list)
    emails = collections.defaultdict(list)
    for r in rows:
        if key := address_key(r):
            address[key].append(r)
        for f, index in [("phone", phones), ("website", webs), ("email", emails)]:
            if r.get(f):
                try:
                    key = normalize(f, r[f])
                    index[key].append(r)
                except ValueError:
                    pass

    def examples(groups):
        return [
            {
                "key": str(k),
                "count": len(v),
                "stores": [{"id": r["id"], "name": r["name"], "address": r["address"]} for r in v],
            }
            for k, v in groups.items()
            if len(v) > 1
        ]

    result["duplicate_review"] = {
        "same_address_groups": examples(address),
        "same_phone_groups": examples(phones),
        "same_website_groups": examples(webs),
        "shared_email_groups": examples(emails),
        "nearby_compatible_pairs": [],
    }
    for a, b in itertools.combinations(rows, 2):
        d = distance(a, b)
        if d < 100 and entity_names_compatible(a, b):
            result["duplicate_review"]["nearby_compatible_pairs"].append(
                {
                    "a": a["id"],
                    "b": b["id"],
                    "a_name": a["name"],
                    "b_name": b["name"],
                    "distance_metres": round(d, 1),
                    "a_address": a["address"],
                    "b_address": b["address"],
                }
            )
    result["conflicts"] = {
        "count": sum(len(r.get("field_conflicts", [])) for r in rows),
        "stores": sum(bool(r.get("field_conflicts")) for r in rows),
        "fields": dict(
            collections.Counter(c["field"] for r in rows for c in r.get("field_conflicts", []))
        ),
    }
    result["freshness"] = {
        "assertion_future_dates": sum(
            isinstance(e.get("checked_at"), (int, float)) and e["checked_at"] > now + 60
            for r in rows
            for e in r.get("field_evidence", [])
        ),
        "source_reported_nonnull_verification_dates": sum(
            m.get("status") == "source_reported"
            and (m.get("verified_at") is not None or m.get("verified_until") is not None)
            for r in rows
            for m in r.get("field_provenance", {}).values()
        ),
        "stale_field_count": sum(
            m.get("status") == "stale" for r in rows for m in r.get("field_provenance", {}).values()
        ),
    }
    age = collections.Counter()
    for r in rows:
        for e in r.get("field_evidence", []):
            if e.get("eligible") and e.get("field") in {
                "phone",
                "website",
                "email",
                "opening_hours",
            }:
                clock = e.get("observed_at")
                age["eligible_total"] += 1
                if isinstance(clock, (int, float)):
                    days = (now - clock) / 86400
                    age[
                        "under_30_days"
                        if days <= 30
                        else "30_to_180_days"
                        if days <= 180
                        else "over_180_days"
                    ] += 1
                else:
                    age["observation_time_unknown"] += 1
    result["freshness"]["eligible_core_assertion_observation_age"] = dict(age)
    segments = collections.defaultdict(list)
    for r in rows:
        segments[chains.get(r.get("chain_id"), {}).get("name") or "Independent / unmapped"].append(
            r
        )
    result["segments"] = [
        {
            "chain": k,
            "stores": len(v),
            **{
                f: sum(bool(r.get(f)) for r in v)
                for f in ["phone", "website", "opening_hours", "email"]
            },
            "conflicted_stores": sum(bool(r.get("field_conflicts")) for r in v),
        }
        for k, v in sorted(segments.items(), key=lambda x: -len(x[1]))
    ]
    core = [
        r
        for r in rows
        if r.get("phone")
        and r.get("website")
        and r.get("opening_hours")
        and r.get("timezone")
        and r.get("latitude") is not None
        and r.get("longitude") is not None
    ]
    result["complete_core_bundle"] = len(core)
    result["complete_core_bundle_without_conflicts"] = sum(
        not r.get("field_conflicts") for r in core
    )
    result["campaigns"] = {
        k: {f: v.get(f) for f in ["state", "phase", "counts", "active", "error_type", "updated_at"]}
        for k, v in s["campaigns"].items()
    }
    result["pack_counts"] = s["pack_counts"]
    result["off"] = {
        k: s["off"].get(k) for k in ["state", "selected_products", "error_type", "phase"]
    }
    return result


if __name__ == "__main__":
    result = profile(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"duplicate_review", "segments"}}, indent=2
        )
    )
    print("SEGMENTS", json.dumps(result["segments"][:12]))
    print("DUPLICATE GROUPS", {k: len(v) for k, v in result["duplicate_review"].items()})
