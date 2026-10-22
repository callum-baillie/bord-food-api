"""Prepare all 50 states plus separate DC using an existing pinned bulk archive. Never crawl."""

import argparse
import json
from pathlib import Path

from bord_food_api.nationwide import stage, verify_bundle
from bord_food_api.platform import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--source-run")
    parser.add_argument("--sha256")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        report = verify_bundle(args.output)
    else:
        if not all((args.archive, args.source_run, args.sha256)):
            parser.error("--archive, --source-run and --sha256 are required")
        report = stage(
            args.archive,
            args.output,
            source_run=args.source_run,
            expected_sha256=args.sha256,
            progress=lambda v: atomic_json(args.output / "scan-progress.json", v),
        )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "state_count",
                    "stores",
                    "targets",
                    "retailer_requests",
                    "paid_calls",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
