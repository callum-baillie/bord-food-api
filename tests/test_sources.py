"""Synthetic source-shaped artifacts; this module never contacts a source host."""

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

from bord_food_api.sources import (
    ATP_MANIFEST,
    OFF_DELTA_INDEX,
    ReconciliationRequired,
    SourceUnresolved,
    acquire_source,
    delta_plan,
    parse_atp_archive_scopes,
    parse_atp_geojson,
    parse_foodkeeper,
    parse_off_jsonl,
    parse_open_prices,
    parse_snap_csv,
    parse_usda,
    pin_atp_output,
    reconcile_off,
    resolve_atp,
    resolve_foodkeeper,
    resolve_snap,
    resolve_usda,
    source_filter_fingerprint,
    strict_gtin,
)


def binary(value):
    return io.BytesIO(json.dumps(value).encode())


def lines(*values):
    return io.BytesIO(b"\n".join(json.dumps(value).encode() for value in values))


def feature(key="1", name="Example Grocery", **props):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-91.5, 41.6]},
        "properties": {
            "ref": key,
            "name": name,
            "brand": "Example",
            "addr:country": "US",
            "shop": "supermarket",
            "addr:street_address": "10 Synthetic Street",
            **props,
        },
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def off(code="012345678905", modified=100, **extra):
    return {
        "code": code,
        "last_modified_t": modified,
        "countries_tags": ["en:united-states"],
        "product_name": "Synthetic oats",
        "nutriments": {"sodium_100g": 0, "sodium_unit": "g", "fiber_100g": None},
        **extra,
    }


def products(*rows):
    return list(parse_off_jsonl(lines(*rows)))


def test_usda_reuses_per_dataset_date_and_exact_normalization():
    urls = resolve_usda("""<a href="/FoodData_Central_branded_food_json_2026-04.zip">a</a>
        <a href="/FoodData_Central_foundation_food_json_2025-10.zip">b</a>""")
    assert {item.partition for item in urls} == {"branded", "foundation"}
    fixture = Path(__file__).parent / "fixtures" / "foods.json"
    rows = list(parse_usda(fixture))
    assert rows and rows[0]["source_key"] == str(rows[0]["payload"]["fdcId"])
    assert "foodNutrients" in rows[0]["payload"]


@pytest.mark.parametrize("host", ["data.alltheplaces.xyz", "alltheplaces-data.openaddresses.io"])
def test_selected_atp_resolves_actual_successful_source_run(host):
    artifacts = resolve_atp(
        {"run_id": "2026-10-15", "start_time": "2026-10-15T01:00:00Z"}, spiders=["walmart_us"]
    )
    pinned = pin_atp_output(
        artifacts[0], f"https://{host}/runs/2026-10-01/output/walmart_us.geojson"
    )
    assert pinned.release == "2026-10-01"
    assert pinned.metadata["source_observed_at"] == "2026-10-01"
    with pytest.raises(SourceUnresolved):
        pin_atp_output(artifacts[0], artifacts[0].url)
    with pytest.raises(SourceUnresolved):
        resolve_atp({"run_id": "2026-10-15"}, spiders=["unreviewed_spider"])


def test_atp_advertised_archive_can_use_reviewed_delivery_host():
    from bord_food_api.settings import SOURCE_DEFAULTS

    origin = "https://alltheplaces-data.openaddresses.io"
    url = origin + "/runs/2026-10-01/output.zip"
    artifacts = resolve_atp(
        {"run_id": "2026-10-01", "output_url": url},
        selection_mode="published_archive_us_grocery",
    )
    assert artifacts[0].url == url
    assert origin in SOURCE_DEFAULTS["all_the_places"]["origins"]


def test_atp_rejects_unreviewed_delivery_hosts():
    artifact = resolve_atp({"run_id": "2026-10-15"}, spiders=["walmart_us"])[0]
    with pytest.raises(SourceUnresolved):
        pin_atp_output(
            artifact, "https://unreviewed.example/runs/2026-10-01/output/walmart_us.geojson"
        )
    with pytest.raises(SourceUnresolved):
        resolve_atp(
            {"run_id": "2026-10-01", "output_url": "https://unreviewed.example/output.zip"},
            selection_mode="published_archive_us_grocery",
        )


def test_atp_grocery_format_country_and_department_filter():
    rows = list(
        parse_atp_geojson(
            binary(
                collection(
                    feature(),
                    feature("2", "Example Pharmacy"),
                    feature("3", **{"addr:country": "CA"}),
                    feature("4", shop="convenience"),
                    feature("5", shop=""),
                    feature("6", **{"addr:country": ""}),
                )
            ),
            "new_spider",
        )
    )
    assert len(rows) == 1
    assert rows[0]["source_key"] == "new_spider:1"
    assert rows[0]["payload"]["chain_candidate"] is True
    assert rows[0]["payload"]["latitude"] == 41.6
    assert rows[0]["payload"]["address"]["street"] == "10 Synthetic Street"


def test_atp_multibanner_mapping_and_stable_source_ids():
    rows = list(
        parse_atp_geojson(
            binary(
                collection(
                    feature(brand="Ralphs"),
                    feature("2", brand="Unknown operator"),
                )
            ),
            "kroger_us",
        )
    )
    assert len(rows) == 1
    assert rows[0]["payload"]["chain_name"] == "Ralphs"
    assert rows[0]["payload"]["source_properties"]["brand"] == "Ralphs"
    with pytest.raises(ValueError, match="stable source"):
        bad = feature()
        del bad["properties"]["ref"]
        list(parse_atp_geojson(binary(collection(bad)), "new_spider"))


def test_atp_archive_independent_scopes_and_resource_preflight(tmp_path):
    archive = tmp_path / "output.zip"
    with ZipFile(archive, "w") as target:
        target.writestr(
            "output/new_grocer.geojson", json.dumps(collection(feature(), feature("2")))
        )
        target.writestr("output/singleton.geojson", json.dumps(collection(feature())))
        target.writestr(
            "output/not_grocery.geojson", json.dumps(collection(feature(shop="clothes")))
        )
        target.writestr("output/broken.geojson", '{"features":')
        target.writestr("metadata.txt", "not a retailer URL to fetch")
    scopes = {scope["partition"]: scope for scope in parse_atp_archive_scopes(archive)}
    assert len(scopes["new_grocer"]["records"]) == 2
    assert next(iter(scopes["singleton"]["records"]))["payload"]["chain_candidate"]
    assert not scopes["not_grocery"]["complete"]
    assert scopes["broken"]["error"] and not scopes["broken"]["complete"]
    repeat = list(parse_atp_archive_scopes(archive))
    assert [
        (item["partition"], item["member_sha256"], list(item["records"])) for item in repeat
    ] == [
        (item["partition"], item["member_sha256"], list(item["records"]))
        for item in scopes.values()
    ]
    with pytest.raises(ValueError, match="budget"):
        list(parse_atp_archive_scopes(archive, max_decompressed_bytes=10))
    with pytest.raises(SourceUnresolved, match="preflight"):
        resolve_atp(
            {
                "run_id": "run",
                "output_url": "https://data.alltheplaces.xyz/out.zip",
                "output_size": 100,
            },
            selection_mode="published_archive_us_grocery",
            max_artifact_bytes=50,
        )


@pytest.mark.parametrize("member", ["../escape.geojson", "/absolute.geojson", "a\\b.geojson"])
def test_atp_archive_rejects_traversal(tmp_path, member):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as target:
        target.writestr(member, "{}")
    with pytest.raises(ValueError, match="Unsafe"):
        list(parse_atp_archive_scopes(archive))


def test_atp_tar_stream_and_link_rejection(tmp_path):
    archive = tmp_path / "output.tar.gz"
    data = json.dumps(collection(feature())).encode()
    with tarfile.open(archive, "w:gz") as target:
        member = tarfile.TarInfo("output/grocery.geojson")
        member.size = len(data)
        target.addfile(member, io.BytesIO(data))
    assert next(iter(parse_atp_archive_scopes(archive)))["complete"]
    with tarfile.open(archive, "w:gz") as target:
        member = tarfile.TarInfo("symlink.geojson")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        target.addfile(member)
    with pytest.raises(ValueError, match="links"):
        list(parse_atp_archive_scopes(archive))


def test_snap_resolver_never_substitutes_history_or_invents_current_url():
    with pytest.raises(SourceUnresolved, match="source_location_unresolved"):
        resolve_snap('<a href="https://www.fns.usda.gov/historical.csv">old</a>')
    current = "https://www.fns.usda.gov/current.csv"
    assert resolve_snap(f'<a href="{current}">current</a>').url == current
    assert resolve_snap("", override=current).url == current
    for url in (
        "http://www.fns.usda.gov/current.csv",
        "https://attacker.test/file.csv",
        "https://user:secret@www.fns.usda.gov/file.csv",
    ):
        with pytest.raises(SourceUnresolved):
            resolve_snap("", override=url)


def test_snap_csv_explicit_schema_and_authorization_only():
    data = io.BytesIO(
        b"Record ID,Store Name,Street Address,City,State,Zip Code,Latitude,Longitude\n"
        b"0001,Synthetic Market,10 Example St,Test,IA,00001,41.6,-91.5\n"
    )
    row = next(iter(parse_snap_csv(data)))
    assert row["source_key"] == "0001"
    assert row["payload"]["snap"]["authorized_in_snapshot"] is True
    assert row["payload"]["address"]["postal_code"] == "00001"
    assert "status" not in row["payload"] and "closed" not in row["payload"]
    assert not data.closed
    with pytest.raises(ValueError, match="Unknown SNAP CSV schema"):
        list(parse_snap_csv(io.BytesIO(b"random,address\n1,somewhere\n")))


@pytest.mark.parametrize(
    "code,expected",
    [
        ("012345678905", "00012345678905"),
        ("4006381333931", "04006381333931"),
        ("012345678906", None),
        ("123", None),
        ("01234567890x", None),
        ("１２３４５６７８", None),
        (12345678905, None),
    ],
)
def test_gtin_strict_check_digit_and_padding(code, expected):
    assert strict_gtin(code) == expected


def test_off_country_filter_retained_unknown_nutrients_and_measures():
    rows = list(
        parse_off_jsonl(
            lines(
                off(serving_size="240 ml", nutrition_data_per="100g"),
                off("4006381333931", countries_tags=["en:germany"]),
                off("00000000", countries_tags=[]),
            ),
            retained_codes=["00000000"],
        )
    )
    assert len(rows) == 2
    assert rows[0]["payload"]["nutrition"]["sodium_100g"] == 0
    assert rows[0]["payload"]["nutrition"]["fiber_100g"] is None
    assert rows[0]["payload"]["nutrition"]["sodium_unit"] == "g"
    assert rows[0]["payload"]["measures"][0]["basis"] == "volume"
    assert not rows[0]["payload"]["measures"][0]["verified_density"]
    assert rows[1]["payload"]["country_scope"] == "retained_identity"


def test_off_delta_continuity_overlap_duplicate_and_filtered_empty():
    index = "openfoodfacts_products_200_300.json.gz\nopenfoodfacts_products_100_200.json.gz\nopenfoodfacts_products_100_200.json.gz\nopenfoodfacts_products_150_250.json.gz"
    plan = delta_plan(index, 150, now=301)
    assert [(item.from_ts, item.to_ts) for item in plan] == [(100, 200), (150, 250), (200, 300)]
    assert list(parse_off_jsonl(lines(off(countries_tags=["en:germany"])))) == []
    # The interval end, not any filtered row timestamp, is the acknowledged cursor.
    assert plan[-1].to_ts == 300
    assert delta_plan(index, 300, now=301) == []


@pytest.mark.parametrize(
    "index,kwargs,message",
    [
        ("openfoodfacts_products_200_300.json.gz", {}, "gap"),
        ("openfoodfacts_products_100_200.json.gz", {"now": 999999}, "stale"),
        ("openfoodfacts_products_100_200.json.gz", {"baseline_parser_version": "0"}, "Parser"),
        ("unexpected.json.gz", {}, "format"),
        ("openfoodfacts_products_200_100.json.gz", {}, "Invalid"),
    ],
)
def test_off_gaps_staleness_parser_and_invalid_feed(index, kwargs, message):
    with pytest.raises(ReconciliationRequired, match=message):
        delta_plan(index, 100, **kwargs)


def test_off_baseline_overlap_is_not_max_filtered_timestamp():
    plan = delta_plan(
        "openfoodfacts_products_100_200.json.gz\nopenfoodfacts_products_200_300.json.gz",
        250,
        baseline_start=150,
    )
    assert plan[0].from_ts == 100 and plan[-1].to_ts == 300
    with pytest.raises(ReconciliationRequired, match="gap"):
        delta_plan("openfoodfacts_products_200_300.json.gz", 250, baseline_start=150)


def test_off_revisions_deletion_reconciliation_and_obsolete():
    prior = reconcile_off({}, products(off(modified=200), off("4006381333931", modified=100)))
    assert reconcile_off(prior, products(off(modified=100))) == prior
    assert reconcile_off(prior, []) == prior  # No tombstones in changed-product exports.
    with pytest.raises(ReconciliationRequired, match="same source timestamp"):
        reconcile_off(prior, products(off(modified=200, product_name="conflicting")))
    merged = reconcile_off(
        prior,
        products(off(modified=100)),
        full=True,
        overlap=products(off(modified=300, obsolete=1)),
    )
    assert set(merged) == {"012345678905"}
    assert merged["012345678905"]["obsolete"] is True
    assert merged["012345678905"]["last_modified_t"] == 300


def test_open_prices_preserves_dependencies_country_and_actual_purchase_date():
    locations = [{"id": 1, "osm_address_country": "US"}, {"id": 2, "country_code": "FR"}]
    proofs = [{"id": 10, "file_path": "proof.jpg"}]
    prices = [
        {
            "id": 1,
            "location_id": 1,
            "proof_id": 10,
            "price": "2.35",
            "currency": "USD",
            "date": "2023-01-01",
            "created": "2026-10-17",
            "product_code": "012345678905",
        },
        {"id": 2, "location_id": 2, "price": 1},
    ]
    row = next(iter(parse_open_prices(lines(*prices), lines(*locations), lines(*proofs))))
    assert row["payload"]["observed_at"] == "2023-01-01"
    assert row["payload"]["amount"] == "2.35"
    assert row["payload"]["location"]["id"] == 1
    assert not row["payload"]["exact_branch_match"]
    assert not row["payload"]["proof_images_downloaded"]
    with pytest.raises(ValueError, match="unresolved"):
        list(parse_open_prices(lines(*prices), lines(*locations), lines()))


def test_foodkeeper_https_and_storage_ranges_not_precise_expiry():
    with pytest.raises(SourceUnresolved):
        resolve_foodkeeper('<a href="http://www.fsis.usda.gov/foodkeeper.json">old</a>')
    url = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
    assert resolve_foodkeeper(f'<a href="{url}">English JSON</a>').url == url
    row = next(
        iter(
            parse_foodkeeper(
                binary(
                    {
                        "sheets": [
                            {"name": "Category", "data": [{"ID": 1, "Name": "Synthetic category"}]},
                            {
                                "name": "Product",
                                "data": [
                                    {
                                        "ID": 2,
                                        "Name": "Synthetic food",
                                        "Category_ID": 1,
                                        "Refrigerate_Min": 3,
                                        "Refrigerate_Max": 5,
                                        "Refrigerate_Metric": "Days",
                                    }
                                ],
                            },
                        ]
                    }
                )
            )
        )
    )
    assert row["payload"]["storage_guidance"]["Refrigerate_Min"] == 3
    assert row["payload"]["category"]["Name"] == "Synthetic category"
    assert row["payload"]["precise_expiry"] is False


class MockTransport:
    def __init__(self, bodies, final_urls=None):
        self.bodies = bodies
        self.final_urls = final_urls or {}
        self.calls = []

    def get(self, url):
        self.calls.append(("get", url))
        return io.BytesIO(self.bodies[url])

    def fetch(self, url, destination, validators=None):
        self.calls.append(("fetch", url))
        body = self.bodies[url]
        Path(destination).write_bytes(body)
        return {
            "url": self.final_urls.get(url, url),
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }


@pytest.mark.parametrize("host", ["data.alltheplaces.xyz", "alltheplaces-data.openaddresses.io"])
def test_mocked_atp_acquisition_never_fetches_retailer_urls(tmp_path, host):
    url = "https://data.alltheplaces.xyz/runs/latest/output/walmart_us.geojson"
    transport = MockTransport(
        {
            ATP_MANIFEST: json.dumps({"run_id": "2026-10-15"}).encode(),
            url: json.dumps(
                collection(feature(brand="Walmart", website="https://untrusted.retailer.test"))
            ).encode(),
        },
        {url: f"https://{host}/runs/2026-10-01/output/walmart_us.geojson"},
    )
    scope = next(
        iter(acquire_source("all_the_places", {"spiders": ["walmart_us"]}, transport, tmp_path))
    )
    assert scope["release"].startswith("2026-10-01:")
    assert len(list(scope["records"])) == 1
    assert len(transport.calls) == 2
    assert all("untrusted" not in url for _, url in transport.calls)


def test_mocked_off_delta_uses_whole_interval_cursor_with_no_selected_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("time.time", lambda: 250)
    url = "https://static.openfoodfacts.org/data/delta/openfoodfacts_products_100_300.json.gz"
    transport = MockTransport(
        {
            OFF_DELTA_INDEX: b"openfoodfacts_products_100_300.json.gz",
            url: gzip.compress(lines(off(countries_tags=["en:germany"])).getvalue()),
        }
    )
    scope = next(
        iter(
            acquire_source(
                "open_food_facts",
                {},
                transport,
                tmp_path,
                {
                    "watermark": 100,
                    "parser_version": "1",
                    "normalizer_version": "1",
                    "filter_fingerprint": source_filter_fingerprint("open_food_facts", {}),
                    "last_full_reconciliation": 200,
                    "baseline_start": 90,
                },
            )
        )
    )
    assert list(scope["records"]) == []
    assert scope["cursor"]["watermark"] == 300
    assert not scope["complete"]


def test_off_deduplicates_overlapping_exports_on_disk():
    from bord_food_api.sources import dedupe_off_records

    repeated = (
        products(off(modified=100)) + products(off(modified=300)) + products(off(modified=200))
    )
    result = list(dedupe_off_records(repeated))
    assert len(result) == 1 and result[0]["payload"]["last_modified_t"] == 300
    with pytest.raises(ReconciliationRequired, match="same source timestamp"):
        list(
            dedupe_off_records(
                products(off(modified=100)) + products(off(modified=100, product_name="conflict"))
            )
        )


def test_off_unproven_baseline_is_snapshot_only_and_no_delta_clock_is_invented(
    tmp_path, monkeypatch
):
    from bord_food_api.sources import OFF_BASELINE

    monkeypatch.setattr("time.time", lambda: 250)
    transport = MockTransport({OFF_BASELINE: gzip.compress(lines(off()).getvalue())})
    scopes = list(acquire_source("open_food_facts", {}, transport, tmp_path))
    scope = scopes[0]
    assert scope["complete"] and len(list(scope["records"])) == 1
    assert scope["cursor"]["watermark"] is None
    assert scope["cursor"]["snapshot_only"]
    assert scope["cursor"]["alignment_status"] == "baseline_extraction_boundary_unresolved"
    assert transport.calls == [("fetch", OFF_BASELINE)]


def test_off_documented_baseline_clock_replays_overlap_and_keeps_latest(tmp_path, monkeypatch):
    from bord_food_api.sources import OFF_BASELINE

    monkeypatch.setattr("time.time", lambda: 250)
    url = "https://static.openfoodfacts.org/data/delta/openfoodfacts_products_100_300.json.gz"
    transport = MockTransport(
        {
            OFF_BASELINE: gzip.compress(lines(off(modified=100)).getvalue()),
            OFF_DELTA_INDEX: b"openfoodfacts_products_100_300.json.gz",
            url: gzip.compress(lines(off(modified=280, product_name="updated")).getvalue()),
        }
    )
    scopes = list(
        acquire_source(
            "open_food_facts", {"baseline_extraction_started_at": 150}, transport, tmp_path
        )
    )
    assert scopes[0]["cursor"]["watermark"] == 300
    assert scopes[0]["cursor"]["alignment_status"] == "aligned"
    assert len(rows := list(scopes[0]["records"])) == 1
    assert rows[0]["payload"]["name"] == "updated"


def test_usda_mocked_acquisition_reuses_unchanged_dataset_and_sidecar(tmp_path):
    page = "https://fdc.nal.usda.gov/download-datasets/"
    first = "https://fdc.nal.usda.gov/FoodData_Central_foundation_food_json_2026-04.zip"
    branded = "https://fdc.nal.usda.gov/FoodData_Central_branded_food_json_2026-04.zip"
    updated = "https://fdc.nal.usda.gov/FoodData_Central_branded_food_json_2026-10.zip"
    transport = MockTransport(
        {
            page: f'<a href="{first}">foundation</a><a href="{branded}">branded</a>'.encode(),
            first: b"synthetic foundation",
            branded: b"synthetic branded",
            updated: b"new branded",
        }
    )
    policy = {"datasets": ["foundation", "branded"]}
    initial = next(iter(acquire_source("usda_fdc", policy, transport, tmp_path)))
    repeat = next(iter(acquire_source("usda_fdc", policy, transport, tmp_path)))
    assert initial["release"] == repeat["release"]
    assert [url for method, url in transport.calls if method == "fetch"] == [first, branded]
    sidecar = initial["paths"][0].with_suffix(initial["paths"][0].suffix + ".source.json")
    assert json.loads(sidecar.read_text())["url"] == first
    transport.bodies[page] = f'<a href="{first}">foundation</a><a href="{updated}">new</a>'.encode()
    refreshed = next(iter(acquire_source("usda_fdc", policy, transport, tmp_path)))
    assert refreshed["release"] != initial["release"]
    assert transport.calls[-1] == ("fetch", updated)
    assert refreshed["paths"][0] == initial["paths"][0]


def test_decompression_budget_covers_gzip_and_line_reads(tmp_path):
    from bord_food_api.sources import open_source

    artifact = tmp_path / "bomb.jsonl.gz"
    artifact.write_bytes(gzip.compress(lines(off()).getvalue()))
    with (
        open_source(artifact, max_decompressed_bytes=10) as stream,
        pytest.raises(ValueError, match="decompressed byte budget"),
    ):
        list(parse_off_jsonl(stream))
    artifact.write_bytes(gzip.compress(b'{"sheets":' + b" " * 100 + b"[]}"))
    with (
        open_source(artifact, max_decompressed_bytes=10) as stream,
        pytest.raises(ValueError, match="decompressed byte budget"),
    ):
        list(parse_foodkeeper(stream))


def test_filter_fingerprint_is_deterministic_and_versions_effective_scope():
    first = source_filter_fingerprint(
        "open_food_facts",
        {
            "countries": ["en:united-states", "en:germany"],
            "retained_codes": ["2", "1"],
        },
    )
    reordered = source_filter_fingerprint(
        "open_food_facts",
        {
            "retained_codes": ["1", "2"],
            "countries": ["en:germany", "en:united-states"],
        },
    )
    assert first == reordered
    for changed in (
        {"countries": ["en:germany"]},
        {"retained_codes": ["3"]},
        {"parser_version": "2"},
        {"normalizer_version": "2"},
        {"columns": {"id": "ReviewedID"}},
        {"spiders": ["walmart_us"]},
        {"selection_mode": "published_archive_us_grocery"},
    ):
        assert source_filter_fingerprint("open_food_facts", changed) != source_filter_fingerprint(
            "open_food_facts", {}
        )


@pytest.mark.parametrize(
    "changed",
    [
        {"countries": ["en:germany"]},
        {"retained_codes": ["4006381333931"]},
        {"parser_version": "2"},
        {"normalizer_version": "2"},
    ],
)
def test_off_scope_or_transform_change_reconciles_cached_baseline(tmp_path, monkeypatch, changed):
    from bord_food_api.sources import OFF_BASELINE

    monkeypatch.setattr("time.time", lambda: 250)
    url = "https://static.openfoodfacts.org/data/delta/openfoodfacts_products_100_300.json.gz"
    transport = MockTransport(
        {
            OFF_BASELINE: gzip.compress(
                lines(
                    off(modified=100),
                    off("4006381333931", countries_tags=["en:germany"]),
                ).getvalue()
            ),
            OFF_DELTA_INDEX: b"openfoodfacts_products_100_300.json.gz",
            url: gzip.compress(b""),
        }
    )
    policy = {"baseline_extraction_started_at": 150}
    first_scopes = list(acquire_source("open_food_facts", policy, transport, tmp_path))
    initial = first_scopes[0]
    assert len(list(initial["records"])) == 1
    calls_before = list(transport.calls)
    transport.bodies.clear()  # Configuration replay must not need another source request.
    replay_scopes = list(
        acquire_source(
            "open_food_facts", {**policy, **changed}, transport, tmp_path, initial["cursor"]
        )
    )
    replay = replay_scopes[0]
    assert replay["complete"] is True
    assert replay["parser_version"] != initial["parser_version"]
    assert replay["release"] == initial["release"]  # Same bytes, different interpretation.
    assert replay["cursor"]["filter_fingerprint"] != initial["cursor"]["filter_fingerprint"]
    assert transport.calls == calls_before
    rows = list(replay["records"])
    if "countries" in changed:
        assert [row["source_key"] for row in rows] == ["4006381333931"]
    elif "retained_codes" in changed:
        assert len(rows) == 2
    else:
        assert len(rows) == 1


def test_atp_same_bytes_replay_after_parser_change_has_new_transform_identity(tmp_path):
    url = "https://data.alltheplaces.xyz/runs/latest/output/walmart_us.geojson"
    transport = MockTransport(
        {
            ATP_MANIFEST: json.dumps({"run_id": "2026-10-15"}).encode(),
            url: json.dumps(collection(feature(brand="Walmart"))).encode(),
        },
        {url: "https://data.alltheplaces.xyz/runs/2026-10-01/output/walmart_us.geojson"},
    )
    policy = {"spiders": ["walmart_us"]}
    initial_scopes = list(acquire_source("all_the_places", policy, transport, tmp_path))
    initial = initial_scopes[0]
    expected = list(initial["records"])
    calls_before = list(transport.calls)
    transport.bodies.clear()
    replay_scopes = list(
        acquire_source(
            "all_the_places",
            {**policy, "parser_version": "2"},
            transport,
            tmp_path,
            initial["cursor"],
        )
    )
    replay = replay_scopes[0]
    assert replay["release"] == initial["release"]
    assert replay["parser_version"] != initial["parser_version"]
    assert list(replay["records"]) == expected
    assert transport.calls == calls_before


@pytest.mark.parametrize("region", ["PR", "GU", "VI", "AS", "MP", "Puerto Rico"])
def test_territory_scope_is_explicit_for_atp_and_snap(region):
    geojson = collection(feature(**{"addr:state": region}), feature("2", **{"addr:state": "IA"}))
    assert len(list(parse_atp_geojson(binary(geojson), "new_spider"))) == 1
    assert (
        len(list(parse_atp_geojson(binary(geojson), "new_spider", include_territories=True))) == 2
    )
    header = "Record ID,Store Name,Street Address,City,State\n"
    body = f"1,Synthetic Market,Example St,Test,{region}\n2,Synthetic Iowa,Test St,Test,IA\n"
    assert len(list(parse_snap_csv(io.BytesIO((header + body).encode())))) == 1
    assert (
        len(list(parse_snap_csv(io.BytesIO((header + body).encode()), include_territories=True)))
        == 2
    )
    assert source_filter_fingerprint("all_the_places", {}) != source_filter_fingerprint(
        "all_the_places", {"include_territories": True}
    )


def test_open_prices_numeric_decimal_precision_zero_null_and_conditions():
    prices = io.BytesIO(
        b'{"id":1,"location_id":1,"price":0.10000000000000000001,"currency":"USD",'
        b'"channel":"in_store","loyalty_conditions":{"membership":"required"},'
        b'"package_conditions":{"count":2},"price_per":"UNIT"}\n'
        b'{"id":2,"location_id":1,"price":0}\n'
        b'{"id":3,"location_id":1,"price":null}\n'
    )
    rows = list(parse_open_prices(prices, lines({"id": 1, "country_code": "US"}), lines()))
    assert [row["payload"]["amount"] for row in rows] == ["0.10000000000000000001", "0", None]
    payload = rows[0]["payload"]
    assert payload["source_record"]["price"] == "0.10000000000000000001"
    assert payload["currency"] == "USD" and payload["channel"] == "in_store"
    assert payload["loyalty_conditions"] == {"membership": "required"}
    assert payload["package_conditions"] == {"count": 2}
    assert payload["price_per"] == "UNIT"
    assert payload["kind"] == "historical_public_observation"
    assert "stock" not in payload


@pytest.mark.parametrize(
    "amount",
    [
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1e100000",
        b"1e-100000",
        b"-0.01",
        b"true",
        b'"not a price"',
    ],
)
def test_open_prices_rejects_nonfinite_negative_and_unbounded_amounts(amount):
    prices = io.BytesIO(b'{"id":1,"location_id":1,"price":' + amount + b"}\n")
    with pytest.raises((TypeError, ValueError), match="price amount"):
        list(parse_open_prices(prices, lines({"id": 1, "country_code": "US"}), lines()))


def test_unknown_atp_banners_keep_spider_identity_namespace():
    first = next(iter(parse_atp_geojson(binary(collection(feature())), "unreviewed_one")))
    second = next(iter(parse_atp_geojson(binary(collection(feature())), "unreviewed_two")))
    assert first["payload"]["chain_name"] == second["payload"]["chain_name"]
    assert first["payload"]["chain_key"] != second["payload"]["chain_key"]
    assert first["payload"]["chain_key"] == "unreviewed_one:banner:example"


def test_off_retention_gap_recovers_full_snapshot_in_same_job_without_cursor_advance(
    tmp_path, monkeypatch
):
    from bord_food_api.sources import OFF_BASELINE

    monkeypatch.setattr("time.time", lambda: 300)
    transport = MockTransport(
        {
            OFF_DELTA_INDEX: b"openfoodfacts_products_200_300.json.gz",
            OFF_BASELINE: gzip.compress(lines(off(modified=250)).getvalue()),
        }
    )
    cursor = {
        "watermark": 100,
        "parser_version": "1",
        "normalizer_version": "1",
        "filter_fingerprint": source_filter_fingerprint("open_food_facts", {}),
        "last_full_reconciliation": 250,
        "baseline_start": 50,
    }
    scopes = list(acquire_source("open_food_facts", {}, transport, tmp_path, cursor))
    assert len(scopes) == 1
    assert scopes[0]["complete"] is True
    assert scopes[0]["cursor"]["watermark"] is None
    assert scopes[0]["cursor"]["snapshot_only"] is True
    assert scopes[0]["cursor"]["alignment_status"] == "baseline_extraction_boundary_unresolved"
    assert len(list(scopes[0]["records"])) == 1
    assert transport.calls == [("get", OFF_DELTA_INDEX), ("fetch", OFF_BASELINE)]
    assert cursor["watermark"] == 100  # Worker acknowledges only after publication.


def test_off_failed_full_alignment_after_gap_has_only_one_recovery_attempt(tmp_path, monkeypatch):
    from bord_food_api.sources import OFF_BASELINE

    monkeypatch.setattr("time.time", lambda: 300)
    policy = {"baseline_extraction_started_at": 150}
    transport = MockTransport(
        {
            OFF_DELTA_INDEX: b"openfoodfacts_products_200_300.json.gz",
            OFF_BASELINE: gzip.compress(lines(off(modified=250)).getvalue()),
        }
    )
    cursor = {
        "watermark": 100,
        "parser_version": "1",
        "normalizer_version": "1",
        "filter_fingerprint": source_filter_fingerprint("open_food_facts", policy),
        "last_full_reconciliation": 250,
        "baseline_start": 50,
    }
    with pytest.raises(ReconciliationRequired, match="retention gap") as error:
        list(acquire_source("open_food_facts", policy, transport, tmp_path, cursor))
    assert error.value.reason_code == "source_reconciliation_required"
    assert sum(url == OFF_BASELINE for _, url in transport.calls) == 1
    assert cursor["watermark"] == 100
    assert (
        SourceUnresolved("arbitrary private upstream diagnostic").reason_code
        == "source_location_unresolved"
    )


def test_foodkeeper_multilingual_catalog_selects_observed_english_over_https():
    url = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
    html = "".join(
        f'<a href="http://www.fsis.usda.gov/shared/data/{lang}/foodkeeper.json">JSON</a>'
        for lang in ("ES", "EN", "PT")
    )
    assert resolve_foodkeeper(html).url == url
    for wrong in (
        "https://evil.example/shared/data/EN/foodkeeper.json",
        url + "?redirect=1",
        url.replace("/EN/", "/ES/"),
    ):
        with pytest.raises(SourceUnresolved):
            resolve_foodkeeper(f'<a href="{wrong}">English</a>')
    with pytest.raises(SourceUnresolved):
        resolve_foodkeeper("", override=url.replace("https:", "http:"))


def test_foodkeeper_cell_rows_preserve_conditions_null_zero_and_workbook():
    data = {
        "fileName": "SYNTHETIC.xlsx",
        "dataVersion": 1,
        "sheets": [
            {"name": "Category", "data": [[{"ID": 1}, {"Category_Name": "Synthetic category"}]]},
            {
                "name": "Product",
                "data": [
                    [
                        {"ID": 2},
                        {"Name": "Synthetic food"},
                        {"Category_ID": 1},
                        {"DOP_Refrigerate_Min": 0},
                        {"DOP_Refrigerate_Max": None},
                        {"DOP_Refrigerate_Metric": "Days"},
                        {"Freeze_Metric": "Not Recommended"},
                        {"Refrigerate_After_Opening_Min": 2},
                    ]
                ],
            },
        ],
    }
    row = next(parse_foodkeeper(binary(data)))["payload"]
    assert row["source_workbook"]["dataVersion"] == 1
    assert row["category"]["Category_Name"] == "Synthetic category"
    assert row["storage_guidance"]["DOP_Refrigerate_Min"] == 0
    assert row["storage_guidance"]["DOP_Refrigerate_Max"] is None
    assert row["storage_guidance"]["Freeze_Metric"] == "Not Recommended"
    assert row["storage_guidance"]["Refrigerate_After_Opening_Min"] == 2
    assert row["precise_expiry"] is False
    data["sheets"][1]["data"][0].append({"Name": "Duplicate"})
    with pytest.raises(ValueError, match="Duplicate"):
        list(parse_foodkeeper(binary(data)))


def test_foodkeeper_rejects_duplicate_categories_and_unresolved_category():
    data = {
        "sheets": [
            {"name": "Category", "data": [{"ID": 1}, {"ID": 1}]},
            {"name": "Product", "data": [{"ID": 2, "Name": "Synthetic", "Category_ID": 1}]},
        ]
    }
    with pytest.raises(ValueError, match="unique category"):
        list(parse_foodkeeper(binary(data)))
    data["sheets"][0]["data"] = [{"ID": 3}]
    with pytest.raises(ValueError, match="unresolved category"):
        list(parse_foodkeeper(binary(data)))


def test_woodmans_optional_roster_does_not_expand_default_selection():
    manifest = {"run_id": "2026-10-10"}
    assert len(resolve_atp(manifest)) == 4
    artifact = resolve_atp(manifest, spiders=["woodmans_markets_us"])[0]
    assert artifact.partition == "woodmans_markets_us"
    row = next(
        parse_atp_geojson(
            binary(
                collection(
                    feature(
                        brand="Woodman's Markets",
                        **{"addr:full": "10 Synthetic Street, Test City, WI 00000"},
                    )
                )
            ),
            "woodmans_markets_us",
        )
    )
    assert row["payload"]["chain_name"] == "Woodman's Markets"
    assert row["payload"]["address"]["full"] == "10 Synthetic Street, Test City, WI 00000"


def test_open_prices_null_location_is_unknown_but_dangling_reference_fails():
    prices = [
        {"id": 1, "location_id": None, "proof_id": 10, "price": "1.580"},
        {"id": 2, "location_id": 20, "proof_id": 10, "price": "0.000", "currency": "USD"},
    ]
    locations = [{"id": 20, "osm_address_country_code": "US", "osm_address_country": "États-Unis"}]
    rows = list(parse_open_prices(lines(*prices), lines(*locations), lines({"id": 10})))
    assert len(rows) == 1 and rows[0]["source_key"] == "2"
    assert rows[0]["payload"]["amount"] == "0.000"
    assert rows[0]["payload"]["exact_branch_match"] is False
    prices[0]["location_id"] = 999
    with pytest.raises(ValueError, match="unresolved"):
        list(parse_open_prices(lines(*prices), lines(*locations), lines({"id": 10})))


def test_mocked_foodkeeper_acquisition_publishes_immutable_guidance(tmp_path):
    from bord_food_api.platform import Platform
    from bord_food_api.sources import FOODKEEPER_PAGE

    url = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
    workbook = {
        "sheets": [
            {"name": "Category", "data": [[{"ID": 1}, {"Category_Name": "Synthetic"}]]},
            {
                "name": "Product",
                "data": [
                    [
                        {"ID": 2},
                        {"Name": "Synthetic oats"},
                        {"Category_ID": 1},
                        {"Pantry_Min": 0},
                        {"Pantry_Max": None},
                        {"Pantry_Metric": "Days"},
                    ]
                ],
            },
        ]
    }
    transport = MockTransport(
        {
            FOODKEEPER_PAGE: f'<a href="{url.replace("https:", "http:")}">English JSON</a>'.encode(),
            url: json.dumps(workbook).encode(),
        }
    )
    platform = Platform(tmp_path / "catalog")
    scope = next(acquire_source("foodkeeper", {}, transport, tmp_path))
    result = platform.sync(
        "foodkeeper",
        **{
            k: scope[k]
            for k in ("partition", "release", "records", "complete", "cursor", "parser_version")
        },
    )
    manifest = result["manifest"]
    path = platform.object_path(manifest["packs"]["guidance"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    scope = next(acquire_source("foodkeeper", {}, transport, tmp_path, cursor=scope["cursor"]))
    replay = platform.sync(
        "foodkeeper",
        **{
            k: scope[k]
            for k in ("partition", "release", "records", "complete", "cursor", "parser_version")
        },
    )
    assert replay["no_change"] is True
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert platform.current()["generation"] == manifest["generation"]
