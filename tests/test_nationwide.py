import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from bord_food_api.nationwide import (
    JURISDICTIONS,
    STATES,
    branch_url,
    stage,
    state_region,
    verify_bundle,
)
from bord_food_api.platform import Platform
from bord_food_api.transport import file_hash

spec = importlib.util.spec_from_file_location(
    "us_runner", Path(__file__).parents[1] / "scripts/run-us-crawl.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def feature(key, state="IA", **values):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-93.6, 41.6]},
        "properties": {
            "ref": key,
            "name": "Synthetic " + key,
            "brand": "Synthetic Grocers",
            "addr:country": "US",
            "addr:state": state,
            "shop": "supermarket",
            "addr:street_address": "10 Imaginary St",
            "addr:city": "Imaginary",
            "addr:postcode": "50000",
            "website": "https://retailer.test/stores/" + key,
            **values,
        },
    }


def bundle(tmp_path):
    archive = tmp_path / "archive.zip"
    with ZipFile(archive, "w") as package:
        package.writestr(
            "grocer.geojson",
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        feature("ia"),
                        feature("ny", "New York"),
                        feature("dc", "DC"),
                        feature("conflict", **{"addr:full": "20 Example St, Other, NY 10001"}),
                        feature("fuel", shop="fuel"),
                        feature("foreign", **{"addr:country": "CA"}),
                        feature("unknown", ""),
                        feature("brandless", brand=None),
                        feature("root", website="https://retailer.test/"),
                    ],
                }
            ),
        )
        package.writestr(
            "broken.geojson",
            '{"type":"FeatureCollection","features":[' + json.dumps(feature("discard")) + ",",
        )
    directory = tmp_path / "bundle"
    report = stage(
        archive, directory, source_run="synthetic-run", expected_sha256=file_hash(archive)
    )
    return directory, report


def test_national_staging_is_inert_and_scope_failures_do_not_leak(tmp_path):
    directory, report = bundle(tmp_path)
    assert len(STATES) == 50 and len(JURISDICTIONS) == 51
    assert report["stores"] == 4 and report["targets"] == 3
    assert report["retailer_requests"] == report["paid_calls"] == 0
    assert report["filter_counts"]["conflicting_postal_state"] == 1
    assert report["failed_scopes"] == [{"spider": "broken", "error": "IncompleteJSONError"}]
    assert report["census_complete"] is False
    for code in JURISDICTIONS:
        plan = json.loads((directory / code / "plan.json").read_text())
        assert plan["enabled"] is False and plan["decisions"]["calls"] == 0
        assert plan["capture_policy"]["product_inventory"] is False
        assert plan["decisions"]["budget_scope"] == "shared_existing_ledger"
    assert not (directory / "control").exists()
    assert verify_bundle(directory)["stores"] == 4
    (directory / "NY/targets.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="bundle_hash"):
        verify_bundle(directory)


def test_region_never_guesses_from_coordinates_or_conflicts():
    assert state_region({"addr:full": "10 Street, Test, North Carolina 27000"}) == (
        "NC",
        "postal_suffix",
    )
    assert state_region({"addr:state": "US-NY"})[0] is None
    assert state_region({"addr:state": "IA", "state": "NY"})[0] is None
    assert state_region({"addr:state": "PR"})[0] is None
    assert state_region({})[0] is None


@pytest.mark.parametrize(
    "url",
    [
        "https://retailer.test/",
        "http://retailer.test/store/1",
        "https://127.0.0.1/store/1",
        "https://retailer.test/login/1",
        "https://retailer.test/map.pdf",
        "https://retailer.test/store/1#fragment",
    ],
)
def test_unsupported_targets_stay_gaps(url):
    assert branch_url(url)[0] is None


def test_exact_query_targets_preserved_without_network():
    url = "https://retailer.test/detail.aspx?s=7"
    assert branch_url(url)[0] == url


def test_pin_and_unsafe_archive_fail_before_output(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("../bad.geojson", "{}")
    with pytest.raises(ValueError, match="pin"):
        stage(archive, tmp_path / "output", source_run="x", expected_sha256="wrong")
    with pytest.raises(ValueError):
        stage(archive, tmp_path / "output", source_run="x", expected_sha256=file_hash(archive))
    assert not (tmp_path / "output").exists()


def test_preparation_requires_catalog_identity_and_keeps_all_gates_off(tmp_path):
    directory, _ = bundle(tmp_path)
    platform = Platform(tmp_path / "catalog")
    empty = runner.prepare(directory, "NY", platform)
    assert empty["targets"] == [] and len(empty["held"]) == 1
    rows = [json.loads(line) for line in (directory / "NY/roster.jsonl").read_text().splitlines()]
    platform.sync("all_the_places", "grocer", "fixture", rows)
    generation = platform.current()["generation"]
    prepared = runner.prepare(directory, "NY", platform)
    assert len(prepared["targets"]) == 1 and prepared["state"] == "NY"
    assert prepared["decisions"]["max_calls"] == 0 and prepared["activation_enabled"] is False
    assert prepared["scopes"]["retailer.test"]["crawl"]["global_enabled"] is False
    assert platform.current()["generation"] == generation
    with platform.control.connect() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    with pytest.raises(ValueError):
        runner.campaign.validate(prepared, platform)


def test_other_state_batch_runs_only_with_explicit_gates_using_mocked_discovery(tmp_path):
    directory, _ = bundle(tmp_path)
    platform = Platform(tmp_path / "catalog")
    rows = [json.loads(line) for line in (directory / "NY/roster.jsonl").read_text().splitlines()]
    platform.sync("all_the_places", "grocer", "fixture", rows)
    config = runner.prepare(directory, "NY", platform)
    config["decisions"] = {"max_calls": 2, "budget_nanousd": 20000000, "key_file": "unused"}
    for scope in config["scopes"].values():
        scope.update(state="approved", review_evidence="Synthetic owner review")
        scope["crawl"].update(
            global_enabled=True, adapter_enabled=True, source_authorized=True, robots_reviewed=True
        )
    assert len(runner.campaign.validate(config, platform)) == 1

    class Judge:
        def __init__(self, *args):
            pass

        def before(self, target):
            assert target["source_address"]["region"] == "NY"

    def discover(platform, job, crawl, **kwargs):
        # Exercise the actual profile sink without constructing a real transport.
        crawl["_evidence_sink"](
            "<main>Synthetic branch details</main>", crawl["approved_targets"][0]
        )
        return {"map_records": 0}

    result = runner.campaign.run(config, platform.root, judge_factory=Judge, discover=discover)
    assert result["state"] == "finished"
    evidence_files = list(
        (platform.root / "crawl-campaigns" / config["campaign_id"] / "evidence").glob("*.json")
    )
    evidence = json.loads(evidence_files[0].read_text())
    assert evidence["acceptance_status"] == "review_required"
    assert evidence["visible_text_excerpt"] == "Synthetic branch details"
    assert not platform.control.enabled("retailer_maps")
