"""One explicit Iowa pilot re-review after correcting empty/truncated model context.

No source transport or hold deletion. Three retained pages, at most three Jev
requests, existing cumulative $15 ledger, original source clocks, fresh reviews.
This is an operator receipt-producing action, not an automatic retry policy.
"""

import gzip
import hashlib
import importlib.util
import json
import sqlite3
import time
from pathlib import Path

from bord_food_api.crawl_evidence import _branch_match, collect_evidence
from bord_food_api.platform import Platform, atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.store_enrichment import publish_crawl_evidence
from bord_food_api.store_pages import branch_html, branch_review_text, structured_nodes

spec = importlib.util.spec_from_file_location("fields", "scripts/run-iowa-fields.py")
fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fields)
root = Path("/data")
campaign = "iowa-contact-context-review-20261020"
out = root / "crawl-campaigns" / campaign
assert not (out / "receipt.json").exists(), "one_explicit_review_only"
config = json.loads(Path("/pilot-config/crawl.json").read_text())["decisions"]
config.update(campaign_id=campaign, max_calls=3, budget_nanousd=30000000)
judge = fields.FieldJudge(root, config)
deadline = time.time() + 1200


def check():
    if (out / "STOP").exists() or time.time() > deadline:
        raise ValueError("operator_stop_or_deadline")


judge.check = check
results = []
selected = {
    "sto_00771498a3124edca3ced134b7c84326",
    "sto_2a998e50d4db4ae99134bb9ab03abbfc",
    "sto_df167da017874693bac1abf35f125608",
}
for path in sorted(
    (root / "crawl-campaigns/iowa-contact-pilot1-20261020-primary/pages").glob("*.json")
):
    saved = json.loads(path.read_text())
    target, old = saved["target"], saved["evidence"]
    if target["store_id"] not in selected:
        continue
    check()
    p = Platform(root)
    store = p.get("store", target["store_id"])
    assert store["address"] == target["source_address"] and store["name"] == target["name"]
    assert store["address"]["region"] == "IA"
    assert old["branch_match"] == "exact_address" and old.get("machine_review")
    assert 0 <= time.time() - old["retrieved_at"] <= 86400
    with gzip.open(path.with_suffix(".html.gz"), "rb") as stream:
        body = stream.read(2097153)
    assert len(body) <= 2097152 and hashlib.sha256(body).hexdigest() == old["html_sha256"]
    page, _nodes = structured_nodes(body.decode("utf-8", errors="replace"))
    _store, _links, branch_path = branch_html(page, target, _branch_match)
    excerpt = branch_review_text(page, branch_path)
    with sqlite3.connect(root / "control/jev-crawl-budget.sqlite") as db:
        original_request = json.loads(
            db.execute(
                "SELECT result FROM decisions WHERE campaign=? AND target=? AND stage='field_page_review' ORDER BY id DESC LIMIT 1",
                ("iowa-contact-pilot1-20261020-primary", store["id"]),
            ).fetchone()[0]
        )["request_evidence"]
    assert excerpt and excerpt != original_request["page_text"], "source_context_must_change"
    item = {
        "store_id": store["id"],
        "url": target["url"],
        "html_sha256": old["html_sha256"],
        "original_review": old["machine_review"],
    }
    try:
        judge.after(target, body)
    except fields.reviewed.ReviewRequired:
        item["state"] = "held_requires_review"
    else:
        fresh = json.loads((judge.directory / path.name).read_text())["evidence"]
        evidence = collect_evidence(
            body.decode("utf-8", errors="replace"), target, retrieved_at=old["retrieved_at"]
        )
        evidence["machine_review"] = fresh["machine_review"]
        evidence["reviewed_at"] = time.time()
        evidence["review_reason"] = "corrected_source_excerpt_after_branch_fields_v8"
        for _attempt in range(60):
            check()
            try:
                lock = heavy_lock(root)
                lock.__enter__()
                break
            except BlockingIOError:
                time.sleep(5)
        else:
            raise ValueError("worker_lock_unavailable")
        try:
            check()
            assert p.get("store", store["id"])["address"] == target["source_address"]
            result = publish_crawl_evidence(p, evidence, now=time.time())
            item.update(
                state="published", changed=result["changed"], generation=p.current()["generation"]
            )
        finally:
            lock.__exit__(None, None, None)
        atomic_json(out / (path.stem + "-source-clock-evidence.json"), evidence)
    reviewed_path = judge.directory / path.name
    if reviewed_path.exists():
        item["new_review"] = json.loads(reviewed_path.read_text())["evidence"].get("machine_review")
    results.append(item)
    atomic_json(out / "progress.json", {"results": results, "source_requests": 0})
assert len(results) == 3
receipt = {
    "state": "finished_with_holds"
    if any(r["state"] != "published" for r in results)
    else "finished",
    "results": results,
    "source_requests": 0,
    "max_jev_requests": 3,
    "old_holds_retained": True,
}
atomic_json(out / "receipt.json", receipt)
print(json.dumps(receipt))
