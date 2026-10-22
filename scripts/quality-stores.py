"""Offline deterministic quality pass; --publish is an explicit immutable publication."""

import argparse
import json
import time
from pathlib import Path

from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.store_quality import prepare, publish
from bord_food_api.store_sources import place_candidate


def run(root, directory, state, *, places=(), candidates=(), reviews=(), apply=False):
    with heavy_lock(root):
        platform = Platform(root)
        current = platform.current()
        retained = list(candidates)
        for source, path in places:
            for line in Path(path).read_text().splitlines():
                raw = json.loads(line)
                r = place_candidate(source, raw)
                if r["category"] == "exclude":
                    continue
                r["payload"].update(
                    source_observed_at=raw.get("_retrieved_at"), source_url=raw.get("_source_url")
                )
                retained.append(r)
        plan = prepare(list(platform.iter_records("store")), retained, state=state)
        plan.update(
            base_generation=current["generation"],
            prepared_at=time.time(),
            source_requests=0,
            paid_calls=0,
        )
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(directory / "plan.json", plan)
        if apply:
            result = publish(platform, plan, reviews, now=plan["prepared_at"])
            atomic_json(
                directory / "publication.json",
                {
                    "state": "published",
                    "changed": result["changed"],
                    "generation": result["manifest"]["generation"],
                },
            )
        return {k: v for k, v in plan.items() if k != "records"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--places", action="append", default=[])
    p.add_argument("--candidates", type=Path)
    p.add_argument("--reviews", type=Path)
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    retained = (
        [json.loads(l) for l in a.candidates.read_text().splitlines()] if a.candidates else []
    )
    print(
        json.dumps(
            run(
                a.data_dir,
                a.run_dir,
                a.state,
                places=[x.split("=", 1) for x in a.places],
                candidates=retained,
                reviews=json.loads(a.reviews.read_text()) if a.reviews else [],
                apply=a.publish,
            )
        )
    )


if __name__ == "__main__":
    main()
