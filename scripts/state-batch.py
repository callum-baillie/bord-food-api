"""Explicit OpenAI post-pass lifecycle. Preparing/importing never makes model calls."""

import argparse
import json
import os
import time
from pathlib import Path

from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.state_batch import (
    Client,
    documents_from_rows,
    import_results,
    prepare,
    write_plan,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "submit", "collect", "import"])
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--snapshot", type=Path)
    p.add_argument("--documents", type=Path)
    p.add_argument("--state")
    p.add_argument("--pass-id")
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--env-file", type=Path)
    p.add_argument("--completed-pass", type=Path)
    a = p.parse_args()
    if a.action == "prepare":
        if not a.completed_pass:
            raise ValueError("completed_pass_receipt_required")
        receipt = json.loads(a.completed_pass.read_text())
        if receipt.get("state") not in {"published", "finished", "finished_with_holds"}:
            raise ValueError("state_pass_not_complete")
        if a.snapshot:
            s = json.loads(a.snapshot.read_text())
        else:
            platform = Platform(a.data_dir)
            s = {
                "generation": platform.current()["generation"],
                "stores": list(platform.iter_records("store")),
            }
        docs = (
            [json.loads(l) for l in a.documents.read_text().splitlines() if l.strip()]
            if a.documents
            else documents_from_rows(s["stores"])
        )
        plan = prepare(
            s["stores"], docs, state=a.state, pass_id=a.pass_id, generation=s["generation"]
        )
        write_plan(a.directory, plan)
        print(
            json.dumps(
                {
                    "state": "prepared",
                    "requests": len(plan["requests"]),
                    "reservation_nanousd": plan["reservation_nanousd"],
                    "deferred": len(plan["deferred"]),
                    "stores_without_eligible_evidence": plan["stores_without_eligible_evidence"],
                }
            )
        )
        return
    if a.action == "import":
        with heavy_lock(a.data_dir):
            result = import_results(
                Platform(a.data_dir),
                json.loads((a.directory / "plan.json").read_text()),
                (a.directory / "output.jsonl").read_text().splitlines(),
                now=time.time(),
            )
            atomic_json(a.directory / "import.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "accepted"}))
        return
    key = os.environ.get("OPENAI_API_KEY")
    if a.env_file:
        # Existing, user-designated key remains in memory and at its original path.
        for line in a.env_file.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    client = Client(key)
    result = client.submit(a.directory) if a.action == "submit" else client.collect(a.directory)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
