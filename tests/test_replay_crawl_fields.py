import gzip
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import pytest

from bord_food_api.platform import Platform

spec = importlib.util.spec_from_file_location(
    "replay_fields", Path(__file__).parents[1] / "scripts/replay-crawl-fields.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.mark.parametrize("legacy_full_address", [False, True])
def test_replay_requires_unchanged_approved_source_and_retains_actual_fetch_clock(
    tmp_path, legacy_full_address
):
    p = Platform(tmp_path)
    address = {"street": "10 Main St", "city": "Ames", "region": "IA", "postal_code": "50010"}
    if legacy_full_address:
        address = {"full": "10 Main St, Ames, IA 50010", "region": "IA"}
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {
                    "name": "Fixture",
                    "country": "US",
                    "address": address,
                    "website": "https://fixture.test/one",
                },
            }
        ],
    )
    s = p.records("store")[0]
    stamp = time.time() - 3600
    target = {
        "store_id": s["id"],
        "name": "Fixture",
        "source_address": address,
        "url": s["website"],
        "expected_branch": "Fixture",
    }
    body = b'<main>10 Main St Ames IA 50010 Monday 8 AM - 9 PM <a href="tel:5155551234">Phone</a></main>'
    pages = tmp_path / "crawl-campaigns/iowa-fields-fixture/pages"
    pages.mkdir(parents=True)
    metadata = {
        "target": target,
        "evidence": {
            "retrieved_at": stamp,
            "html_sha256": hashlib.sha256(body).hexdigest(),
            "parser_version": "fixture-old",
            "machine_review": {"choice": "consistent", "confidence": 0.99},
        },
    }
    (pages / "one.json").write_text(json.dumps(metadata))
    (pages / "one.html.gz").write_bytes(gzip.compress(body))
    result = replay.run(tmp_path, tmp_path / "replay", publish=True)
    assert (
        result["source_requests"] == result["paid_calls"] == 0
        and result["results"][0]["publication"] == 1
    )
    row = p.get("store", s["id"])
    assert (
        row["phone"] == "+15155551234"
        and row["field_provenance"]["phone"]["last_checked_at"] == stamp
    )
    generation = p.current()["generation"]
    (pages / "one.html.gz").write_bytes(gzip.compress(b"changed"))
    with pytest.raises(ValueError, match="retained_page_changed"):
        replay.run(tmp_path, tmp_path / "replay", publish=True)
    assert p.current()["generation"] == generation
