"""Inspect, then explicitly run/resume a post-supermarket food-assistance worker.

Uses the ordinary source scheduler for automatic updates. No product inventories,
paid models, source entitlement signup or Bòrd household writes. Waits for terminal
supermarket dependencies before the first source or operator request.
"""

import argparse
import fcntl
import importlib.util
import json
import os
import signal
import threading
import time
from pathlib import Path

from bord_food_api.assistance import validate_states
from bord_food_api.assistance_campaign import run_pass, supermarket_gate
from bord_food_api.domain import content_hash
from bord_food_api.platform import atomic_json
from bord_food_api.settings import Settings, load_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate_states(config["states"])
    policy_path = Path(config["policy_path"])
    if not policy_path.is_absolute():
        policy_path = args.config.resolve().parent / policy_path
    os.environ["BORD_FOOD_CONFIG"] = str(policy_path)
    settings = Settings(
        data_dir=args.data_dir,
        import_dir=args.data_dir / "assistance-no-local-imports",
        auto_download=False,
    )

    def reviewer_factory(identifier):
        from bord_food_api.assistance_review import needs_review, review_page

        spec = importlib.util.spec_from_file_location(
            "assistance_jev", Path(__file__).with_name("run-reviewed-crawl.py")
        )
        reviewed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reviewed)
        judge = reviewed.Judge(
            args.data_dir,
            {
                "campaign_id": identifier,
                "global_budget_nanousd": 15000000000,
                "budget_nanousd": 10000000,
                "max_calls": 1,
                "key_file": config.get("jev_key_file", "/run/secrets/jev-api-key"),
            },
        )

        def review(html, target, extracted):
            if not needs_review(target, extracted):
                return None
            return review_page(judge, reviewed.review_text(html), target, extracted)

        return review

    fingerprint = content_hash({"campaign": config, "policy": load_policy(settings)})
    if not args.run:
        print(
            json.dumps(
                {
                    "state": "staged",
                    "states": config["states"],
                    "after_campaigns": config["after_campaigns"],
                    "source_requests": 0,
                    "paid_calls": 0,
                    "config_sha256": fingerprint,
                }
            )
        )
        return
    directory = args.data_dir / "crawl-campaigns" / config["campaign_id"]
    directory.mkdir(parents=True, exist_ok=True)
    status_path = directory / "status.json"
    if status_path.exists() and not args.resume:
        raise ValueError("explicit_assistance_resume_required")
    if (
        status_path.exists()
        and json.loads(status_path.read_text()).get("config_sha256") != fingerprint
    ):
        raise ValueError("assistance_resume_policy_changed")
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    phase_cancel = threading.Event()

    def watch_stop():
        while not stopped.is_set():
            if (directory / "STOP").exists():
                phase_cancel.set()
            stopped.wait(1)
        phase_cancel.set()

    threading.Thread(target=watch_stop, daemon=True).start()
    with (directory / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        next_pass_at = 0
        if status_path.exists():
            next_pass_at = json.loads(status_path.read_text()).get("next_pass_at", 0)
        interval = config.get("pass_interval_seconds", 21600)
        if type(interval) is not int or not 3600 <= interval <= 604800:
            raise ValueError("assistance_pass_interval_invalid")
        while not stopped.is_set():
            if (directory / "STOP").exists():
                atomic_json(
                    status_path,
                    {
                        "state": "paused_operator",
                        "config_sha256": fingerprint,
                        "updated_at": time.time(),
                    },
                )
                if args.once:
                    return
                stopped.wait(30)
                continue
            gate = supermarket_gate(args.data_dir, config["after_campaigns"])
            if gate["ready"] and time.time() < next_pass_at:
                if args.once:
                    return
                stopped.wait(30)
                continue
            atomic_json(
                status_path,
                {
                    "state": "waiting_for_supermarkets" if not gate["ready"] else "running",
                    "dependency": gate,
                    "config_sha256": fingerprint,
                    "updated_at": time.time(),
                },
            )
            if gate["ready"]:
                try:
                    phase_cancel.clear()
                    result = run_pass(
                        settings,
                        config,
                        cancellation=phase_cancel,
                        reviewer_factory=reviewer_factory
                        if config.get("jev_enabled") is True
                        else None,
                    )
                except BlockingIOError:
                    result = {"state": "waiting_for_worker_slot"}
                except ValueError as error:
                    if str(error) != "assistance_operator_stopped":
                        raise
                    result = {"state": "paused_operator"}
                next_pass_at = time.time() + (
                    30 if result["state"] == "waiting_for_worker_slot" else interval
                )
                atomic_json(
                    status_path,
                    {
                        **result,
                        "config_sha256": fingerprint,
                        "next_pass_at": next_pass_at,
                        "updated_at": time.time(),
                    },
                )
            if args.once:
                return
            # Responsive shutdown; do not hold a worker slot while waiting.
            for _ in range(60):
                if stopped.is_set() or (directory / "STOP").exists():
                    break
                time.sleep(1)
        atomic_json(
            status_path,
            {"state": "stopped", "config_sha256": fingerprint, "updated_at": time.time()},
        )


if __name__ == "__main__":
    main()
