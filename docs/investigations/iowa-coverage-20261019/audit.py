"""Offline replay of Iowa source selection; no networking or serving database writes."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT = Path.cwd()
while not (ROOT / "bord_food_api").is_dir() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from bord_food_api.nationwide import state_region
from bord_food_api.sources import ATP_DESCRIPTORS, _atp_feature

DATA = ROOT / "data/iowa-coverage-investigation-20261019"
OUT = ROOT / "docs/investigations/iowa-coverage-20261019"
live = json.loads((DATA / "live-summary.json").read_text())
coverage = json.loads((ROOT / "data/nationwide-staging/us-20261019-r2/coverage.json").read_text())
archive = ROOT / "data/nationwide-staging/input/atp-output.zip"
with archive.open("rb") as handle:
    digest = hashlib.file_digest(handle, "sha256").hexdigest()
assert digest == coverage["archive_sha256"]
scopes = []
accepted_keys = []
with ZipFile(archive) as package:
    for spider in sorted(live["by_spider"]):
        member = package.getinfo("output/" + spider + ".geojson")
        # Existing published Iowa-contributing scopes are small; do not load
        # arbitrary archive members into memory in this targeted replay.
        assert member.file_size < 100 * 1024**2
        raw = package.read(member)
        features = json.loads(raw)["features"]
        selected, accepted, filtered, null_urls = 0, 0, Counter(), 0
        for feature in features:
            props = feature["properties"]
            if state_region(props)[0] != "IA":
                continue
            country = str(props.get("addr:country") or props.get("country") or "").upper()
            if country not in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
                continue
            selected += 1
            row = _atp_feature(feature, spider, ATP_DESCRIPTORS.get(spider))
            if row is None:
                reason = (
                    "pharmacy"
                    if props.get("amenity") == "pharmacy" or props.get("shop") == "pharmacy"
                    else "other_format_or_banner_filter"
                )
                filtered[reason] += 1
                continue
            accepted += 1
            accepted_keys.append(row["source_key"])
            null_urls += not bool(row["payload"].get("website"))
        scopes.append(
            {
                "spider": spider,
                "member_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_iowa": selected,
                "eligible": accepted,
                "published": live["by_spider"][spider],
                "filtered": dict(filtered),
                "missing_website": null_urls,
            }
        )

assert sorted(accepted_keys) == live["source_keys"], "source/import identity mismatch"
assert len(accepted_keys) == len(set(accepted_keys)) == live["iowa_records"] == 362
results = json.loads((DATA / "upstream-results.json").read_text())["results"]
walmart = json.loads((DATA / "walmart_us.json").read_text())
assert walmart["item_scraped_count"] == 1484
assert walmart["finish_reason"] == "closespider_timeout"
result = {
    "source_run": coverage["source_run"],
    "archive_sha256": digest,
    "scope_replay": scopes,
    "eligible_source_keys_equal_published": True,
    "eligible": len(accepted_keys),
    "duplicate_source_keys": len(accepted_keys) - len(set(accepted_keys)),
    "upstream_run_results": [
        row for row in results if row["spider"] in {"walmart_us", "hy_vee_us", "fareway_us"}
    ],
    "walmart_run": {
        key: walmart[key]
        for key in (
            "finish_reason",
            "elapsed_time_seconds",
            "item_scraped_count",
            "scheduler/enqueued",
            "scheduler/dequeued",
            "downloader/response_status_count/200",
        )
    },
    "walmart_unprocessed_requests": walmart["scheduler/enqueued"] - walmart["scheduler/dequeued"],
    "global_failed_source_scopes": len(coverage["failed_scopes"]),
    "global_failed_scopes_are_not_an_iowa_missing_store_count": True,
    "limitations": [
        "Replay covers all 14 Iowa-contributing scopes, not every rejected archive scope.",
        "Source identities equal published identities; physical-location deduplication is separate.",
        "The statewide missing-location total is unknown; planning estimates are not a reference roster.",
        "No live source import, crawler restart, paid call or deployment was performed.",
    ],
}
(OUT / "source-audit.json").write_text(json.dumps(result, indent=2) + "\n")
(OUT / "live-summary.json").write_text(json.dumps(live, indent=2) + "\n")
print(
    json.dumps(
        {
            "eligible": result["eligible"],
            "identity_match": True,
            "source_scopes": len(scopes),
            "walmart_finish": walmart["finish_reason"],
            "walmart_unprocessed_requests": result["walmart_unprocessed_requests"],
            "filtered": dict(sum((Counter(row["filtered"]) for row in scopes), Counter())),
        },
        indent=2,
    )
)
