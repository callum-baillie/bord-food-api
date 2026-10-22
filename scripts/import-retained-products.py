"""Explicit network-free import of retained USDA/OFF/chart artifacts.

Run in an isolated worker. Default --plan is read-only; --apply publishes immutable
packs. No source discovery, download, retail API, crawler or paid request exists here.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from bord_food_api.operator_products import cold_storage_chart, import_usda_products
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.sources import open_source, parse_off_jsonl


def run(root, directory, *, apply=False, usda=False, off=None, chart=None, sha256=None):
    platform = Platform(root)
    before = platform.current()
    plan = {
        "mode": "apply" if apply else "plan",
        "base_generation": before.get("generation") if before else None,
        "usda_projection": usda,
        "off_scope": ["en:united-states"] if off else None,
        "source_network": False,
        "paid_calls": 0,
        "chart": bool(chart),
    }
    if not apply:
        return plan
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "status.json").exists():
        raise ValueError("use_new_import_run_directory")
    state = {
        **plan,
        "state": "running",
        "started_at": time.time(),
        "phase": "waiting_for_worker_slot",
    }
    atomic_json(directory / "status.json", state)
    try:
        with heavy_lock(root):
            if usda:
                state["phase"] = "usda_projection"
                atomic_json(directory / "status.json", state)

                def progress(count):
                    state.update(projected_usda_records=count, updated_at=time.time())
                    atomic_json(directory / "status.json", state)

                result = import_usda_products(platform, progress=progress)
                state["usda_products_changed"] = result["changed"]
            if chart:
                state["phase"] = "storage_guidance"
                atomic_json(directory / "status.json", state)
                raw = Path(chart).read_bytes()
                document = json.loads(raw)
                result = platform.sync(
                    "foodsafety_cold_storage",
                    "chart",
                    hashlib.sha256(raw).hexdigest(),
                    cold_storage_chart(document),
                    complete=True,
                    parser_version="official-chart-snapshot-v1",
                    cursor={"source_last_reviewed": document.get("source_last_reviewed")},
                )
                state["guidance_changed"] = result["changed"]
            if off:
                path = Path(off)
                meta = json.loads(Path(str(path) + ".metadata.json").read_text())
                state["phase"] = "off_verify_retained_bytes"
                atomic_json(directory / "status.json", state)
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if (
                    not sha256
                    or digest != sha256
                    or meta.get("sha256") != digest
                    or path.stat().st_size != meta["bytes"]
                ):
                    raise ValueError("retained_off_artifact_does_not_match_reviewed_receipt")
                state["phase"] = "off_streaming_us_snapshot"
                atomic_json(directory / "status.json", state)

                def records():
                    with open_source(path, 200 * 1024**3) as stream:
                        for index, row in enumerate(
                            parse_off_jsonl(stream, countries=["en:united-states"]), start=1
                        ):
                            if index % 1000 == 0:
                                state.update(selected_products=index, updated_at=time.time())
                                atomic_json(directory / "status.json", state)
                            yield row

                result = platform.sync(
                    "open_food_facts",
                    "products",
                    digest,
                    records(),
                    complete=True,
                    parser_version="1",
                    cursor={
                        "sha256": digest,
                        "snapshot_only": True,
                        "watermark": None,
                        "delta_alignment": "unverified",
                        "countries": ["en:united-states"],
                        "source_version_id": meta.get("source_version_id"),
                    },
                )
                state["off_products_changed"] = result["changed"]
                state["off_delta_alignment"] = "unverified_snapshot_only"
            state.update(
                state="succeeded",
                completed_at=time.time(),
                generation=platform.current()["generation"],
            )
            atomic_json(directory / "status.json", state)
            return state
    except BaseException as error:
        state.update(state="failed", completed_at=time.time(), error_type=type(error).__name__)
        atomic_json(directory / "status.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--usda-products", action="store_true")
    parser.add_argument("--off", type=Path)
    parser.add_argument("--off-sha256")
    parser.add_argument("--storage-chart", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.data_dir,
                args.run_dir,
                apply=args.apply,
                usda=args.usda_products,
                off=args.off,
                chart=args.storage_chart,
                sha256=args.off_sha256,
            )
        )
    )


if __name__ == "__main__":
    main()
