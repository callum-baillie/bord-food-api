"""Explicit offline projections/imports from already retained food artifacts."""

import hashlib
import json
from datetime import UTC, datetime

from . import catalog
from .domain import normalize_gtin

PROJECTION_VERSION = "usda-branded-products-v1"
CHART_URL = "https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts"


def usda_products(path, *, release):
    """One source assertion per FDC record; no UPC/name merge or stock inference."""
    with catalog.connect(path) as db:
        for row in db.execute(
            "select fdc_id,payload from foods where data_type='Branded' order by fdc_id"
        ):
            raw = catalog.unpack(row["payload"])
            identity = str(row["fdc_id"])
            brand = raw.get("brandName") or raw.get("brandOwner")
            category = raw.get("foodCategory")
            if isinstance(category, dict):
                category = category.get("description")
            yield {
                "kind": "product",
                "source_key": identity,
                "payload": {
                    "name": raw.get("description"),
                    "source_id": identity,
                    "gtin_raw": raw.get("gtinUpc"),
                    "gtin14": normalize_gtin(raw["gtinUpc"])
                    if isinstance(raw.get("gtinUpc"), str)
                    else None,
                    "identifiers": [{"namespace": "gtin", "value": raw["gtinUpc"]}]
                    if isinstance(raw.get("gtinUpc"), str) and normalize_gtin(raw["gtinUpc"])
                    else [],
                    "brands": [brand] if brand else [],
                    "categories": [category] if category else [],
                    "nutrition": raw.get("foodNutrients", []),
                    "nutrition_basis": "original_usda_record",
                    "serving_size": raw.get("servingSize"),
                    "serving_size_unit": raw.get("servingSizeUnit"),
                    "ingredients": raw.get("ingredients"),
                    "publication_date": raw.get("publicationDate"),
                    "food_reference": {
                        "source_id": "usda_fdc",
                        "record_id": identity,
                        "content_revision": hashlib.sha256(
                            json.dumps(
                                raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                            ).encode()
                        ).hexdigest(),
                    },
                    "source_refs": [
                        {
                            "source_id": "usda_fdc",
                            "record_id": identity,
                            "release_id": release,
                            "parser_version": PROJECTION_VERSION,
                        }
                    ],
                    "source_url": "https://fdc.nal.usda.gov/food-details/"
                    + identity
                    + "/nutrients",
                    "attribution": "USDA FoodData Central — Global Branded Food Products Database",
                    "license": "CC0-1.0",
                    "inventory_status": "unknown",
                    "assortment_status": "unknown",
                    "branch_listings": [],
                    "projection_version": PROJECTION_VERSION,
                },
            }


def cold_storage_chart(document):
    """Reviewed official-source table snapshot; storage ranges stay verbatim."""
    if (
        document.get("source_url") != CHART_URL
        or document.get("source_title") != "Cold Food Storage Chart"
        or not document.get("source_snapshot_sha256")
    ):
        raise ValueError("reviewed_official_chart_required")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows or len(rows) > 2000:
        raise ValueError("invalid_chart_rows")
    for index, row in enumerate(rows):
        if not all(
            isinstance(row.get(k), str) and row[k].strip()
            for k in ("food", "type", "refrigerator", "freezer")
        ):
            raise ValueError("chart_rows_require_explicit_source_cells")
        identity = hashlib.sha256((row["food"] + "\0" + row["type"]).encode()).hexdigest()[:24]
        yield {
            "kind": "guidance",
            "source_key": identity,
            "payload": {
                "source_id": identity,
                "name": row["food"] + " — " + row["type"],
                "category": row["food"],
                "form": row["type"],
                "storage_state": "refrigerated_or_frozen",
                "storage_guidance": {
                    "refrigerator": row["refrigerator"],
                    "freezer": row["freezer"],
                    "refrigerator_temperature": "40°F (4°C) or below",
                    "freezer_temperature": "0°F (-18°C) or below",
                    "freezer_range_basis": "quality_only_continuously_frozen_at_or_below_0F",
                    "not_a_precise_expiry": True,
                },
                "source_record": row,
                "source_title": document["source_title"],
                "source_url": CHART_URL,
                "source_last_reviewed": document.get("source_last_reviewed"),
                "retrieved_at": document.get("retrieved_at"),
                "source_snapshot_sha256": document["source_snapshot_sha256"],
                "attribution": "FoodSafety.gov — U.S. Department of Health and Human Services / USDA FSIS",
                "license": "US-federal-government-work",
                "precise_expiry": False,
                "source_line": row.get("source_line"),
                "foodkeeper_record": False,
            },
        }


def import_usda_products(platform, *, fence=None, progress=None):
    current = platform.current()
    if not current or "usda" not in current["packs"]:
        raise ValueError("published_usda_required")
    release = current["packs"]["usda"].split("/")[-1].removesuffix(".sqlite")

    def records():
        for index, row in enumerate(
            usda_products(platform.object_path(current["packs"]["usda"]), release=release), start=1
        ):
            if progress and index % 1000 == 0:
                progress(index)
            yield row

    return platform.sync(
        "usda_products",
        "branded",
        release,
        records(),
        parser_version=PROJECTION_VERSION,
        complete=True,
        cursor={"usda_pack": release, "projection_version": PROJECTION_VERSION},
        fence=fence,
    )


def timestamp_now():
    return datetime.now(UTC).isoformat()
