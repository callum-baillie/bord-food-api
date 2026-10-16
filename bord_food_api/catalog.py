"""Read-only queries against an atomically replaceable SQLite catalog."""

import json
import re
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE foods (
    fdc_id INTEGER PRIMARY KEY,
    data_type TEXT NOT NULL,
    description TEXT NOT NULL,
    brand TEXT NOT NULL,
    category TEXT NOT NULL,
    gtin TEXT,
    published TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE INDEX foods_gtin ON foods(gtin, published DESC, fdc_id DESC);
CREATE INDEX foods_type ON foods(data_type);
CREATE VIRTUAL TABLE foods_fts USING fts5(
    description, brand, category,
    content='foods', content_rowid='fdc_id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def barcode_key(value: str) -> str | None:
    # Bòrd strips leading zeroes before searching, so accept 8–14 digits here.
    return value.zfill(14) if re.fullmatch(r"[0-9]{8,14}", value) else None


def publication_sort_key(value: str) -> str:
    # Downloads use M/D/YYYY; the live API may use ISO dates. Keep source text intact.
    try:
        if "/" in value:
            return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


@contextmanager
def connect(path: Path):
    # FastAPI may enter and close a synchronous dependency on different worker threads.
    # Each request owns this connection; no connection is shared between requests.
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False
    )
    connection.row_factory = sqlite3.Row
    connection.create_function("publication_sort_key", 1, publication_sort_key, deterministic=True)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise ValueError("Unsupported catalog version; reimport the source datasets")
        yield connection
    finally:
        connection.close()


def unpack(payload: bytes) -> dict:
    return json.loads(zlib.decompress(payload))


def summary(food: dict) -> dict:
    fields = (
        "fdcId",
        "description",
        "dataType",
        "brandOwner",
        "brandName",
        "gtinUpc",
        "servingSize",
        "servingSizeUnit",
        "householdServingFullText",
        "ingredients",
        "foodCategory",
        "publicationDate",
        "modifiedDate",
    )
    result = {key: food[key] for key in fields if key in food}
    result["foodNutrients"] = [
        {
            "nutrientId": item["nutrient"]["id"],
            "nutrientName": item["nutrient"]["name"],
            "unitName": item["nutrient"]["unitName"],
            **({"value": item["amount"]} if "amount" in item else {}),
        }
        for item in food.get("foodNutrients", [])
    ]
    return result


def search(connection, query: str, page: int, page_size: int, data_types: list[str] | None):
    terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    gtin = barcode_key(query)
    params: list = []
    if gtin:
        source, where, order = (
            "foods f",
            "f.gtin = ?",
            "publication_sort_key(f.published) DESC, f.fdc_id DESC",
        )
        params.append(gtin)
    elif terms:
        source = "foods_fts JOIN foods f ON f.fdc_id = foods_fts.rowid"
        where = "foods_fts MATCH ?"
        # Input is tokenized and quoted: it cannot inject FTS operators or SQL.
        params.append(" AND ".join(f'"{term}"*' for term in terms))
        order = "bm25(foods_fts, 5, 2, 1), f.fdc_id DESC"
    else:
        return {"foods": [], "totalHits": 0, "currentPage": page, "totalPages": 0}
    if data_types:
        where += f" AND f.data_type IN ({','.join('?' for _ in data_types)})"
        params.extend(data_types)
    total = connection.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
    rows = connection.execute(
        f"SELECT f.payload FROM {source} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "foods": [summary(unpack(row["payload"])) for row in rows],
        "totalHits": total,
        "currentPage": page,
        "totalPages": (total + page_size - 1) // page_size,
    }


def metadata(connection) -> dict:
    return {
        row["key"]: json.loads(row["value"]) for row in connection.execute("SELECT * FROM metadata")
    }
