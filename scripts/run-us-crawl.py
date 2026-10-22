"""Verify/prepare staged state batches; networking requires a separate explicit --run.

Preparation does not import the roster, enable a source, create jobs or call Jev.
Prepared configs start disabled. Use one worker and the existing shared Tower data root.
"""

import argparse
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

from bord_food_api.crawl_history import prior_holds
from bord_food_api.nationwide import JURISDICTIONS, PROFILE, REGIONS, verify_bundle
from bord_food_api.platform import Platform, atomic_json

spec = importlib.util.spec_from_file_location(
    "state_campaign", Path(__file__).with_name("run-iowa-crawl.py")
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def prepare(bundle, state, platform, *, offset=0, limit=25):
    verify_bundle(bundle)
    if state not in JURISDICTIONS or offset < 0 or not 1 <= limit <= 25:
        raise ValueError("invalid_state_batch")
    directory = Path(bundle) / state
    plan = json.loads((directory / "plan.json").read_text())
    by_source = {}
    for store in platform.records("store"):
        key = (store.get("spider"), store.get("source_id"))
        by_source.setdefault(key, []).append(store)
    candidates = [
        json.loads(line) for line in (directory / "targets.jsonl").read_text().splitlines()
    ]
    duplicated = {
        row["url"]
        for row in (
            json.loads(line)
            for line in (Path(bundle) / "host-queue.jsonl").read_text().splitlines()
        )
        if len(row["references"]) > 1
    }
    targets, held, seen = [], [], set()
    for row in candidates[offset : offset + limit]:
        if row["url"] in duplicated:
            held.append(
                {
                    "source_key": row["source_key"],
                    "reason": "cross_state_or_source_url_identity_review",
                }
            )
            continue
        matches = by_source.get((row["partition"], row["source_id"]), [])
        if len(matches) != 1:
            held.append(
                {
                    "source_key": row["source_key"],
                    "reason": "catalog_import_or_identity_review_required",
                }
            )
            continue
        store = matches[0]
        if (
            store.get("website") != row["url"]
            or store.get("name") != row["name"]
            or REGIONS.get(str(store.get("address", {}).get("region", "")).casefold()) != state
        ):
            held.append({"source_key": row["source_key"], "reason": "published_branch_changed"})
            continue
        history = prior_holds(platform.root, {"store_id": store["id"], "url": row["url"]})
        if history:
            held.append(
                {
                    "source_key": row["source_key"],
                    "reason": "prior_history_hold",
                    "history": history,
                }
            )
            continue
        if row["url"] in seen:
            held.append({"source_key": row["source_key"], "reason": "duplicate_branch_url"})
            continue
        seen.add(row["url"])
        targets.append(
            {
                "store_id": store["id"],
                "name": store["name"],
                "chain_id": store["chain_id"],
                "spider": store["spider"],
                "source_website": store["website"],
                "url": row["url"],
                "source_address": store["address"],
                "expected_branch": row["expected_branch"],
            }
        )
    scopes = {}
    for target in targets:
        host = urlsplit(target["url"]).hostname
        scopes[host] = {
            "state": "staged",
            "review_evidence": None,
            "crawl": {
                "global_enabled": False,
                "adapter_enabled": False,
                "source_authorized": False,
                "terms_reviewed": False,
                "owner_public_robots_authorized": True,
                "robots_reviewed": False,
                "contact": plan["contact"],
                "allowed_host": host,
                "scope_prefix": "/",
                "allow_exact_target_queries": True,
                "min_spacing": 45,
                "max_pages_day": 50,
                "max_pages_run": 2,
                "max_bytes": 524288,
            },
        }
    return {
        "campaign_id": plan["campaign_id"] + f"-b{offset}",
        "state": state,
        "activation_enabled": False,
        "collection_profile": PROFILE,
        "source_bundle_sha256": plan["archive_sha256"],
        "catalog_generation": (platform.current() or {}).get("generation"),
        "batch": {"offset": offset, "limit": limit, "total_candidates": len(candidates)},
        "targets": targets,
        "held": held,
        "scopes": scopes,
        "decisions": {"max_calls": 0, "budget_nanousd": 0, "key_file": ""},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--state", choices=JURISDICTIONS)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--prepare", type=Path, help="Write a disabled batch config; no network")
    parser.add_argument(
        "--run", type=Path, help="Explicitly run an independently activated prepared config"
    )
    args = parser.parse_args()
    report = verify_bundle(args.bundle)
    if args.prepare and args.run:
        parser.error("choose preparation or execution")
    if args.prepare:
        if not args.state or not args.data_dir:
            parser.error("preparation needs --state and --data-dir")
        if args.prepare.exists():
            parser.error("refusing to overwrite an existing prepared config")
        config = prepare(
            args.bundle, args.state, Platform(args.data_dir), offset=args.offset, limit=args.limit
        )
        atomic_json(args.prepare, config)
        print(
            json.dumps(
                {
                    "network": False,
                    "activation_enabled": False,
                    "targets": len(config["targets"]),
                    "held": len(config["held"]),
                }
            )
        )
    elif args.run:
        if not args.data_dir:
            parser.error("execution needs the shared --data-dir")
        config = json.loads(args.run.read_text())
        if (
            config.get("activation_enabled") is not True
            or config.get("collection_profile") != PROFILE
            or config.get("state") not in JURISDICTIONS
            or config.get("source_bundle_sha256") != report["archive_sha256"]
            or not 1 <= len(config.get("targets", [])) <= 25
        ):
            raise ValueError("explicit_validated_activation_required")
        # The runner still checks every branch snapshot, scopes and budget before
        # constructing a paid transport or unpausing a source. No parallel states.
        result = campaign.run(config, args.data_dir)
        print(json.dumps({"state": result["state"], "campaign_id": config["campaign_id"]}))
        if result["state"] != "finished":
            raise SystemExit(1)
    else:
        print(
            json.dumps(
                {
                    "network": False,
                    "status": report["status"],
                    "states": report["state_count"],
                    "stores": report["stores"],
                    "targets": report["targets"],
                    "dc_separate": True,
                }
            )
        )


if __name__ == "__main__":
    main()
