"""Explicit-state field campaign with one bounded canonical-URL follow-up pass.

Primary redirects are retained. Follow-up URLs come only from observed same-site
www/slash redirects or the explicitly reviewed ALDI locator migration. Each URL
gets fresh robots authorization; no branch redirect is implicitly followed.
"""

import argparse
import copy
import importlib.util
import json
import signal
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bord_food_api.crawl_history import CrawlHistory
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.store_enrichment import public_url

spec = importlib.util.spec_from_file_location(
    "campaign_fields", Path(__file__).with_name("run-iowa-fields.py")
)
fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fields)


def canonical_followup(config, status, platform):
    mappings = []
    by_id = {t["store_id"]: t for t in config["targets"]}
    for identity, item in status.get("targets", {}).items():
        old = by_id.get(identity)
        destination = item.get("redirect_candidate")
        if not old or item.get("http_status") not in {301, 302, 307, 308} or not destination:
            continue
        try:
            target = public_url(destination)
            parsed = urlsplit(target)
            source = urlsplit(old["url"])
        except ValueError:
            continue
        if parsed.scheme != "https" or "[redacted]" in target or "%5Bredacted%5D" in target:
            continue
        www_alias = parsed.hostname.removeprefix("www.") == source.hostname.removeprefix("www.")
        same_path = (
            parsed.path.rstrip("/") == source.path.rstrip("/") and parsed.query == source.query
        )
        aldi_migration = (
            source.hostname in {"stores.aldi.us", "info.aldi.us"}
            and parsed.hostname == "www.aldi.us"
            and parsed.path.startswith(
                "/store/aldi/pages/locator/l/" + config["state"].lower() + "/"
            )
            and not parsed.query
        )
        robots = item.get("stage") == "robots" and parsed.path == "/robots.txt" and not parsed.query
        if www_alias and (robots or same_path):
            mappings.append((source.hostname, parsed.hostname, identity, target, robots, item))
        elif aldi_migration and item.get("stage") == "branch_page":
            mappings.append((source.hostname, parsed.hostname, identity, target, False, item))
    targets = []
    scopes = {}
    seen = set()
    for old in config["targets"]:
        item = status.get("targets", {}).get(old["store_id"], {})
        if item.get("state") not in {"host_blocked", "prior_history_hold"}:
            continue
        source = urlsplit(old["url"])
        mapping = next(
            (m for m in mappings if m[0] == source.hostname and (m[4] or m[2] == old["store_id"])),
            None,
        )
        if not mapping:
            continue
        _old_host, new_host, _identity, observed, robots, proof = mapping
        row = platform.get("store", old["store_id"])
        if (
            not row
            or row.get("address") != old.get("source_address")
            or row.get("name") != old["name"]
        ):
            continue
        url = (
            urlunsplit(("https", new_host, source.path or "/", source.query, ""))
            if robots
            else observed
        )
        if url in seen:
            continue
        seen.add(url)
        t = {
            **old,
            "source_website": row.get("website"),
            "url": url,
            "canonical_review_required": True,
        }
        t["observed_url_evidence"] = {
            "kind": "observed_official_branch_page",
            "store_id": row["id"],
            "url": url,
            "evidence_url": url,
            "source_address": row["address"],
            "reviewed_at": proof["finished_at"],
            "note": "Bounded canonical rule: observed HTTPS www/slash redirect or reviewed ALDI migration. Robots and exact branch identity still required",
            "redirect_proof": {
                "source_url": old["url"],
                "location": observed,
                "http_status": proof["http_status"],
                "stage": proof.get("stage"),
            },
        }
        if urlsplit(url).path in ("", "/"):
            t["single_store_site"] = True
        targets.append(t)
        scope = copy.deepcopy(config["scopes"][source.hostname])
        scope["crawl"].update(allowed_host=new_host, scope_prefix="/")
        # A robots alias may be retried only as a separate bounded robots fetch.
        scope["crawl"]["robots_redirect_hosts"] = (
            [new_host.removeprefix("www.")]
            if new_host.startswith("www.")
            else ["www." + new_host]
            if new_host.count(".") == 1
            else []
        )
        scopes[new_host] = scope
    return {
        **config,
        "campaign_id": config["campaign_id"] + "-canonical",
        "targets": targets,
        "scopes": scopes,
        "coverage_gaps": [],
        "missing_branch_urls": 0,
    }


def retained_canonical_targets(config, root):
    """Reuse only successful prior canonical routing for an unchanged identity."""
    proposals = {}
    for path in Path(root).glob("crawl-campaigns/iowa-fields-*/canonical-config.json"):
        previous = json.loads(path.read_text())
        status_path = Path(root) / "crawl-campaigns" / previous["campaign_id"] / "status.json"
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text())
        for target in previous["targets"]:
            item = status.get("targets", {}).get(target["store_id"], {})
            if item.get("state") == "published":
                stamp = item.get("finished_at", 0)
                if stamp > proposals.get(target["store_id"], (0, None))[0]:
                    proposals[target["store_id"]] = stamp, target
    result = copy.deepcopy(config)
    for index, target in enumerate(result["targets"]):
        prior = proposals.get(target["store_id"])
        if not prior:
            continue
        saved = prior[1]
        if (
            target.get("source_address") != saved.get("source_address")
            or target["name"] != saved["name"]
            or target.get("source_website") != saved.get("source_website")
        ):
            continue
        replacement = {**saved, "source_website": target["source_website"]}
        result["targets"][index] = replacement
        host = urlsplit(replacement["url"]).hostname
        old_host = urlsplit(target["url"]).hostname
        scope = copy.deepcopy(result["scopes"][old_host])
        scope["crawl"].update(allowed_host=host, scope_prefix="/")
        scope["crawl"]["robots_redirect_hosts"] = (
            [host.removeprefix("www.")]
            if host.startswith("www.")
            else ["www." + host]
            if host.count(".") == 1
            else []
        )
        result["scopes"][host] = scope
    return result


def _run(config, root, *, resume=False):
    root = Path(root)
    fields.validate(config, Platform(root))
    directory = root / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    status_path = directory / "status.json"
    if status_path.exists() and not resume:
        raise ValueError("campaign_already_started")
    status = (
        json.loads(status_path.read_text())
        if status_path.exists()
        else {
            "campaign_id": config["campaign_id"],
            "started_at": time.time(),
            "directory_stores": config["directory_stores"],
            "planned_targets": len(config["targets"]),
            "coverage_gaps": len(config.get("coverage_gaps", [])),
            "passes": {},
        }
    )
    stopped = threading.Event()
    shutdown = threading.Event()
    active = [None]
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())

    def parent_check():
        if stopped.is_set() or (directory / "STOP").exists():
            raise fields.statewide.Stopped("operator_stop")

    def monitor():
        while not shutdown.wait(1):
            if (
                stopped.is_set()
                or (directory / "STOP").exists()
                or time.time() - status["started_at"] > config["duration_seconds"]
            ):
                stopped.set()
                if active[0]:
                    target = root / "crawl-campaigns" / active[0]
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "STOP").touch()
                break

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        primary = {
            **retained_canonical_targets(config, root),
            "campaign_id": config["campaign_id"] + "-primary",
        }
        for name in ["primary", "canonical"]:
            if stopped.is_set() or (directory / "STOP").exists():
                status["state"] = "stopped"
                break
            child = (
                primary
                if name == "primary"
                else canonical_followup(
                    {**primary, "campaign_id": config["campaign_id"]},
                    json.loads(
                        (
                            root / "crawl-campaigns" / primary["campaign_id"] / "status.json"
                        ).read_text()
                    ),
                    Platform(root),
                )
            )
            if not child["targets"]:
                status["passes"][name] = {"state": "not_needed", "targets": 0}
                continue
            remaining = int(config["duration_seconds"] - (time.time() - status["started_at"]))
            if remaining < 60:
                status["state"] = "stopped"
                break
            child["duration_seconds"] = min(child["duration_seconds"], remaining)
            # A persisted child config makes explicit resume independent of clocks.
            saved = directory / (name + "-config.json")
            if saved.exists():
                child = json.loads(saved.read_text())
            else:
                atomic_json(saved, child)
            fields.validate(child, Platform(root))
            if stopped.is_set() or (directory / "STOP").exists():
                status["state"] = "stopped"
                break
            if name == "canonical":
                history = CrawlHistory(root)
                for target in child["targets"]:
                    for hold in history.blocking(target):
                        if not hold["hold_key"].startswith("host:"):
                            continue
                        with history.connect() as db:
                            row = db.execute(
                                "SELECT payload FROM events WHERE id=?", (hold["event_id"],)
                            ).fetchone()
                        if row and json.loads(row[0]).get("http_status") in {301, 302, 307, 308}:
                            history.resolve(
                                hold["hold_key"],
                                "Iowa bounded canonical redirect review from primary status. No access denial cleared",
                            )
            active[0] = child["campaign_id"]
            status.update(state="running", phase=name, active_run=active[0], updated_at=time.time())
            atomic_json(status_path, status)
            child_path = root / "crawl-campaigns" / active[0] / "status.json"
            previous = json.loads(child_path.read_text()) if child_path.exists() else None
            result = (
                previous
                if previous and previous.get("state") in {"finished", "finished_with_holds"}
                else fields.statewide.run(
                    child,
                    root,
                    resume=resume and child_path.exists(),
                    judge_factory=fields.FieldJudge,
                    install_signals=False,
                    external_check=lambda: parent_check(),
                )
            )
            status["passes"][name] = {
                "campaign_id": child["campaign_id"],
                "state": result["state"],
                "counts": result.get("counts", {}),
            }
            if result["state"] not in {"finished", "finished_with_holds"}:
                status["state"] = result["state"]
                break
        else:
            status["state"] = (
                "finished_with_holds"
                if any(p.get("state") == "finished_with_holds" for p in status["passes"].values())
                else "finished"
            )
    except BaseException as error:
        status.update(state="paused_error", error_type=type(error).__name__)
        raise
    finally:
        shutdown.set()
        watcher.join(timeout=2)
        status.update(updated_at=time.time(), active_run=None)
        atomic_json(status_path, status)
    hook = config.get("post_pass_review") or {}
    if hook.get("enabled") is True and status["state"] in {"finished", "finished_with_holds"}:
        from bord_food_api.state_batch import prepare_after_pass

        output = root / "operator-imports" / (config["campaign_id"] + "-review")
        try:
            plan = prepare_after_pass(
                Platform(root),
                status,
                state=config["state"],
                pass_id=config["campaign_id"],
                directory=output,
            )
            status["post_pass_review"] = {
                "state": "prepared",
                "directory": str(output),
                "inference_requests": len(plan["requests"]),
                "reservation_nanousd": plan["reservation_nanousd"],
                "submitted": False,
            }
        except (ValueError, OSError) as error:
            status["post_pass_review"] = {
                "state": "preparation_failed",
                "error_type": type(error).__name__,
                "submitted": False,
            }
        atomic_json(status_path, status)
    return status


def run(config, root, *, resume=False):
    directory = Path(root) / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    with fields.statewide.controller_lock(directory):
        return _run(config, root, resume=resume)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("config", type=Path)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--run", action="store_true")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    config = json.loads(a.config.read_text())
    fields.validate(config, Platform(a.data_dir))
    if not a.run:
        print(
            json.dumps({"network": False, "planned_targets": len(config["targets"]), "passes": 2})
        )
        return
    result = run(config, a.data_dir, resume=a.resume)
    print(json.dumps(result))
    if result["state"] not in {"finished", "finished_with_holds"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
