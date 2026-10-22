"""Read-only, offline analysis. Usage: python analyze.py snapshot.json SOURCE_DIRECTORY."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bord_food_api.chain_profiles import profile_for
from bord_food_api.store_enrichment import normalize
from bord_food_api.store_quality import location_key, same_brand
from bord_food_api.store_sources import osm_fields, place_candidate


def analyze(snapshot, candidates=(), places=()):
    rows = snapshot["stores"]
    assert len({r["id"] for r in rows}) == len(rows)
    chains = {r["id"]: r["name"] for r in snapshot["chains"]}
    segments = defaultdict(list)
    by_address = defaultdict(list)
    for r in rows:
        label = (
            chains.get(r.get("chain_id")) or profile_for(r).get("brand") or "Independent / unmapped"
        )
        segments[label].append(r)
        if key := location_key(r):
            by_address[key].append(r)
    fields = ("phone", "website", "opening_hours")
    counts = {f: sum(bool(r.get(f)) for r in rows) for f in fields}
    missing = {f: [r for r in rows if not r.get(f)] for f in fields}
    summary = []
    for label, group in sorted(segments.items(), key=lambda p: -len(p[1])):
        summary.append(
            {
                "segment": label,
                "stores": len(group),
                **{f: sum(bool(r.get(f)) for r in group) for f in fields},
                "missing_phone": sum(not r.get("phone") for r in group),
                "missing_hours": sum(not r.get("opening_hours") for r in group),
            }
        )
    evidence = {}
    for f in fields:
        causes = Counter()
        for r in missing[f]:
            e = [e for e in r.get("field_evidence", []) if e.get("field") == f]
            if not e:
                cause = "no_retained_field_assertion"
            elif any(
                e.get("eligible") and not e.get("superseded") and not e.get("withdrawn") for e in e
            ):
                cause = "eligible_evidence_but_no_selected_value"
            else:
                cause = "only_invalid_ineligible_stale_or_withdrawn_assertions"
            causes[cause] += 1
        evidence[f] = {
            "missing_stores": len(missing[f]),
            "causes": dict(causes),
            "present_status": dict(
                Counter(
                    r.get("field_provenance", {}).get(f, {}).get("status", "no_metadata")
                    for r in rows
                    if r.get(f)
                )
            ),
            "raw_invalid": sum(_invalid(f, r[f]) for r in rows if r.get(f)),
        }
    schedule = Counter()
    for r in rows:
        v = r.get("opening_hours")
        if v:
            try:
                n = normalize("opening_hours", v)
                schedule["seven_days" if len({x["day"] for x in n}) == 7 else "partial_week"] += 1
            except (ValueError, TypeError, KeyError):
                schedule["invalid"] += 1
    child = snapshot["statuses"]["iowa-quality-continuation-20261020-primary"]
    targets = child.get("targets", {})
    gaps = {i for i, t in targets.items() if t.get("state") == "missing_branch_url"}
    gap_sources = Counter()
    gap_examples = []
    for r in rows:
        if r["id"] not in gaps:
            continue
        urls = [r.get("website")]
        for e in r.get("field_evidence", []):
            if e.get("field") == "website":
                urls += [e.get("raw_value")]
        values = [u for u in urls if isinstance(u, str) and u]
        kind = (
            "no_website_evidence"
            if not values
            else "http_only"
            if all(u.startswith("http://") for u in values)
            else "social_only"
            if all(any(d in u for d in ("facebook.", "instagram.", "twitter.")) for u in values)
            else "unsupported_ambiguous_or_shared_website"
        )
        gap_sources[kind] += 1
        if values and len(gap_examples) < 14:
            gap_examples.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "address": r["address"],
                    "values": list(dict.fromkeys(values)),
                    "missing_phone": not r.get("phone"),
                    "missing_hours": not r.get("opening_hours"),
                }
            )
    conflict_shapes = Counter()
    for r in missing["opening_hours"]:
        values = [
            e["value"]
            for e in r.get("field_evidence", [])
            if e.get("field") == "opening_hours" and e.get("eligible")
        ]
        maps = []
        for value in values:
            days = defaultdict(set)
            for span in value:
                days[span["day"]].add((span["opens"], span["closes"], span.get("closed", False)))
            maps.append(dict(days))
        if len(maps) > 1:
            same = all(all(a[d] == b[d] for d in a.keys() & b.keys()) for a in maps for b in maps)
            conflict_shapes[
                "agree_on_overlapping_days" if same else "disagree_on_overlapping_days"
            ] += 1
            if same and any(len(m) == 7 for m in maps):
                conflict_shapes["overlap_agrees_and_full_week_available"] += 1
    source_coverage = {}
    gain_union = {f: set() for f in fields}
    for name, items in [("openstreetmap", candidates), ("overture_places", places)]:
        eligible = [c for c in items if name != "openstreetmap" or c["source"] == name]
        field_counts = Counter()
        matched = set()
        gains = {f: set() for f in fields}
        novel = {f: set() for f in fields}
        samples = []
        for c in eligible:
            if name == "openstreetmap":
                p = c["payload"]
                values = osm_fields(p.get("source_record") or p.get("tags") or p)
            else:
                candidate = place_candidate(name, c)
                if candidate["category"] == "exclude":
                    continue
                p = candidate["payload"]
                values = {
                    f: c[k][0]
                    for f, k in [("phone", "phones"), ("website", "websites")]
                    if c.get(k)
                }
            field_counts.update(values.keys())
            key = location_key(p)
            matches = [r for r in by_address.get(key, []) if same_brand(r, p)] if key else []
            if len(matches) != 1:
                continue
            r = matches[0]
            matched.add(r["id"])
            for f in fields:
                if f in values and not r.get(f) and not _invalid(f, values[f]):
                    gains[f].add(r["id"])
                    gain_union[f].add(r["id"])
                    if not any(
                        e.get("field") == f and e.get("source_id") == name
                        for e in r.get("field_evidence", [])
                    ):
                        novel[f].add(r["id"])
                    if len(samples) < 10:
                        samples.append(
                            {
                                "id": r["id"],
                                "name": r["name"],
                                "field": f,
                                "candidate_value": values[f],
                                "note": "exact-address/name candidate; not published or independently verified",
                            }
                        )
        source_coverage[name] = {
            "source_assertions": len(eligible),
            "scope_filtered_fields_present": dict(field_counts),
            "exact_unique_current_store_matches": len(matched),
            "possible_missing_fields_from_exact_join": {f: len(ids) for f, ids in gains.items()},
            "no_prior_same_source_field_assertion": {f: len(ids) for f, ids in novel.items()},
            "examples": samples,
        }
    target_states = {
        f: dict(
            Counter(
                targets.get(r["id"], {}).get(
                    "state", "preserved_prior_outcome_or_not_in_current_child"
                )
                for r in missing[f]
            )
        )
        for f in ("phone", "opening_hours")
    }
    return {
        "captured_at": snapshot["captured_at"],
        "generation": snapshot["generation"],
        "manifest_stable": snapshot["manifest_stable"],
        "stores": len(rows),
        "counts": counts,
        "missing": {f: len(v) for f, v in missing.items()},
        "segments": summary,
        "evidence": evidence,
        "schedule": dict(schedule),
        "missing_hours_conflict_shapes": dict(conflict_shapes),
        "retained_sources_union_possible": {f: len(ids) for f, ids in gain_union.items()},
        "known_chain_phone_scope": sum(
            r.get("contact_channels", {}).get("phone", {}).get("scope") == "chain" for r in rows
        ),
        "missing_url_gaps": len(gaps),
        "gap_sources": dict(gap_sources),
        "gap_examples": gap_examples,
        "missing_field_campaign_state": target_states,
        "current_campaign": {
            k: child.get(k) for k in ["state", "phase", "updated_at", "counts", "blocked_hosts"]
        },
        "sources": source_coverage,
    }


def _invalid(field, value):
    try:
        normalize(field, value)
        return False
    except (ValueError, TypeError, KeyError, AttributeError):
        return True


if __name__ == "__main__":
    snapshot = json.loads(Path(sys.argv[1]).read_text())
    root = Path(sys.argv[2])

    def records(name):
        return [json.loads(l) for l in (root / name).read_text().splitlines() if l.strip()]

    result = analyze(
        snapshot,
        records("iowa-phone-hours-candidates.jsonl"),
        records("iowa-phone-hours-places.jsonl"),
    )
    Path(sys.argv[1]).with_name("analysis.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"gap_examples", "sources", "segments"}},
            indent=2,
        )
    )
    print("SEGMENTS", json.dumps(result["segments"][:12]))
    print("SOURCES", json.dumps(result["sources"]))
