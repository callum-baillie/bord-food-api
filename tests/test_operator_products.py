import importlib.util
import json
from pathlib import Path

import pytest

from bord_food_api.operator_products import cold_storage_chart, import_usda_products, usda_products
from bord_food_api.platform import Platform


def test_usda_products_preserve_fdc_ids_units_null_zero_and_no_stock(settings):
    p = Platform(settings.data_dir)
    p.adopt_legacy()
    before = p.current()
    original = p.object_path(before["packs"]["usda"]).read_bytes()
    projected = list(usda_products(p.legacy_path(), release="fixture"))
    assert projected
    for row in projected:
        payload = row["payload"]
        assert payload["source_refs"][0]["record_id"] == row["source_key"]
        assert payload["inventory_status"] == "unknown" and payload["branch_listings"] == []
        assert payload["food_reference"]["source_id"] == "usda_fdc"
    result = import_usda_products(p)
    assert "products" in result["manifest"]["packs"]
    assert result["manifest"]["packs"]["usda"] == before["packs"]["usda"]
    assert p.object_path(before["packs"]["usda"]).read_bytes() == original
    assert import_usda_products(p)["no_change"]


def test_off_import_is_network_free_scoped_and_rejects_tampered_receipt(settings, tmp_path):
    import gzip
    import hashlib

    spec = importlib.util.spec_from_file_location(
        "retained_import", Path(__file__).parents[1] / "scripts/import-retained-products.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = Platform(settings.data_dir)
    p.adopt_legacy()
    path = tmp_path / "off.jsonl.gz"
    raw = b"\n".join(
        json.dumps(
            {"code": code, "product_name": "Synthetic", "countries_tags": countries}
        ).encode()
        for code, countries in [
            ("012345678905", ["en:united-states"]),
            ("012345678912", ["en:france"]),
        ]
    )
    path.write_bytes(gzip.compress(raw))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(str(path) + ".metadata.json").write_text(
        json.dumps({"sha256": digest, "bytes": path.stat().st_size})
    )
    plan = module.run(settings.data_dir, tmp_path / "plan", off=path)
    assert not (tmp_path / "plan").exists() and not plan["source_network"]
    result = module.run(settings.data_dir, tmp_path / "apply", apply=True, off=path, sha256=digest)
    assert result["state"] == "succeeded"
    assert len(p.records("product")) == 1
    assert p.current()["sources"]["open_food_facts:products"]["cursor"]["snapshot_only"]
    with pytest.raises(ValueError):
        module.run(settings.data_dir, tmp_path / "bad", apply=True, off=path, sha256="bad")


def test_storage_chart_conditions_and_original_ranges_are_not_expiry_guesses():
    doc = {
        "source_url": "https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts",
        "source_title": "Cold Food Storage Chart",
        "source_snapshot_sha256": "fixture",
        "rows": [
            {
                "food": "Synthetic eggs",
                "type": "Synthetic cooked",
                "refrigerator": "1 week",
                "freezer": "Do not freeze",
            }
        ],
    }
    row = next(iter(cold_storage_chart(doc)))["payload"]
    assert row["storage_guidance"]["refrigerator"] == "1 week"
    assert row["storage_guidance"]["freezer"] == "Do not freeze"
    assert not row["precise_expiry"] and not row["foodkeeper_record"]
    with pytest.raises(ValueError):
        list(cold_storage_chart({**doc, "source_url": "https://unverified.example"}))


def test_usda_product_projection_respects_parent_rights(settings):
    p = Platform(settings.data_dir)
    p.adopt_legacy()
    import_usda_products(p)
    assert p.records("product")
    p.control.set_action("usda_fdc", "can_display", False)
    assert not p.records("product")
