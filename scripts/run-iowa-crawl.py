"""Explicit multi-retailer Iowa map-link campaign; no built-in source activation.

Uses source-backed catalog branches and independently reviewed exact host scopes.
Blocked/unsupported hosts stay in coverage reports and are never replaced by guesses.
"""

import argparse
import hashlib
import importlib.util
import json
import signal
import time
from pathlib import Path
from urllib.parse import urlsplit

from bord_food_api.crawl_runtime import run_map_discovery, validate_map_discovery
from bord_food_api.crawlers import CrawlBlocked
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import Lease, heavy_lock
from bord_food_api.transport import PolicyError, TransportError

spec = importlib.util.spec_from_file_location(
    "reviewed", Path(__file__).with_name("run-reviewed-crawl.py")
)
reviewed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewed)
SOURCE = "retailer_maps"


class CampaignStopped(RuntimeError):
    pass


def validate(config, platform):
    identifier = config.get("campaign_id", "")
    if (
        not identifier
        or len(identifier) > 80
        or not all(c.isalnum() or c in "-_" for c in identifier)
    ):
        raise ValueError("invalid_campaign_id")
    targets = config.get("targets", [])
    if not 1 <= len(targets) <= 100:
        raise ValueError("target_limit")
    if (
        not 1 <= config["decisions"]["max_calls"] <= 100
        or not 0 < config["decisions"]["budget_nanousd"] <= 1_000_000_000
    ):
        raise ValueError("decision_limit")
    seen = set()
    for target in targets:
        branch = platform.get("store", target["store_id"])
        observed = target.get("observed_url_evidence") or {}
        observed_match = (
            observed.get("store_id") == target["store_id"]
            and observed.get("url") == target["url"]
            and observed.get("evidence_url") == target["url"]
            and observed.get("kind") == "observed_official_branch_page"
            and observed.get("source_address") == (branch or {}).get("address")
            and bool(observed.get("reviewed_at"))
        )
        if (
            not branch
            or str(branch.get("address", {}).get("region", "")).upper() not in ("IA", "IOWA")
            or branch.get("website") != target["source_website"]
            or (target["url"] != target["source_website"] and not observed_match)
            or branch.get("spider") != target["spider"]
            or branch.get("chain_id") != target["chain_id"]
            or branch.get("name") != target["name"]
        ):
            raise ValueError("source_backed_iowa_branch_required")
        host = urlsplit(target["url"]).hostname
        scope = config["scopes"].get(host, {})
        if scope.get("state") != "approved" or not scope.get("review_evidence"):
            raise ValueError("host_access_review_required")
        crawl = {**scope["crawl"], "approved_targets": [target]}
        if (
            crawl["allowed_host"] != host
            or crawl["min_spacing"] < 30
            or crawl["max_pages_day"] > 50
            or crawl["max_pages_run"] != 2
            or crawl["max_bytes"] > 524288
        ):
            raise ValueError("host_limit")
        validate_map_discovery(crawl)
        if target["url"] in seen or urlsplit(target["url"]).path in ("", "/"):
            raise ValueError("distinct_branch_urls_required")
        seen.add(target["url"])
    return targets


def run(config, root, *, judge_factory=reviewed.Judge, discover=run_map_discovery):
    platform = Platform(root)
    targets = validate(config, platform)  # No source unpause/paid calls before full validation.
    directory = Path(root) / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "status.json"
    if path.exists():
        raise ValueError("campaign_already_started")
    status = {
        "state": "starting",
        "campaign_id": config["campaign_id"],
        "targets": len(targets),
        "completed": [],
        "active": None,
        "started_at": time.time(),
        "blocked_hosts": {},
    }
    stopped = [False]
    signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stopped.__setitem__(0, True))
    judge = judge_factory(root, {**config["decisions"], "campaign_id": config["campaign_id"]})
    atomic_json(path, status)

    def check():
        if (
            stopped[0]
            or (directory / "STOP").exists()
            or not platform.control.enabled(SOURCE)
            or time.time() - status["started_at"] > 7200
        ):
            raise CampaignStopped("operator_or_campaign_stop")

    with heavy_lock(root):
        platform.recover()
        platform.control.set_source(SOURCE, True)
        try:
            status["state"] = "running"
            for index, target in enumerate(targets):
                check()
                host = urlsplit(target["url"]).hostname
                item = {"store_id": target["store_id"], "host": host}
                if host in status["blocked_hosts"]:
                    status["completed"].append({**item, "state": "host_deferred"})
                    atomic_json(path, status)
                    continue
                status.update(active=target["store_id"], phase="jev_before_fetch")
                atomic_json(path, status)
                try:
                    judge.before(target)
                except reviewed.ReviewRequired:
                    status["completed"].append({**item, "state": "review_required"})
                    atomic_json(path, status)
                    continue
                job_id = platform.control.enqueue(
                    SOURCE,
                    host,
                    operation="operator_discover_map",
                    version=f"{config['campaign_id']}:{index}",
                )
                job = platform.control.claim(config["campaign_id"], ttl=120, job_id=job_id)
                if not job:
                    raise ValueError("job_claim_failed")
                with Lease(platform.control, job, 120, 20) as lease:
                    lease.policy_check = check
                    crawl = {
                        **config["scopes"][host]["crawl"],
                        "approved_targets": [target],
                        "_check": lease.check,
                        "min_spacing": max(
                            config["scopes"][host]["crawl"]["min_spacing"],
                            30
                            + (
                                int(hashlib.sha256(target["url"].encode()).hexdigest()[:4], 16) % 16
                            ),
                        ),
                    }
                    status["phase"] = "robots_and_branch_fetch"
                    atomic_json(path, status)
                    try:
                        result = discover(
                            platform,
                            job,
                            crawl,
                            transport_factory=reviewed.reviewed_transport(judge, target),
                        )
                        platform.control.finish(job)
                        item.update(
                            state="published", map_records=result["map_records"], job_id=job_id
                        )
                    except reviewed.ReviewRequired:
                        platform.control.finish(job, reason="machine_review_required")
                        item.update(state="review_required", job_id=job_id)
                    except (CrawlBlocked, TransportError, PolicyError) as error:
                        # No source retry or proxy fallback; other reviewed hosts can proceed.
                        platform.control.finish(
                            job, state="failed", reason="host_access_or_budget_block"
                        )
                        reason = type(error).__name__
                        status["blocked_hosts"][host] = reason
                        item.update(state="host_blocked", reason=reason, job_id=job_id)
                    except BaseException:
                        platform.control.finish(
                            job, state="failed", reason="campaign_stopped_or_invalid"
                        )
                        raise
                status["completed"].append(item)
                atomic_json(path, status)
            status.update(state="finished", active=None, completed_at=time.time())
        except BaseException as error:  # noqa: BLE001 - Persist a sanitized stop state and pause.
            status.update(state="stopped", error_type=type(error).__name__, stopped_at=time.time())
        finally:
            platform.control.set_source(SOURCE, False)
            atomic_json(path, status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.plan:
        targets = validate(config, Platform(args.data_dir))
        print(
            json.dumps(
                {
                    "network": False,
                    "campaign_id": config["campaign_id"],
                    "targets": len(targets),
                    "hosts": sorted({urlsplit(x["url"]).hostname for x in targets}),
                }
            )
        )
    else:
        result = run(config, args.data_dir)
        print(json.dumps(result))
        if result["state"] != "finished":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
