"""Backfill/watch durable crawl history offline. This tool never fetches sources or calls models."""

import argparse
import hashlib
import json
import signal
import sqlite3
import threading
import time
from pathlib import Path

from bord_food_api.crawl_history import CrawlHistory
from bord_food_api.nationwide import branch_url
from bord_food_api.platform import atomic_json


def read_json(path):
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError("history_input_byte_limit")
    return json.loads(path.read_text())


def store_index(root):
    pointer = Path(root) / "current.json"
    if not pointer.exists():
        return {}
    manifest = read_json(pointer)
    relative = manifest.get("packs", {}).get("stores")
    if not relative:
        return {}
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("unsafe_store_pack")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        return {
            row["id"]: row
            for row in (
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM entities WHERE kind='store'")
            )
        }


def configs_in(metadata):
    configs = {}
    if metadata:
        for path in sorted(Path(metadata).glob("**/*.json")):
            try:
                value = read_json(path)
                if (
                    isinstance(value, dict)
                    and value.get("campaign_id")
                    and isinstance(value.get("targets"), list)
                ):
                    digest = (
                        value.get("original_config_sha256")
                        or hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
                    )
                    configs.setdefault(value["campaign_id"], []).append((digest, value))
            except (OSError, ValueError, TypeError):
                continue
    return configs


def missing_url_rows(root, config, stores):
    directory = config.get("source_directory")
    if not directory:
        return []
    directory = Path(directory).resolve()
    if not directory.is_relative_to(Path(root).resolve()):
        return []
    path = directory / "roster.jsonl"
    if not path.exists() or path.stat().st_size > 16 * 1024**2:
        return []
    by_source = {(v.get("spider"), v.get("source_id")): v for v in stores.values()}
    rows = []
    for line in path.read_text().splitlines():
        value = json.loads(line)
        payload = value["payload"]
        url, reason = branch_url(payload.get("website"))
        if url:
            continue
        store = by_source.get((payload.get("spider"), payload.get("source_id")), {})
        rows.append(
            {
                "store_id": store.get("id"),
                "source_key": "all_the_places:" + value["partition"] + ":" + value["source_key"],
                "name": payload.get("name"),
                "state": "missing_branch_url",
                "reason": reason,
                "url": payload.get("website"),
                "network_attempted": False,
            }
        )
    return rows


def observe_once(root, history, *, metadata=None):
    root = Path(root)
    stores = store_index(root)
    configs = configs_in(history.directory / "run-metadata")
    for run, choices in configs_in(metadata).items():
        configs.setdefault(run, []).extend(choices)
    failures = []
    added = 0
    scanned = 0
    paths = sorted((root / "crawl-campaigns").glob("*/status.json"))
    for path in paths:
        try:
            snapshot = read_json(path)
            run = snapshot.get("campaign_id")
            if not run:
                continue  # A discovery status is not a crawl execution.
            candidates = configs.get(run, [])
            if snapshot.get("config_sha256"):
                candidates = [c for c in candidates if c[0] == snapshot["config_sha256"]]
            config = candidates[-1][1] if candidates else {"campaign_id": run}
            added += history.ingest(snapshot, config, stores)
            gaps = missing_url_rows(root, config, stores)
            if gaps:
                added += history.ingest(
                    {
                        **snapshot,
                        "targets": {r.get("store_id") or r["source_key"]: r for r in gaps},
                    },
                    config,
                    stores,
                )
            scanned += 1
        except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error) as error:
            # No exception strings, input bodies, keys or headers in observer logs.
            failures.append({"run_directory": path.parent.name, "error_type": type(error).__name__})
    summary = history.export()
    result = {
        "observed_at": time.time(),
        "runs_scanned": scanned,
        "events_added": added,
        "states": summary["states"],
        "active_holds": summary["active_holds"],
        "errors": failures,
        "network": False,
        "paid_calls": 0,
    }
    atomic_json(history.directory / "observer-status.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--history-dir", type=Path)
    parser.add_argument("--metadata-dir", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--resolve-hold")
    parser.add_argument("--evidence")
    args = parser.parse_args()
    if not 5 <= args.interval <= 300:
        parser.error("interval must be 5..300 seconds")
    history = CrawlHistory(args.data_dir, directory=args.history_dir)
    if args.resolve_hold:
        history.resolve(args.resolve_hold, args.evidence)
        print(json.dumps({"resolved": args.resolve_hold, "network": False}))
        return
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while True:
        result = observe_once(args.data_dir, history, metadata=args.metadata_dir)
        print(json.dumps(result), flush=True)
        if not args.watch or stop.wait(args.interval):
            break


if __name__ == "__main__":
    main()
