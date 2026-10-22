"""Reconcile retained directory/page evidence, with no network or model requests.

Default prepares a reviewable plan. --publish atomically replaces the stores pack.
Known shared provider lineage never counts as a second corroborating source.
"""

import argparse
import copy
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from bord_food_api.crawl_evidence import retailer_assertions
from bord_food_api.domain import content_hash
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.store_discovery import entity_names_compatible
from bord_food_api.store_enrichment import (
    enrichment_digest,
    publish_enrichment,
    reconcile_fields,
    reparse_assertions,
    snapshot_assertions,
)
from bord_food_api.store_quality import location_key
from bord_food_api.store_sources import place_candidate, source_assertions


def hold_shared_provider_emails(stores, evidence):
    """Retain shared contacts without presenting them as branch-specific email."""
    locations = defaultdict(set)
    for store in stores:
        for row in [*store.get("field_evidence", []), *evidence[store["id"]]]:
            if row.get("field") == "email" and row.get("validation") == "valid":
                locations[str(row["value"]).casefold()].add(store["id"])
    result = copy.deepcopy(stores)
    count = 0
    for store in result:
        for row in [*store.get("field_evidence", []), *evidence[store["id"]]]:
            if (
                row.get("field") == "email"
                and row.get("validation") == "valid"
                and row.get("source_id") != "retailer_page"
                and len(locations[str(row["value"]).casefold()]) > 1
            ):
                row.update(
                    withdrawn=True,
                    contact_scope="shared_across_locations",
                    shared_location_count=len(locations[str(row["value"]).casefold()]),
                    withdrawal_reason="provider_contact_shared_across_distinct_store_ids_requires_branch_scope_review",
                )
                count += 1
    return result, count


def prepare(root, *, state=None, places=(), reviews=(), now=None):
    root = Path(root)
    now = now or time.time()
    platform = Platform(root)
    manifest = platform.current()
    stores = list(platform.iter_records("store"))
    stores = [r for r in stores if not state or (r.get("address") or {}).get("region") == state]
    by_id = {r["id"]: r for r in stores}
    by_address = defaultdict(list)
    for row in stores:
        if key := location_key(row):
            by_address[key].append(row)
    dataset_links = defaultdict(list)
    evidence = defaultdict(list)
    blocks = []
    for row in stores:
        evidence[row["id"]].extend(snapshot_assertions(row, source_id=row.get("catalog_source")))
        evidence[row["id"]].extend(reparse_assertions(row))
    # Canonical association comes from the previously reviewed directory crosswalk,
    # not from proximity or model similarity. Only known matched IDs are accepted.
    for directory in sorted((root / "discovery").glob("*/bundle.json"), reverse=True):
        bundle = json.loads(directory.read_text())
        if state and bundle.get("state") not in {None, state}:
            continue
        crosswalk = directory.parent / "crosswalk.jsonl"
        candidates = directory.parent / "candidates.jsonl"
        if not crosswalk.is_file() or not candidates.is_file():
            continue
        aliases = {key: row["id"] for row in stores for key in row.get("discovery_keys", [])}
        for line in crosswalk.read_text().splitlines():
            item = json.loads(line)
            canonical = manifest.get("redirects", {}).get(
                item.get("canonical_id"), item.get("canonical_id")
            )
            if canonical in by_id:
                aliases[item["source_key"]] = canonical
        for line in candidates.read_text().splitlines():
            candidate = json.loads(line)
            identity = aliases.get(candidate["source_key"])
            match_kind = "reviewed_crosswalk"
            if (
                not identity
                and candidate["source"] == "openstreetmap"
                and candidate.get("category") == "include"
            ):
                matches = [
                    s
                    for s in by_address.get(location_key(candidate["payload"]), [])
                    if entity_names_compatible(s, candidate["payload"])
                ]
                if len(matches) == 1:
                    identity = matches[0]["id"]
                    match_kind = "exact_address"
            if not identity:
                continue
            payload = candidate["payload"]
            dataset_links[identity].append(
                {
                    "source_id": candidate["source"],
                    "record_id": candidate["source_key"],
                    "source_url": payload.get("source_url"),
                    "observed_at": payload.get("source_observed_at"),
                    "retrieved_at": bundle.get("acquired_at"),
                    "relationship": "snap_authorization_snapshot"
                    if candidate["source"] == "usda_snap_arcgis"
                    else "place_assertion",
                    "product_inventory_evidence": False,
                }
            )
            if candidate["source"] != "openstreetmap":
                continue
            payload = candidate["payload"]
            evidence[identity].extend(
                source_assertions(
                    "openstreetmap",
                    payload,
                    by_id[identity],
                    record_id=candidate["source_key"],
                    source_url=payload["source_url"],
                    checked_at=bundle.get("acquired_at"),
                    branch_match=match_kind,
                    source_revision=bundle.get("candidate_sha256"),
                )
            )
        break
    for path in sorted((root / "crawl-campaigns").glob("*/evidence/*.json")):
        saved = json.loads(path.read_text())
        identity = saved.get("store_id")
        if identity not in by_id:
            continue
        if saved.get("field_assertions"):
            evidence[identity].extend(saved["field_assertions"])
            continue
        candidates = saved.get("store_candidates", [])
        if saved.get("branch_match") != "exact_address" or len(candidates) != 1:
            blocks.append(
                {
                    "source": "retailer_page",
                    "store_id": identity,
                    "reason": "ambiguous_legacy_page_evidence",
                    "file": path.relative_to(root).as_posix(),
                }
            )
            continue
        candidate = candidates[0]
        target = {
            "store_id": identity,
            "url": saved["source_url"],
            "country": by_id[identity].get("country", "US"),
        }
        rows = retailer_assertions(
            candidate["fields"], candidate["source_path"], [], target, saved["retrieved_at"]
        )
        for row in rows:
            row["source_revision"] = saved.get("html_sha256")
            row["id"] = content_hash(
                {k: v for k, v in row.items() if k not in {"id", "checked_at", "observed_at"}}
            )
        evidence[identity].extend(rows)
    for source, path in places:
        with Path(path).open() as stream:
            for line in stream:
                row = json.loads(line)
                candidate = place_candidate(source, row)
                if candidate["category"] == "exclude":
                    blocks.append(
                        {
                            "source": source,
                            "record_id": candidate["source_key"],
                            "reason": candidate["reason"],
                        }
                    )
                    continue
                matches = [
                    s
                    for s in by_address.get(location_key(candidate["payload"]), [])
                    if entity_names_compatible(s, candidate["payload"])
                ]
                if len(matches) != 1:
                    blocks.append(
                        {
                            "source": source,
                            "record_id": candidate["source_key"],
                            "reason": "exact_branch_identity_unresolved",
                        }
                    )
                    continue
                target = matches[0]
                # The extract must carry acquisition provenance; absent clocks
                # remain stale/unverified rather than using this process's time.
                source_url = row.get("_source_url") or (
                    "https://foursquare.com/placemakers/review-place/" + candidate["source_key"]
                    if source == "foursquare_os"
                    else "https://docs.overturemaps.org/guides/places/"
                )
                dataset_links[target["id"]].append(
                    {
                        "source_id": source,
                        "record_id": candidate["source_key"],
                        "source_url": source_url,
                        "retrieved_at": row.get("_retrieved_at"),
                        "release_id": row.get("_release"),
                        "record_version": row.get("version"),
                        "provider_existence_confidence": row.get("confidence"),
                        "confidence_scope": "place_existence_not_field_accuracy",
                        "providers": [
                            {
                                k: s.get(k)
                                for k in (
                                    "dataset",
                                    "license",
                                    "property",
                                    "record_id",
                                    "update_time",
                                )
                            }
                            for s in row.get("sources", [])
                        ],
                        "relationship": "exact_address_name_place_assertion",
                        "product_inventory_evidence": False,
                    }
                )
                evidence[target["id"]].extend(
                    source_assertions(
                        source,
                        row,
                        target,
                        record_id=candidate["source_key"],
                        source_url=source_url,
                        checked_at=row.get("_retrieved_at"),
                        branch_match="exact_address",
                        source_revision=row.get("version"),
                    )
                )
    stores, shared_contacts = hold_shared_provider_emails(stores, evidence)
    updates = []
    states = Counter()
    promoted = Counter()
    conflicts = Counter()
    for row in stores:
        applicable = [
            r for r in reviews if any(a["id"] == r.get("assertion_id") for a in evidence[row["id"]])
        ]
        result = reconcile_fields(row, evidence[row["id"]], now=now, reviews=applicable)
        for field, meta in result["field_provenance"].items():
            states[meta["status"]] += 1
            if meta["status"] in {"corroborated", "reviewed", "derived"}:
                promoted[field] += 1
            if meta["status"] == "conflicted":
                conflicts[field] += 1
        result["dataset_links"] = list(
            {
                (link.get("source_id"), link.get("record_id")): link
                for link in [*row.get("dataset_links", []), *dataset_links.get(row["id"], [])]
            }.values()
        )
        updates.append(result)
    return {
        "base_generation": manifest["generation"],
        "state_filter": state,
        "prepared_at": now,
        "stores": len(updates),
        "field_statuses": dict(states),
        "promoted_or_derived": dict(promoted),
        "conflicts": dict(conflicts),
        "blocks": blocks,
        "release": enrichment_digest(updates),
        "records": updates,
        "source_network_requests": 0,
        "paid_calls": 0,
        "shared_email_assertions_held": shared_contacts,
    }


def run(root, directory, *, publish=False, state=None, places=(), reviews=()):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with heavy_lock(root):
        plan = prepare(root, state=state, places=places, reviews=reviews)
        records = plan.pop("records")
        with (directory / "records.jsonl").open("w") as out:
            for row in records:
                out.write(json.dumps(row, allow_nan=False) + "\n")
        atomic_json(directory / "plan.json", plan)
        if publish:
            result = publish_enrichment(
                Platform(root),
                records,
                base_generation=plan["base_generation"],
                release=plan["release"],
                now=plan["prepared_at"],
            )
            atomic_json(
                directory / "publication.json",
                {
                    **plan,
                    "state": "published",
                    "changed": result["changed"],
                    "generation": result["manifest"]["generation"],
                },
            )
        return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--state")
    parser.add_argument(
        "--places",
        action="append",
        default=[],
        help="overture_places=FILE.jsonl or foursquare_os=FILE.jsonl; retained extracts only",
    )
    parser.add_argument("--reviews", type=Path)
    args = parser.parse_args()
    places = [tuple(v.split("=", 1)) for v in args.places]
    reviews = json.loads(args.reviews.read_text()) if args.reviews else []
    print(
        json.dumps(
            run(
                args.data_dir,
                args.run_dir,
                publish=args.publish,
                state=args.state,
                places=places,
                reviews=reviews,
            )
        )
    )


if __name__ == "__main__":
    main()
