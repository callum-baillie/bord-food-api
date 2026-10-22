"""Offline public-directory discovery, reusable for any explicitly selected state.

Network acquisition remains in the reviewed crawler; this CLI never fetches pages,
changes serving facts or activates campaigns.
"""

import argparse
import json
from pathlib import Path

from bord_food_api.platform import Platform, atomic_json
from bord_food_api.site_discovery import directory_candidates


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--state", required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--source-id", choices=["ncg", "iga", "civic_directory"], required=True)
    p.add_argument("--retrieved-at", type=float, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    platform = Platform(a.data_dir)
    candidates = directory_candidates(
        a.html.read_text(),
        a.source_url,
        list(platform.iter_records("store")),
        state=a.state,
        source_id=a.source_id,
        retrieved_at=a.retrieved_at,
    )
    atomic_json(
        a.output,
        {
            "state": a.state,
            "generation": platform.current()["generation"],
            "candidates": candidates,
            "network_requests": 0,
            "publication": False,
        },
    )
    print(json.dumps({"candidates": len(candidates), "activated": False}))


if __name__ == "__main__":
    main()
