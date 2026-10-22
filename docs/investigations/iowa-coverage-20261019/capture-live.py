import json
import pathlib
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime

root = pathlib.Path("/data")
m = json.loads((root / "current.json").read_text())
campaign = "iowa-statewide-20261019"
with sqlite3.connect((root / m["packs"]["stores"]).resolve().as_uri() + "?mode=ro", uri=True) as db:
    rows = [
        {**json.loads(raw), "source_key": key}
        for raw, key in db.execute("SELECT payload,source_key FROM entities WHERE kind='store'")
    ]
rows = [
    r for r in rows if str((r.get("address") or {}).get("region", "")).upper() in ("IA", "IOWA")
]
s = json.loads((root / "crawl-campaigns" / campaign / "status.json").read_text())
by_host = defaultdict(Counter)
for v in s["targets"].values():
    by_host[v["host"]][v["state"]] += 1
reviews = defaultdict(Counter)
for v in s["targets"].values():
    if v["state"] == "review_required":
        reviews[v["host"]][v.get("reason", "historical_detail_unavailable")] += 1
judgments = Counter()
with sqlite3.connect("file:/data/control/jev-crawl-budget.sqlite?mode=ro", uri=True) as db:
    for target, stage, state, raw in db.execute(
        "SELECT target,stage,state,result FROM decisions WHERE campaign=?", (campaign,)
    ):
        if s["targets"].get(target, {}).get("state") != "review_required" or state != "answered":
            continue
        v = json.loads(raw or "{}")
        for name, a in v.get("answers", {}).items():
            if name not in ("fetch", "branch"):
                continue
            confidence = a.get("confidence", 0)
            key = f"{stage}:{name}:{a.get('choice')}:{'below_0.8' if confidence < 0.8 else 'at_least_0.8'}"
            judgments[key] += 1
current = {
    "observed_utc": datetime.now(UTC).isoformat(),
    "generation": m["generation"],
    "store_pack": m["packs"]["stores"],
    "iowa_records": len(rows),
    "source_keys": sorted(r["source_key"] for r in rows),
    "by_spider": dict(Counter(r["spider"] for r in rows)),
    "by_banner": dict(Counter(r["chain_name"] for r in rows)),
    "null_websites": sum(not r.get("website") for r in rows),
    "status": s["state"],
    "counts": s["counts"],
    "missing_branch_urls": s["missing_branch_urls"],
    "by_host": {k: dict(v) for k, v in by_host.items()},
    "review_reasons": {k: dict(v) for k, v in reviews.items()},
    "review_decision_summary": dict(judgments),
    "explicit_error_targets": [
        {k: i.get(k) for k in ("host", "state", "reason", "http_status", "stage")}
        for i in s["targets"].values()
        if i.get("error_type")
    ],
    "same_source_duplicate_keys": len(rows) - len({r["source_key"] for r in rows}),
}
print(json.dumps(current, indent=2))
