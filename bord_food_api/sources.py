"""Offline-testable bulk source contracts and streaming parsers.

No function in this module opens a network connection. Resolvers return pinned
acquisition descriptions; the worker supplies its policy-enforcing transport.
Source payloads retain their native evidence, never retailer stock assumptions.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import re
import sqlite3
import tarfile
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from urllib.parse import urljoin, urlparse
from zipfile import BadZipFile, ZipFile, is_zipfile

import ijson

from .domain import normalize_gtin
from .download import discover
from .importer import normalize, records

ATP_HOST = "data.alltheplaces.xyz"
ATP_DELIVERY_HOSTS = {ATP_HOST, "alltheplaces-data.openaddresses.io"}
ATP_MANIFEST = f"https://{ATP_HOST}/runs/latest.json"
OFF_BASELINE = "https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz"
OFF_DELTA_INDEX = "https://static.openfoodfacts.org/data/delta/index.txt"
SNAP_PAGE = "https://www.fns.usda.gov/snap/retailer-locator"
FOODKEEPER_PAGE = "https://catalog.data.gov/dataset/fsis-foodkeeper-data"


class SourceUnresolved(ValueError):
    """An official current resource could not be established; do not guess."""

    reason_code = "source_location_unresolved"


class ReconciliationRequired(ValueError):
    """A safe contiguous delta cursor cannot be established."""

    reason_code = "source_reconciliation_required"


@dataclass(frozen=True)
class Artifact:
    partition: str
    url: str
    release: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ATPDescriptor:
    """Reviewed spider scope; mappings keep multi-banner operators separate."""

    spider: str
    banner: str | None = None
    format: str | None = None
    banner_map: dict[str, str] = field(default_factory=dict)


ATP_DESCRIPTORS = {
    "woodmans_markets_us": ATPDescriptor("woodmans_markets_us", "Woodman's Markets", "grocery"),
    "walmart_us": ATPDescriptor(
        "walmart_us",
        "Walmart",
        "superstore",
        banner_map={
            "walmart": "Walmart",
            "walmart neighborhood market": "Walmart Neighborhood Market",
        },
    ),
    "aldi_sud_us": ATPDescriptor("aldi_sud_us", "ALDI", "grocery"),
    "target_us": ATPDescriptor("target_us", "Target", "superstore"),
    "kroger_us": ATPDescriptor(
        "kroger_us",
        format="grocery",
        banner_map={
            name.casefold(): name
            for name in (
                "Kroger",
                "Ralphs",
                "Fred Meyer",
                "King Soopers",
                "Fry's",
                "Fry's Food Stores",
                "Gerbes",
                "Pay Less",
                "JayC",
                "Mariano's Fresh Market",
                "Smith's",
                "Dillons",
                "QFC",
                "City Market",
                "Food 4 Less",
                "Foods Co",
                "Mariano's",
                "Pick 'n Save",
                "Metro Market",
                "Harris Teeter",
                "Baker's",
                "Jay C",
            )
        },
    ),
}
GROCERY_SHOPS = {"supermarket", "grocery", "wholesale", "superstore", "warehouse"}
EXCLUDED_SHOPS = {"fuel", "gas", "pharmacy", "convenience", "variety_store"}
US_TERRITORIES = {
    "PR",
    "GU",
    "VI",
    "AS",
    "MP",
    "PUERTO RICO",
    "GUAM",
    "U.S. VIRGIN ISLANDS",
    "US VIRGIN ISLANDS",
    "AMERICAN SAMOA",
    "NORTHERN MARIANA ISLANDS",
}


def _https(url: str, hosts: set[str]) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise SourceUnresolved("Resource does not meet the exact HTTPS source policy")
    return url


def resolve_usda(html: str) -> list[Artifact]:
    """Reuse the legacy per-dataset filename/date resolver unchanged."""
    return [
        Artifact(name, url, Path(urlparse(url).path).stem) for name, url in discover(html).items()
    ]


# Registering an optional reviewed spider must not expand automatic default scope.
ATP_DEFAULT_SPIDERS = ("walmart_us", "aldi_sud_us", "target_us", "kroger_us")


def resolve_atp(
    manifest: dict,
    spiders: Iterable[str] = ATP_DEFAULT_SPIDERS,
    selection_mode: str = "selected_spiders",
    max_artifact_bytes: int | None = None,
) -> list[Artifact]:
    if not isinstance(manifest, dict):
        raise SourceUnresolved("ATP run manifest must be an object")
    run = manifest.get("run_id") or manifest.get("run") or manifest.get("start_time")
    if not isinstance(run, (str, int)) or not str(run).strip():
        raise SourceUnresolved("ATP manifest has no identifiable run")
    metadata = {"manifest_run": str(run), "source_observed_at": manifest.get("start_time")}
    if selection_mode == "published_archive_us_grocery":
        url = manifest.get("output_url")
        if not isinstance(url, str):
            raise SourceUnresolved("ATP manifest advertises no published archive")
        size = (
            manifest.get("size_bytes")
            or manifest.get("output_size")
            or manifest.get("output_size_bytes")
        )
        if size is not None:
            if type(size) is not int or size <= 0:
                raise SourceUnresolved("ATP archive size is invalid")
            if max_artifact_bytes is not None and size > max_artifact_bytes:
                raise SourceUnresolved("ATP archive exceeds the configured preflight byte budget")
        return [
            Artifact(
                "archive",
                _https(url, ATP_DELIVERY_HOSTS),
                str(run),
                {**metadata, "advertised_bytes": size},
            )
        ]
    if selection_mode != "selected_spiders":
        raise ValueError("Unknown ATP selection mode")
    result = []
    for spider in spiders:
        if spider not in ATP_DESCRIPTORS:
            raise SourceUnresolved("Selected ATP spider has no reviewed descriptor")
        result.append(
            Artifact(
                spider,
                f"https://{ATP_HOST}/runs/latest/output/{spider}.geojson",
                str(run),
                {**metadata, "requires_resolved_run": True},
            )
        )
    return result


def pin_atp_output(artifact: Artifact, final_url: str) -> Artifact:
    """A latest-success output can be older than the global latest run."""
    _https(final_url, ATP_DELIVERY_HOSTS)
    match = re.fullmatch(r"/runs/([^/]+)/output/([^/]+)\.geojson", urlparse(final_url).path)
    if not match or match[1] == "latest" or match[2] != artifact.partition:
        raise SourceUnresolved("ATP output did not resolve to a matching distinct run")
    return Artifact(
        artifact.partition,
        final_url,
        match[1],
        {
            **artifact.metadata,
            "requires_resolved_run": False,
            "source_run": match[1],
            "source_observed_at": match[1],
        },
    )


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def _resource(html: str, page: str, hosts: set[str], suffix: str, override: str | None):
    if override:
        return _https(override, hosts)
    parser = _Links()
    parser.feed(html)
    matches = []
    for href in parser.links:
        url = urljoin(page, href)
        if not urlparse(url).path.lower().endswith(suffix):
            continue
        if any(word in url.lower() for word in ("historical", "history", "archive")):
            continue
        try:
            matches.append(_https(url, hosts))
        except SourceUnresolved:
            continue
    if len(set(matches)) != 1:
        raise SourceUnresolved(
            "source_location_unresolved: supply a reviewed current official file"
        )
    return matches[0]


def resolve_snap(html: str, override: str | None = None) -> Artifact:
    url = _resource(html, SNAP_PAGE, {"www.fna.usda.gov", "www.fns.usda.gov"}, ".csv", override)
    return Artifact("current", url, url, {"authorization_only": True})


def resolve_foodkeeper(html: str, override: str | None = None) -> Artifact:
    hosts = {"catalog.data.gov", "www.fsis.usda.gov"}
    if override:
        url = _resource(html, FOODKEEPER_PAGE, hosts, ".json", override)
    else:
        # The official catalog advertises EN/ES/PT and legacy HTTP links. Select
        # the observed English resource, upgrading only its exact official path.
        # Never make an HTTP request or guess a fallback/mirror after a 403.
        parser = _Links()
        parser.feed(html)
        english = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
        candidates = {
            english
            for href in parser.links
            if urljoin(FOODKEEPER_PAGE, href) in (english, english.replace("https:", "http:"))
        }
        if not candidates:
            raise SourceUnresolved("FoodKeeper catalog has no reviewed English JSON resource")
        url = candidates.pop()
    return Artifact("english", url, url)


class _BoundedStream(io.BufferedIOBase):
    """Enforce expanded-byte limits across read, readline and ijson readinto."""

    def __init__(self, source, limit):
        self.source = source
        self.limit = limit
        self.consumed = 0

    def readable(self):
        return True

    def seekable(self):
        return self.source.seekable()

    def _account(self, data):
        self.consumed += len(data)
        if self.consumed > self.limit:
            raise ValueError("Source exceeds its decompressed byte budget")
        return data

    def read(self, size=-1):
        remaining = self.limit - self.consumed + 1
        return self._account(self.source.read(min(size, remaining) if size >= 0 else remaining))

    def read1(self, size=-1):
        return self.read(size)

    def readline(self, size=-1):
        remaining = self.limit - self.consumed + 1
        return self._account(self.source.readline(min(size, remaining) if size >= 0 else remaining))

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def seek(self, offset, whence=0):
        return self.source.seek(offset, whence)

    def tell(self):
        return self.source.tell()


@contextmanager
def open_source(path: Path, max_decompressed_bytes: int = 200 * 1024**3):
    """Stream plain/gzip artifacts under a cumulative expanded-byte budget."""
    if max_decompressed_bytes <= 0:
        raise ValueError("Decompressed byte budget must be positive")
    with Path(path).open("rb") as raw:
        magic = raw.read(2)
        raw.seek(0)
        if magic == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=raw) as stream:
                yield _BoundedStream(stream, max_decompressed_bytes)
        else:
            yield _BoundedStream(raw, max_decompressed_bytes)


def _record(kind: str, key: str, payload: dict) -> dict:
    return {"kind": kind, "source_key": str(key), "payload": payload}


def _number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError("Boolean is not a numeric source value")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite source value")
    return number


def _coordinates(geometry):
    if not geometry:
        return None, None
    if geometry.get("type") != "Point":
        raise ValueError("ATP store geometry must be a point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError("Invalid ATP point coordinates")
    lon, lat = _number(coords[0]), _number(coords[1])
    if lon is None or lat is None or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("ATP point outside coordinate bounds")
    return lat, lon


def _atp_feature(
    feature: dict, spider: str, descriptor: ATPDescriptor | None, include_territories: bool = False
):
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("Invalid ATP feature")
    props = feature.get("properties")
    if not isinstance(props, dict):
        raise TypeError("ATP feature has no properties")
    country = str(props.get("addr:country") or props.get("country") or "").upper()
    if country not in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
        return None
    region = str(props.get("addr:state") or props.get("state") or "").strip().upper()
    if not include_territories and region in US_TERRITORIES:
        return None
    shop = str(props.get("shop") or "").casefold()
    amenity = str(props.get("amenity") or "").casefold()
    if shop in EXCLUDED_SHOPS or amenity in {"fuel", "pharmacy"}:
        return None
    name = props.get("name") or (descriptor.banner if descriptor else None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("ATP feature has no name")
    # Department rows often carry the parent retailer brand as well.
    if re.search(r"\b(pharmacy|fuel (?:station|center)|gas station)\b", name, re.IGNORECASE):
        return None
    if descriptor is None and shop not in GROCERY_SHOPS:
        return None  # Unknown format is a review candidate, not a grocery assertion.
    native_brand = props.get("brand") or props.get("operator") or name
    if descriptor and descriptor.banner_map:
        banner = descriptor.banner_map.get(str(native_brand).casefold())
        if banner is None:
            return None  # Explicit banner mapping is required for a multi-banner family.
    else:
        banner = descriptor.banner if descriptor else props.get("brand")
    if not isinstance(banner, str) or not banner.strip():
        return None
    native_id = props.get("ref") or props.get("@id") or feature.get("id")
    if native_id is None or isinstance(native_id, (dict, list, bool)):
        raise ValueError("ATP feature has no stable source identifier")
    lat, lon = _coordinates(feature.get("geometry"))
    chain_key = (
        f"banner:{banner.casefold()}" if descriptor else f"{spider}:banner:{banner.casefold()}"
    )
    return _record(
        "store",
        f"{spider}:{native_id}",
        {
            "name": name,
            "source_id": str(native_id),
            "spider": spider,
            "chain_key": chain_key,
            "chain_name": banner,
            "chain_candidate": descriptor is None,
            "format": (
                "grocery"
                if banner == "Walmart Neighborhood Market"
                else descriptor.format
                if descriptor
                else shop
            ),
            "country": "US",
            "address": {
                "street": props.get("addr:street_address")
                or " ".join(
                    str(props[k]) for k in ("addr:housenumber", "addr:street") if props.get(k)
                )
                or None,
                "city": props.get("addr:city"),
                "region": props.get("addr:state"),
                "postal_code": props.get("addr:postcode"),
                **({"full": props["addr:full"]} if props.get("addr:full") else {}),
                "country": "US",
            },
            "latitude": lat,
            "longitude": lon,
            "phone": props.get("phone"),
            "website": props.get("website"),
            "hours": props.get("opening_hours"),
            "source_url": props.get("@source_uri"),
            "source_properties": props,
            "attribution": "All The Places",
            "license": "CC0-1.0",
        },
    )


def parse_atp_geojson(
    stream: BinaryIO,
    spider: str,
    descriptor: ATPDescriptor | None = None,
    include_territories: bool = False,
) -> Iterator[dict]:
    """Stream a FeatureCollection; explicit unknown spiders use strict grocery filters."""
    descriptor = descriptor or ATP_DESCRIPTORS.get(spider)
    # Validate the collection header independently; ijson.items alone silently
    # accepts a wrong wrapper as an empty successful source.
    stream.seek(0)
    first = next(ijson.items(stream, "type"), None)
    if first != "FeatureCollection":
        raise ValueError("ATP root must be a FeatureCollection")
    stream.seek(0)
    for feature in ijson.items(stream, "features.item", use_float=True):
        item = _atp_feature(feature, spider, descriptor, include_territories)
        if item is not None:
            yield item


class _DiskRecords:
    """A replayable scope buffered on disk, with constant normalization memory."""

    def __init__(self):
        self.stream = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115 -- scope owns this handle
        self.count = 0

    def append(self, row):
        self.stream.write(json.dumps(row, allow_nan=False).encode() + b"\n")
        self.count += 1

    def __len__(self):
        return self.count

    def __iter__(self):
        self.stream.seek(0)
        for line in self.stream:
            yield json.loads(line)

    def close(self):
        self.stream.close()


def _safe_member(name: str):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name or not path.name:
        raise ValueError("Unsafe ATP archive member")
    return path


def parse_atp_archive_scopes(
    path: Path,
    max_decompressed_bytes: int = 512 * 1024 * 1024,
    max_member_bytes: int = 64 * 1024 * 1024,
    include_territories: bool = False,
) -> Iterator[dict]:
    """Read ZIP or tar outputs without extraction; fail scopes independently.

    Limits cover *all* uncompressed members, including formats we do not parse.
    A missing/malformed/empty scope never supplies complete absence evidence.
    """
    total = 0
    seen = set()

    def parse(name, source, size):
        nonlocal total
        member = _safe_member(name)
        if size < 0 or size > max_member_bytes:
            raise ValueError("ATP member exceeds decompression budget")
        total += size
        if total > max_decompressed_bytes:
            raise ValueError("ATP archive exceeds decompression budget")
        if member.suffix.lower() not in {".geojson", ".json"}:
            return None
        spider = member.stem
        if spider in seen:
            raise ValueError("Duplicate ATP archive source scope")
        seen.add(spider)
        digest = hashlib.sha256()
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            count = 0
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                if count > size or count > max_member_bytes:
                    raise ValueError("ATP member exceeds advertised size/budget")
                digest.update(chunk)
                spool.write(chunk)
            if count != size:
                raise ValueError("Truncated ATP archive member")
            spool.seek(0)
            try:
                rows = _DiskRecords()
                for row in parse_atp_geojson(
                    spool, spider, include_territories=include_territories
                ):
                    rows.append(row)
                return {
                    "partition": spider,
                    "records": rows,
                    "complete": bool(rows),
                    "member_sha256": digest.hexdigest(),
                    "error": None,
                }
            except (TypeError, ValueError, ijson.JSONError) as error:
                if "rows" in locals():
                    rows.close()
                return {
                    "partition": spider,
                    "records": [],
                    "complete": False,
                    "member_sha256": digest.hexdigest(),
                    "error": str(error),
                }

    if is_zipfile(path):
        with ZipFile(path) as archive:
            for member in archive.infolist():
                _safe_member(member.filename)
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("ATP archive symlinks are forbidden")
                with archive.open(member) as source:
                    scope = parse(member.filename, source, member.file_size)
                if scope:
                    yield scope
    else:
        try:
            with tarfile.open(path, mode="r|*") as archive:
                for member in archive:
                    _safe_member(member.name)
                    if member.isdir():
                        continue
                    if not member.isfile():
                        raise ValueError("ATP archive links and special files are forbidden")
                    with archive.extractfile(member) as source:
                        scope = parse(member.name, source, member.size)
                    if scope:
                        yield scope
        except (tarfile.TarError, BadZipFile) as error:
            raise ValueError("Unsupported or malformed ATP archive") from error


def parse_atp_archive(path: Path, **kwargs) -> Iterator[dict]:
    for scope in parse_atp_archive_scopes(path, **kwargs):
        if scope["error"]:
            raise ValueError(f"Invalid ATP member {scope['partition']}: {scope['error']}")
        yield from scope["records"]


SNAP_COLUMNS = {
    "id": ("Record ID", "FNS Number", "FNS_NUMBER", "FNS_NUM"),
    "name": ("Store Name", "STORE_NAME"),
    "street": ("Street Address", "Address Line 1", "Address", "ADDRESS1"),
    "city": ("City", "CITY"),
    "region": ("State", "STATE"),
    "postal_code": ("Zip Code", "Zip5", "ZIP_CODE"),
    "latitude": ("Latitude", "LATITUDE"),
    "longitude": ("Longitude", "LONGITUDE"),
    "store_type": ("Store Type", "STORE_TYPE"),
}


def parse_snap_csv(
    stream: BinaryIO, columns: dict | None = None, include_territories: bool = False
) -> Iterator[dict]:
    """Known schema aliases only; authorization never asserts store-open status."""
    text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(text)
        header = reader.fieldnames or []
        if len(header) != len(set(header)):
            raise ValueError("Duplicate SNAP CSV columns")
        mapping = {}
        for key, aliases in SNAP_COLUMNS.items():
            allowed = (columns[key],) if columns and key in columns else aliases
            found = [name for name in allowed if name in header]
            if len(found) > 1:
                raise ValueError(f"Ambiguous SNAP schema column: {key}")
            mapping[key] = found[0] if found else None
        if any(mapping[key] is None for key in ("id", "name", "street", "city", "region")):
            raise ValueError("Unknown SNAP CSV schema; configure a reviewed column mapping")
        seen = set()
        for row in reader:
            if None in row:
                raise ValueError("SNAP CSV row has unexpected extra columns")
            values = {key: row.get(column) if column else None for key, column in mapping.items()}
            key = values.pop("id")
            if not key or key in seen:
                raise ValueError("SNAP requires unique nonempty authorization identifiers")
            seen.add(key)
            if not values["name"] or not values["street"]:
                raise ValueError("SNAP record is missing required name/address")
            if (
                not include_territories
                and str(values["region"] or "").strip().upper() in US_TERRITORIES
            ):
                continue
            lat, lon = _number(values.pop("latitude")), _number(values.pop("longitude"))
            if (lat is not None and not -90 <= lat <= 90) or (
                lon is not None and not -180 <= lon <= 180
            ):
                raise ValueError("SNAP coordinates outside bounds")
            yield _record(
                "store",
                key,
                {
                    "name": values.pop("name"),
                    "source_id": key,
                    "address": {
                        key: values.pop(key) for key in ("street", "city", "region", "postal_code")
                    },
                    "country": "US",
                    "latitude": lat,
                    "longitude": lon,
                    "snap": {
                        "authorization_id": key,
                        "authorized_in_snapshot": True,
                        "store_type": values["store_type"],
                    },
                    "source_record": row,
                    "attribution": "USDA Food and Nutrition Service",
                },
            )
    finally:
        text.detach()  # Do not close a stream owned by the caller.


def strict_gtin(code) -> str | None:
    """Use the shared strict contract; retain the original source code separately."""
    return normalize_gtin(code)


def _jsonl(
    stream: BinaryIO, max_line_bytes: int = 8 * 1024 * 1024, parse_float=float
) -> Iterator[dict]:
    line_number = 0
    while raw := stream.readline(max_line_bytes + 1):
        line_number += 1
        if len(raw) > max_line_bytes:
            raise ValueError(f"JSONL line {line_number} exceeds the byte limit")
        if not raw.strip():
            continue
        row = json.loads(raw, parse_float=parse_float)
        if not isinstance(row, dict):
            raise TypeError(f"JSONL line {line_number} must contain an object")
        yield row


def _off_product(row: dict) -> dict:
    code = row.get("code") or row.get("_id")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("OFF product needs its original string code")
    modified = row.get("last_modified_t")
    if modified is not None:
        if isinstance(modified, str) and modified.isdigit():
            modified = int(modified)
        if type(modified) is not int or modified < 0:
            raise ValueError("Invalid OFF modification timestamp")
    nutrients = row.get("nutriments") or {}
    if not isinstance(nutrients, dict):
        raise TypeError("Invalid OFF nutriments")
    measures = []
    serving = row.get("serving_size")
    if isinstance(serving, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(g|ml)\s*", serving, re.IGNORECASE)
        if match:
            unit = match[2].lower()
            measures.append(
                {
                    "amount": float(match[1]),
                    "unit": unit,
                    "basis": "mass" if unit == "g" else "volume",
                    "source": "open_food_facts",
                    "verified_density": False,
                }
            )
    return _record(
        "product",
        code,
        {
            "code": code,
            "source_id": code,
            "gtin14": strict_gtin(code),
            "name": row.get("product_name") or row.get("product_name_en"),
            "brands": row.get("brands"),
            "quantity": row.get("quantity"),
            "serving_size": serving,
            "measures": measures,
            "nutrition": nutrients,
            "nutrition_basis": row.get("nutrition_data_per"),
            "countries_tags": row.get("countries_tags", []),
            "last_modified_t": modified,
            "revision": row.get("rev"),
            "obsolete": row.get("obsolete") in (True, 1, "1"),
            "source_record": row,
            "attribution": "Open Food Facts contributors",
            "license": "ODbL-1.0",
            "images_downloaded": False,
        },
    )


def parse_off_jsonl(
    stream: BinaryIO,
    countries: Iterable[str] = ("en:united-states",),
    retained_codes: Iterable[str] = (),
) -> Iterator[dict]:
    allowed, retained = set(countries), set(retained_codes)
    for row in _jsonl(stream):
        code = row.get("code") or row.get("_id")
        tags = row.get("countries_tags") or []
        if not isinstance(tags, list):
            raise TypeError("Invalid OFF countries_tags")
        if code not in retained and not allowed.intersection(tags):
            continue
        product = _off_product(row)
        product["payload"]["country_scope"] = (
            "retained_identity" if code in retained else "selected"
        )
        yield product


DELTA_PATTERN = re.compile(r"openfoodfacts_products_(\d+)_(\d+)\.json\.gz")


@dataclass(frozen=True, order=True)
class DeltaInterval:
    from_ts: int
    to_ts: int
    url: str


def delta_plan(
    index: str,
    cursor: int,
    baseline_start: int | None = None,
    now: int | None = None,
    max_staleness: int = 7 * 86400,
    parser_version: str = "1",
    baseline_parser_version: str = "1",
) -> list[DeltaInterval]:
    """Prove interval coverage, never infer it from retained product timestamps."""
    if parser_version != baseline_parser_version:
        raise ReconciliationRequired("Parser changed; replay/reconcile the baseline")
    if type(cursor) is not int or cursor < 0:
        raise ReconciliationRequired("No compatible acknowledged baseline boundary")
    intervals = set()
    for line in index.splitlines():
        line = line.strip()
        if not line:
            continue
        name = Path(urlparse(line).path).name
        match = DELTA_PATTERN.fullmatch(name)
        if not match:
            raise ReconciliationRequired("Unknown OFF delta index format")
        start, end = map(int, match.groups())
        if start >= end:
            raise ReconciliationRequired("Invalid OFF delta interval")
        # Absolute entries still require the precise official host and path.
        if "://" in line:
            _https(line, {"static.openfoodfacts.org"})
            if urlparse(line).path != f"/data/delta/{name}":
                raise ReconciliationRequired("Unexpected OFF delta path")
        elif line != name:
            raise ReconciliationRequired("Unexpected relative OFF delta path")
        intervals.add(
            DeltaInterval(start, end, f"https://static.openfoodfacts.org/data/delta/{name}")
        )
    if not intervals:
        raise ReconciliationRequired("OFF delta index is empty")
    if now is not None and now - max(interval.to_ts for interval in intervals) > max_staleness:
        raise ReconciliationRequired("OFF delta index is stale")
    boundary = baseline_start if baseline_start is not None else cursor
    if type(boundary) is not int or boundary < 0 or boundary > cursor:
        raise ReconciliationRequired("Invalid baseline retrieval overlap boundary")
    position = boundary
    selected = []
    for interval in sorted(intervals):
        if interval.to_ts <= position:
            continue
        if interval.from_ts > position:
            raise ReconciliationRequired("OFF delta retention gap; full reconciliation required")
        selected.append(interval)
        position = interval.to_ts
    if position < cursor:
        raise ReconciliationRequired("OFF delta index regressed behind the baseline")
    return selected


def _revision(payload):
    modified = payload.get("last_modified_t")
    if type(modified) is not int:
        raise ReconciliationRequired("OFF incremental row has no trustworthy modification time")
    return modified


def _business(payload):
    # Scope is local selection metadata, not an upstream revision.
    return json.dumps(
        {k: v for k, v in payload.items() if k != "country_scope"},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def reconcile_off(
    prior: dict[str, dict],
    rows: Iterable[dict],
    full: bool = False,
    overlap: Iterable[dict] = (),
) -> dict[str, dict]:
    """Apply revisions before publication; full reconciliation withdraws absent rows.

    ``prior`` maps original codes to payloads. A full baseline must be followed by
    verified overlapping deltas; callers establish the extraction clock via
    delta_plan rather than taking the maximum timestamp among selected products.
    Active-products deltas alone never delete a prior row.
    """
    result = {} if full else dict(prior)
    for record in rows:
        if record.get("kind") != "product":
            raise ValueError("OFF reconciliation accepts only product records")
        key, payload = record["source_key"], record["payload"]
        old = result.get(key)
        if old is not None:
            previous, incoming = _revision(old), _revision(payload)
            if incoming < previous:
                continue
            if incoming == previous and _business(old) != _business(payload):
                raise ReconciliationRequired(
                    "Conflicting OFF payloads at the same source timestamp"
                )
        result[key] = payload
    if full:
        # A newer previously acknowledged delta must survive a non-atomic dump.
        for key in result.keys() & prior.keys():
            if _revision(prior[key]) > _revision(result[key]):
                result[key] = prior[key]
    if overlap:
        result = reconcile_off(result, overlap)
    return result


def parse_usda(path: Path) -> Iterator[dict]:
    """The source-neutral view retains the exact validated legacy USDA payload."""
    for food in records(Path(path)):
        if food is not None:
            payload = normalize(food)
            yield _record("food", str(payload["fdcId"]), payload)


def _decimal_amount(value) -> str | None:
    """Keep source decimal precision while bounding fixed-point expansion."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError("Invalid public price amount")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid public price amount") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid public price amount")
    digits = amount.as_tuple()
    if len(digits.digits) > 100 or abs(digits.exponent) > 100 or amount.adjusted() > 100:
        raise ValueError("Public price amount exceeds the decimal expansion limit")
    return format(amount, "f")


def parse_open_prices(
    prices: BinaryIO,
    locations: BinaryIO,
    proofs: BinaryIO,
) -> Iterator[dict]:
    """Join related snapshots before selecting U.S. observations; no dangling facts."""

    with tempfile.TemporaryDirectory(prefix="bord-price-joins-") as temporary:
        connection = sqlite3.connect(Path(temporary) / "joins.sqlite")
        try:
            connection.executescript(
                "CREATE TABLE locations (id TEXT PRIMARY KEY,payload TEXT NOT NULL);"
                "CREATE TABLE proofs (id TEXT PRIMARY KEY,payload TEXT NOT NULL);"
                "CREATE TABLE seen_prices (id TEXT PRIMARY KEY);"
            )
            for table, stream in (("locations", locations), ("proofs", proofs)):
                for row in _jsonl(stream):
                    if row.get("id") is None:
                        raise ValueError("Open Prices exports need unique native IDs")
                    try:
                        connection.execute(
                            f"INSERT INTO {table} VALUES (?,?)",
                            (
                                str(row["id"]),
                                json.dumps(row, allow_nan=False),
                            ),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError("Open Prices exports need unique native IDs") from error
            connection.commit()

            def related(table, key):
                found = connection.execute(
                    f"SELECT payload FROM {table} WHERE id=?", (str(key),)
                ).fetchone()
                return json.loads(found[0]) if found else None

            for price in _jsonl(prices, parse_float=str):
                key = price.get("id")
                if key is None:
                    raise ValueError("Open Prices exports need unique price IDs")
                try:
                    connection.execute("INSERT INTO seen_prices VALUES (?)", (str(key),))
                except sqlite3.IntegrityError as error:
                    raise ValueError("Open Prices exports need unique price IDs") from error
                location_id, proof_id = price.get("location_id"), price.get("proof_id")
                location = related("locations", location_id)
                proof = related("proofs", proof_id) if proof_id is not None else None
                if proof_id is not None and proof is None:
                    raise ValueError(
                        "Open Prices snapshot has unresolved location/proof references"
                    )
                if location_id is None:
                    # A source observation may have no location. It cannot be
                    # assigned to U.S. coverage or a branch; omit it from this pack.
                    continue
                if location is None:
                    raise ValueError(
                        "Open Prices snapshot has unresolved location/proof references"
                    )
                country = (
                    location.get("osm_address_country_code")
                    or location.get("country_code")
                    or location.get("osm_address_country")
                )
                if str(country).upper() not in {"US", "USA", "UNITED STATES"}:
                    continue
                amount = _decimal_amount(price.get("price"))
                code = price.get("product_code")
                yield _record(
                    "price",
                    str(key),
                    {
                        "source_id": str(key),
                        "product_code": code,
                        "gtin14": strict_gtin(code),
                        "amount": amount,
                        "currency": price.get("currency"),
                        "channel": price.get("channel"),
                        "loyalty_conditions": price.get("loyalty_conditions"),
                        "package_conditions": price.get("package_conditions"),
                        "price_per": price.get("price_per"),
                        "price_is_discounted": price.get("price_is_discounted"),
                        "discount_type": price.get("discount_type"),
                        "product_quantity": price.get("product_quantity"),
                        "product_quantity_unit": price.get("product_quantity_unit"),
                        "observed_at": price.get("date"),
                        "source_created_at": price.get("created"),
                        "location_source_id": str(location_id),
                        "location": location,
                        "proof_source_id": str(proof_id) if proof_id is not None else None,
                        "proof": proof,
                        "proof_images_downloaded": False,
                        "source_record": price,
                        "kind": "historical_public_observation",
                        "exact_branch_match": False,
                        "attribution": "Open Prices contributors",
                        "license": "ODbL-1.0",
                    },
                )
        finally:
            connection.close()


def parse_foodkeeper(stream: BinaryIO) -> Iterator[dict]:
    """Read the official workbook-shaped JSON, preserving storage ranges verbatim."""

    def worksheet_row(row):
        # Workbook exports encode each row as an array of one-field cells.
        # Also accept an already flattened row from reviewed local ingestion.
        if isinstance(row, dict):
            return row
        if not isinstance(row, list):
            raise TypeError("Invalid FoodKeeper worksheet row")
        flattened = {}
        for cell in row:
            if not isinstance(cell, dict) or len(cell) != 1:
                raise TypeError("Invalid FoodKeeper worksheet cell")
            key, value = next(iter(cell.items()))
            if key in flattened:
                raise ValueError("Duplicate FoodKeeper worksheet field")
            flattened[key] = value
        return flattened

    data = json.load(stream)
    if not isinstance(data, dict) or not isinstance(data.get("sheets"), list):
        raise TypeError("FoodKeeper JSON must have the documented sheets collection")
    sheets = {}
    for sheet in data["sheets"]:
        if not isinstance(sheet, dict) or not isinstance(sheet.get("data"), list):
            raise TypeError("Invalid FoodKeeper worksheet")
        name = sheet.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("FoodKeeper worksheet needs a name")
        if name in sheets:
            raise ValueError("Duplicate FoodKeeper worksheet")
        sheets[name] = [worksheet_row(row) for row in sheet["data"]]
    products = sheets.get("Product")
    if products is None:
        raise ValueError("FoodKeeper JSON has no Product worksheet")
    categories = {}
    for row in sheets.get("Category", []):
        key = row.get("ID")
        if key is None or isinstance(key, (bool, list, dict)) or str(key) in categories:
            raise ValueError("FoodKeeper needs unique category IDs")
        categories[str(key)] = row
    workbook = {key: value for key, value in data.items() if key != "sheets"}
    seen = set()
    for row in products:
        if not isinstance(row, dict):
            raise TypeError("Invalid FoodKeeper product row")
        key = row.get("ID")
        if key is None or isinstance(key, (bool, list, dict)) or str(key) in seen:
            raise ValueError("FoodKeeper needs unique product IDs")
        seen.add(str(key))
        name = row.get("Name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("FoodKeeper product has no name")
        category_id = row.get("Category_ID")
        if category_id is not None and str(category_id) not in categories:
            raise ValueError("FoodKeeper product has an unresolved category")
        yield _record(
            "guidance",
            str(key),
            {
                "source_id": str(key),
                "name": name,
                "category_source_id": category_id,
                "category": categories.get(str(category_id)),
                "storage_guidance": {
                    key: value
                    for key, value in row.items()
                    if key not in {"ID", "Name", "Category_ID"}
                },
                "source_record": row,
                "source_workbook": workbook,
                "attribution": "USDA FSIS FoodKeeper",
                "license": "CC0-1.0_as_catalogued",
                "precise_expiry": False,
            },
        )


def timestamp(value: str) -> int:
    """Parse explicit source clocks; never substitute the worker's retrieval time."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def source_filter_fingerprint(source: str, policy: dict) -> str:
    """Version the effective record scope independently of artifact bytes."""
    selectors = {
        "source": source,
        "countries": sorted(set(policy.get("countries", ["en:united-states"]))),
        "retained_codes": sorted(set(policy.get("retained_codes", []))),
        "columns": policy.get("columns") or {},
        "selection_mode": policy.get("selection_mode", "selected_spiders"),
        "spiders": sorted(set(policy.get("spiders", ATP_DEFAULT_SPIDERS))),
        "include_territories": bool(policy.get("include_territories", False)),
        "parser_version": str(policy.get("parser_version", "1")),
        "normalizer_version": str(policy.get("normalizer_version", "1")),
    }
    return hashlib.sha256(
        json.dumps(selectors, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def acquire_source(source, policy, transport, directory: Path, cursor=None):
    """Attach transform/scope identity to every source checkpoint and candidate."""
    fingerprint = source_filter_fingerprint(source, policy)
    parser_version = str(policy.get("parser_version", "1"))
    normalizer_version = str(policy.get("normalizer_version", "1"))
    cursor = cursor or {}
    checkpoints = list(cursor.get("partitions", {}).values()) or [cursor]
    changed = any(not item or item.get("filter_fingerprint") != fingerprint for item in checkpoints)
    config = {
        **policy,
        "_filter_fingerprint": fingerprint,
        "_replay_cached": bool(cursor) and changed,
    }
    for scope in _acquire_source(source, config, transport, directory, cursor):
        scope["parser_version"] = f"{parser_version}:{normalizer_version}:{fingerprint}"
        scope["cursor"] = {
            **(scope.get("cursor") or {}),
            "filter_fingerprint": fingerprint,
            "parser_version": parser_version,
            "normalizer_version": normalizer_version,
        }
        scope["metadata"] = {**scope.get("metadata", {}), "filter_fingerprint": fingerprint}
        yield scope


def _acquire_source(source, policy, transport, directory: Path, cursor=None):
    """Acquire bulk artifacts through an injected policy-enforcing transport.

    Yield private candidate scopes. Consumers publish them before acknowledging
    ``cursor``. No examples, research rows or retailer URLs enter this pipeline.
    ``policy`` is the source's effective configuration, not a network bypass.
    """
    import time

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cursor = cursor or {}
    artifact_limit = int(policy.get("max_artifact_bytes", 20 * 1024**3))
    expanded_limit = int(
        policy.get(
            "max_decompressed_bytes", 32 * 1024**2 if source == "foodkeeper" else 200 * 1024**3
        )
    )

    def text(url):
        cached = directory / ("discovery-" + hashlib.sha256(url.encode()).hexdigest() + ".txt")
        if policy["_replay_cached"] and cached.exists():
            return cached.read_text(encoding="utf-8")
        with transport.get(url) as response:
            body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise ValueError("Source discovery metadata exceeds its byte budget")
        decoded = body.decode("utf-8")
        cached.write_text(decoded, encoding="utf-8")
        return decoded

    def fetch(artifact):
        suffix = "".join(Path(urlparse(artifact.url).path).suffixes)[-30:]
        path = directory / (hashlib.sha256(artifact.url.encode()).hexdigest() + suffix)
        sidecar = path.with_name(path.name + ".metadata.json")
        saved = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        if saved.get("sha256") and path.exists():
            with path.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() != saved["sha256"]:
                    saved = {}
        else:
            saved = {}
        # Dated USDA ZIPs are reused by exact checksum, while URLs such as ATP
        # latest and optional snapshots get conditional representation checks.
        if saved and policy["_replay_cached"]:
            return path, saved
        if source in {"usda_fdc", "usda"} and saved.get("release") == artifact.release:
            return path, saved
        started = int(time.time())
        metadata = transport.fetch(artifact.url, path, validators=saved or None)
        if metadata.get("not_modified"):
            if not saved or not path.exists():
                raise ValueError("304 received without a verified cached representation")
            metadata = {**saved, **metadata, "sha256": saved["sha256"]}
        else:
            metadata = {
                **metadata,
                "retrieval_started": started,
                "retrieval_completed": int(time.time()),
            }
        metadata = {**metadata, "release": artifact.release}
        if metadata.get("bytes", 0) > artifact_limit:
            raise ValueError("Artifact exceeds its source byte budget")
        sidecar.write_text(json.dumps(metadata, sort_keys=True) + "\n")
        path.with_suffix(path.suffix + ".source.json").write_text(
            json.dumps(
                {
                    "sha256": metadata["sha256"],
                    "url": metadata.get("url", artifact.url),
                },
                sort_keys=True,
            )
            + "\n"
        )
        return path, metadata

    def observed_records(rows, source_run, source_time=None):
        for row in rows:
            row["payload"]["source_observed_at"] = source_time or source_run
            row["payload"]["last_observed_in_source_run"] = source_run
            yield row

    def stream_records(parser, paths, **kwargs):
        for path in paths:
            with open_source(path, expanded_limit) as stream:
                yield from parser(stream, **kwargs)

    if source in {"usda_fdc", "usda"}:
        artifacts = {
            item.partition: item
            for item in resolve_usda(text("https://fdc.nal.usda.gov/download-datasets/"))
        }
        datasets = tuple(policy.get("datasets", ("foundation", "fndds", "sr_legacy", "branded")))
        if set(datasets) - artifacts.keys():
            raise SourceUnresolved("USDA discovery lacks a configured dataset")
        paths, provenance = [], {}
        for name in datasets:
            path, metadata = fetch(artifacts[name])
            paths.append(path)
            provenance[name] = {**metadata, "url": artifacts[name].url}
        identity = {
            name: {"url": value["url"], "sha256": value["sha256"]}
            for name, value in provenance.items()
        }
        release = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        yield {
            "partition": "catalog",
            "release": release,
            "paths": paths,
            "records": (),
            "complete": True,
            "cursor": provenance,
            "metadata": {"datasets": provenance},
        }
    elif source == "all_the_places":
        manifest = json.loads(text(ATP_MANIFEST))
        artifacts = resolve_atp(
            manifest,
            policy.get("spiders", ATP_DEFAULT_SPIDERS),
            policy.get("selection_mode", "selected_spiders"),
            artifact_limit,
        )
        for artifact in artifacts:
            path, metadata = fetch(artifact)
            if artifact.partition == "archive":
                for scope in parse_atp_archive_scopes(
                    path,
                    max_decompressed_bytes=int(policy.get("max_decompressed_bytes", 200 * 1024**3)),
                    max_member_bytes=int(policy.get("max_member_bytes", 2 * 1024**3)),
                    include_territories=bool(policy.get("include_territories", False)),
                ):
                    yield {
                        **scope,
                        "records": observed_records(
                            scope["records"],
                            artifact.release,
                            artifact.metadata.get("source_observed_at"),
                        ),
                        "release": f"{artifact.release}:{scope['member_sha256']}",
                        "cursor": {"source_run": artifact.release},
                        "metadata": {**artifact.metadata, **metadata},
                    }
            else:
                artifact = pin_atp_output(artifact, metadata.get("url", artifact.url))
                yield {
                    "partition": artifact.partition,
                    "release": f"{artifact.release}:{metadata['sha256']}",
                    "records": observed_records(
                        stream_records(
                            parse_atp_geojson,
                            [path],
                            spider=artifact.partition,
                            include_territories=bool(policy.get("include_territories", False)),
                        ),
                        artifact.release,
                    ),
                    "complete": True,
                    "cursor": {"source_run": artifact.release},
                    "metadata": {**metadata, **artifact.metadata},
                }
    elif source in {"usda_snap", "snap_current"}:
        override = policy.get("url_override") or policy.get("download_url")
        artifact = resolve_snap("" if override else text(SNAP_PAGE), override)
        path, metadata = fetch(artifact)
        yield {
            "partition": artifact.partition,
            "release": metadata["sha256"],
            "records": stream_records(
                parse_snap_csv,
                [path],
                columns=policy.get("columns"),
                include_territories=bool(policy.get("include_territories", False)),
            ),
            "complete": True,
            "cursor": {"sha256": metadata["sha256"]},
            "metadata": {**artifact.metadata, **metadata},
        }
    elif source == "foodkeeper":
        override = policy.get("url_override") or policy.get("download_url")
        artifact = resolve_foodkeeper("" if override else text(FOODKEEPER_PAGE), override)
        path, metadata = fetch(artifact)
        yield {
            "partition": artifact.partition,
            "release": metadata["sha256"],
            "records": stream_records(parse_foodkeeper, [path]),
            "complete": True,
            "cursor": {"sha256": metadata["sha256"]},
            "metadata": metadata,
        }
    elif source == "open_prices":
        paths, metadata = {}, {}
        for name in ("prices", "locations", "proofs"):
            artifact = Artifact(
                name, f"https://prices.openfoodfacts.org/data/{name}.jsonl.gz", name
            )
            paths[name], metadata[name] = fetch(artifact)

        def price_records():
            with (
                open_source(paths["prices"], expanded_limit) as prices,
                open_source(paths["locations"], expanded_limit) as locations,
                open_source(paths["proofs"], expanded_limit) as proofs,
            ):
                yield from parse_open_prices(prices, locations, proofs)

        release = hashlib.sha256(
            json.dumps(
                {key: value["sha256"] for key, value in metadata.items()},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        yield {
            "partition": "joined",
            "release": release,
            "records": price_records(),
            "complete": True,
            "cursor": {"sha256": release},
            "metadata": metadata,
        }
    elif source == "open_food_facts":
        clock = int(time.time())
        last_full = cursor.get("last_full_reconciliation", 0)
        full = (
            not cursor.get("watermark")
            or cursor.get("filter_fingerprint") != policy["_filter_fingerprint"]
            or cursor.get("parser_version") != str(policy.get("parser_version", "1"))
            or cursor.get("normalizer_version") != str(policy.get("normalizer_version", "1"))
            or policy.get("force_reconciliation", False)
            or clock - last_full >= int(policy.get("reconciliation_days", 30)) * 86400
        )
        paths = []
        if full:
            baseline, baseline_metadata = fetch(Artifact("products", OFF_BASELINE, "baseline"))
            baseline_start = policy.get("baseline_extraction_started_at")
            if isinstance(baseline_start, str):
                baseline_start = timestamp(baseline_start)
            baseline_end = baseline_metadata["retrieval_completed"]
            if baseline_start is not None:
                if (
                    type(baseline_start) is not int
                    or baseline_start > baseline_metadata["retrieval_started"]
                ):
                    raise ReconciliationRequired("Invalid documented baseline extraction start")
                intervals = delta_plan(
                    text(OFF_DELTA_INDEX),
                    baseline_end,
                    baseline_start=baseline_start,
                    now=baseline_end,
                )
                if not intervals or intervals[-1].to_ts < baseline_end:
                    raise ReconciliationRequired(
                        "OFF baseline extraction window lacks delta coverage"
                    )
            else:
                # The dump publisher's extraction start is not the time at which
                # this worker downloaded it. Serve a valid snapshot, but make no
                # unsupported claim that incremental coverage is aligned.
                intervals = []
            paths.append(baseline)
        else:
            try:
                intervals = delta_plan(
                    text(OFF_DELTA_INDEX),
                    cursor["watermark"],
                    now=clock,
                    baseline_parser_version=cursor.get("parser_version", ""),
                    parser_version=str(policy.get("parser_version", "1")),
                )
            except ReconciliationRequired:
                # Recover retention gaps/stale feeds in this job. The forced-full
                # branch never enters this handler, so a baseline alignment
                # failure propagates after one bounded recovery attempt.
                yield from _acquire_source(
                    source, {**policy, "force_reconciliation": True}, transport, directory, cursor
                )
                return
            baseline_start = cursor.get("baseline_start")
            baseline_metadata = None
        for interval in intervals:
            path, _ = fetch(Artifact("products", interval.url, str(interval.to_ts)))
            paths.append(path)
        if not paths:
            return
        watermark = (
            intervals[-1].to_ts if intervals else (None if full else cursor.get("watermark"))
        )
        new_cursor = {
            "watermark": watermark,
            "parser_version": "1",
            "baseline_start": baseline_start,
            "last_full_reconciliation": clock if full else last_full,
            "snapshot_only": watermark is None,
            "alignment_status": "aligned"
            if watermark is not None
            else "baseline_extraction_boundary_unresolved",
        }
        yield {
            "partition": "products",
            "release": (
                f"{baseline_metadata['sha256']}:{watermark}"
                if baseline_metadata
                else str(watermark)
            ),
            "records": dedupe_off_records(
                stream_records(
                    parse_off_jsonl,
                    paths,
                    countries=policy.get("countries", ["en:united-states"]),
                    retained_codes=policy.get("retained_codes", []),
                )
            ),
            "complete": full,
            "cursor": new_cursor,
            "metadata": {
                "baseline": baseline_metadata,
                "delta_intervals": [[item.from_ts, item.to_ts] for item in intervals],
                "deletion_feed_guaranteed": False,
            },
        }
    else:
        raise ValueError("No implemented V1 bulk adapter for the configured source")


def dedupe_off_records(rows: Iterable[dict]) -> Iterator[dict]:
    """Collapse baseline/delta overlap on disk before the immutable build.

    OFF exports can repeat a product across several overlapping intervals. Keep
    the newest source timestamp, quarantine equal-clock conflicts and use SQLite
    rather than an unbounded in-memory product dictionary.
    """
    with tempfile.TemporaryDirectory(prefix="bord-off-revisions-") as temporary:
        connection = sqlite3.connect(Path(temporary) / "revisions.sqlite")
        try:
            connection.execute(
                "CREATE TABLE revisions (source_key TEXT PRIMARY KEY, modified INTEGER, "
                "business TEXT NOT NULL, record TEXT NOT NULL)"
            )
            for record in rows:
                key, payload = record["source_key"], record["payload"]
                modified = _revision(payload)
                business = _business(payload)
                previous = connection.execute(
                    "SELECT modified,business FROM revisions WHERE source_key=?",
                    (key,),
                ).fetchone()
                if previous:
                    if modified < previous[0]:
                        continue
                    if modified == previous[0]:
                        if business != previous[1]:
                            raise ReconciliationRequired(
                                "Conflicting OFF payloads at the same source timestamp"
                            )
                        continue
                connection.execute(
                    "INSERT OR REPLACE INTO revisions VALUES (?,?,?,?)",
                    (
                        key,
                        modified,
                        business,
                        json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False),
                    ),
                )
            connection.commit()
            for (record,) in connection.execute("SELECT record FROM revisions ORDER BY source_key"):
                yield json.loads(record)
        finally:
            connection.close()
