"""Reparse retained, Jev-approved Iowa branch pages without source/model requests."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

from bord_food_api.crawl_evidence import collect_evidence
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.store_enrichment import public_url, publish_crawl_evidence
from bord_food_api.store_quality import location_key


def run(root, directory, *, publish=False):
    root, directory = Path(root), Path(directory)
    with heavy_lock(root):
        platform = Platform(root)
        selected = {}
        for path in sorted((root / "crawl-campaigns").glob("iowa-fields-*/pages/*.json")):
            saved = json.loads(path.read_text())
            target = saved["target"]
            evidence = saved["evidence"]
            decision = evidence.get("machine_review") or {}
            if decision.get("choice") != "consistent" or decision.get("confidence", 0) < 0.8:
                continue
            body_path = path.with_suffix(".html.gz")
            if not body_path.is_file():
                continue
            store = platform.get("store", target["store_id"])
            if (
                not store
                or store.get("address", {}).get("region") != "IA"
                or (
                    store.get("address") != target.get("source_address")
                    and (
                        location_key(store) is None
                        or location_key(store)
                        != location_key({"address": target.get("source_address")})
                    )
                )
                or store.get("name") != target.get("name")
            ):
                continue
            if not store.get("website") or public_url(store["website"]) != public_url(
                target["url"]
            ):
                continue
            key = (target["store_id"], target["url"])
            stamp = evidence["retrieved_at"]
            if not 0 <= time.time() - stamp <= 86400:
                continue
            if key not in selected or selected[key][0] < stamp:
                selected[key] = (stamp, body_path, target, evidence)
        directory.mkdir(parents=True, exist_ok=True)
        results = []
        for stamp, path, target, previous in selected.values():
            with gzip.open(path, "rb") as stream:
                body = stream.read(2097153)
            if len(body) > 2097152 or hashlib.sha256(body).hexdigest() != previous["html_sha256"]:
                raise ValueError("retained_page_changed")
            evidence = collect_evidence(
                body.decode("utf-8", errors="replace"), target, retrieved_at=stamp
            )
            item = {
                "store_id": target["store_id"],
                "source_url": target["url"],
                "old_parser": previous["parser_version"],
                "parser_version": evidence["parser_version"],
                "html_sha256": evidence["html_sha256"],
                "branch_match": evidence["branch_match"],
                "valid_fields": sorted(
                    {
                        r["field"]
                        for r in evidence["field_assertions"]
                        if r["validation"] == "valid" and r["branch_match"] == "exact_address"
                    }
                ),
            }
            if evidence["branch_match"] == "exact_address":
                evidence["reused_machine_review"] = previous["machine_review"]
                atomic_json(
                    directory / (hashlib.sha256(target["url"].encode()).hexdigest() + ".json"),
                    evidence,
                )
                if publish:
                    item["publication"] = publish_crawl_evidence(
                        platform, evidence, now=time.time()
                    )["changed"]
            results.append(item)
        receipt = {
            "state": "published" if publish else "prepared",
            "source_requests": 0,
            "paid_calls": 0,
            "results": results,
            "generation": platform.current()["generation"],
        }
        atomic_json(directory / "receipt.json", receipt)
        return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path("/data"))
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--publish", action="store_true")
    args = p.parse_args()
    print(json.dumps(run(args.data_dir, args.run_dir, publish=args.publish)))


if __name__ == "__main__":
    main()
