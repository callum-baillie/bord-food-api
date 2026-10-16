"""Stream USDA JSON/ZIP files into a new database, then publish it with rename."""

import fcntl
import json
import logging
import math
import os
import sqlite3
import tempfile
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import ijson

from .catalog import SCHEMA, SCHEMA_VERSION, barcode_key
from .download import sha256

LOG = logging.getLogger(__name__)
ROOTS = {"BrandedFoods", "FoundationFoods", "SurveyFoods", "SRLegacyFoods"}
TYPES = {"Branded", "Foundation", "Survey (FNDDS)", "SR Legacy"}


@contextmanager
def import_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "import.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another download/import is already running") from error
        yield


def iter_json(stream):
    events = iter(ijson.parse(stream, use_float=True))
    first = next(events, None)
    if first == ("", "start_array", None):
        prefix = "item"
    else:
        if first != ("", "start_map", None):
            raise ValueError("Expected a USDA JSON object or an array of food records")
        root = next(events, None)
        if not root or root[1] != "map_key" or root[2] not in ROOTS:
            raise ValueError("Unknown USDA JSON root; expected " + ", ".join(sorted(ROOTS)))
        if next(events, None) != (root[2], "start_array", None):
            raise ValueError("USDA food collection must be an array")
        prefix = root[2] + ".item"
    # Rewind the small header read, then keep the full parsing loop in ijson's C backend.
    # Both local files and ZipExtFile support seek; no extracted copy is necessary.
    del events
    stream.seek(0)
    yield from ijson.items(stream, prefix, use_float=True)


def records(path: Path):
    if path.suffix.lower() == ".zip":
        with ZipFile(path) as archive:
            members = [
                item for item in archive.infolist() if item.filename.lower().endswith(".json")
            ]
            if not members:
                raise ValueError(f"{path.name} has no JSON; use the USDA JSON download, not CSV")
            for member in members:
                # Never extract user-supplied archive paths onto the filesystem.
                with archive.open(member) as stream:
                    yield from iter_json(stream)
    elif path.suffix.lower() == ".json":
        with path.open("rb") as stream:
            yield from iter_json(stream)
    else:
        raise ValueError(f"Unsupported source: {path.name}; expected .json or .zip")


def normalize(food: dict) -> dict:
    if not isinstance(food, dict):
        raise TypeError("Food record must be an object")
    food = dict(food)
    if type(food.get("fdcId")) is not int or not 0 < food["fdcId"] < 2**63:
        raise ValueError("Food record needs a positive integer fdcId")
    if not isinstance(food.get("description"), str) or not food["description"].strip():
        raise ValueError(f"Food {food['fdcId']} has no description")
    if food.get("dataType") not in TYPES:
        raise ValueError(f"Food {food['fdcId']} has an unsupported dataType")
    for key in (
        "brandOwner",
        "brandName",
        "gtinUpc",
        "servingSizeUnit",
        "householdServingFullText",
        "ingredients",
        "publicationDate",
        "modifiedDate",
    ):
        if food.get(key) is None:
            food.pop(key, None)
        elif not isinstance(food[key], str):
            raise ValueError(f"Food {food['fdcId']} has an invalid {key}")
    if food.get("servingSize") is None:
        food.pop("servingSize", None)
    elif type(food["servingSize"]) not in (int, float) or not math.isfinite(food["servingSize"]):
        raise ValueError(f"Food {food['fdcId']} has an invalid servingSize")
    category = (
        food.get("foodCategory") or food.get("brandedFoodCategory") or food.get("wweiaFoodCategory")
    )
    if isinstance(category, (str, dict)):
        if isinstance(category, dict) and not isinstance(category.get("description"), str):
            category = None
    else:
        category = None
    if category is not None:
        food["foodCategory"] = category
    else:
        food.pop("foodCategory", None)
    nutrients = food.get("foodNutrients") or []
    if not isinstance(nutrients, list):
        raise TypeError(f"Food {food['fdcId']} has invalid foodNutrients")
    for item in nutrients:
        nutrient = item.get("nutrient", {}) if isinstance(item, dict) else {}
        if (
            type(nutrient.get("id")) is not int
            or not isinstance(nutrient.get("name"), str)
            or not isinstance(nutrient.get("unitName"), str)
        ):
            raise ValueError(f"Food {food['fdcId']} has an invalid nutrient definition")
        amount = item.get("amount")
        if amount is not None and (type(amount) not in (int, float) or not math.isfinite(amount)):
            raise ValueError(f"Food {food['fdcId']} has an invalid nutrient amount")
    food["foodNutrients"] = nutrients
    return food


def build_catalog(paths: list[Path], destination: Path) -> dict:
    """Caller holds import_lock. A failed build never replaces the serving catalog."""
    if not paths:
        raise ValueError("Supply at least one USDA JSON or ZIP file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="catalog-", suffix=".building", dir=destination.parent)
    os.close(fd)
    staging = Path(temporary)
    connection = sqlite3.connect(staging)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA cache_size=-32768")
        connection.execute("PRAGMA temp_store=FILE")
        connection.executescript(SCHEMA)
        sources = []
        total = 0
        for path in paths:
            LOG.info("Importing %s", path.name)
            count = 0
            skipped_nulls = 0
            for raw in records(path):
                # Official Foundation releases contain trailing null placeholders.
                # Count these explicitly; every non-null food must still validate.
                if raw is None:
                    skipped_nulls += 1
                    continue
                food = normalize(raw)
                category = food.get("foodCategory", "")
                category = (
                    category.get("description", "") if isinstance(category, dict) else category
                )
                payload = zlib.compress(
                    json.dumps(food, separators=(",", ":"), allow_nan=False).encode(), level=1
                )
                connection.execute(
                    "INSERT INTO foods VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        food["fdcId"],
                        food["dataType"],
                        food["description"],
                        " ".join(filter(None, (food.get("brandName"), food.get("brandOwner")))),
                        category,
                        barcode_key(food.get("gtinUpc", "")),
                        food.get("publicationDate", ""),
                        payload,
                    ),
                )
                count += 1
                total += 1
                if total % 10000 == 0:
                    connection.commit()
                    LOG.info("Imported %d foods", total)
            if count == 0:
                raise ValueError(f"No food records in {path.name}")
            digest = sha256(path)
            source = {
                "file": path.name,
                "sha256": digest,
                "records": count,
                "skippedNulls": skipped_nulls,
            }
            if skipped_nulls:
                LOG.info("Skipped %d null placeholders in %s", skipped_nulls, path.name)
            sidecar = path.with_suffix(path.suffix + ".source.json")
            if sidecar.exists():
                saved = json.loads(sidecar.read_text())
                if saved.get("sha256") == digest:
                    source["url"] = saved.get("url")
            sources.append(source)
        LOG.info("Building search index for %d foods", total)
        connection.execute("INSERT INTO foods_fts(foods_fts) VALUES ('rebuild')")
        connection.execute("INSERT INTO foods_fts(foods_fts) VALUES ('optimize')")
        connection.execute("ANALYZE")
        report = {
            "importedAt": datetime.now(UTC).isoformat(),
            "totalFoods": total,
            "dataTypes": dict(
                connection.execute("SELECT data_type, count(*) FROM foods GROUP BY data_type")
            ),
            "sources": sources,
            "attribution": "U.S. Department of Agriculture, FoodData Central",
            "license": "CC0 1.0",
        }
        connection.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            [(key, json.dumps(value)) for key, value in report.items()],
        )
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Catalog integrity check failed")
        connection.close()
        with staging.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(staging, destination)
        directory_fd = os.open(destination.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        LOG.info("Catalog ready: %d foods", total)
        return report
    finally:
        connection.close()
        staging.unlink(missing_ok=True)
