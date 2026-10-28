"""Local-only native catalog HTTP contract; household state stays in Bòrd."""

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import tempfile
import time
from contextlib import closing
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import catalog
from .domain import normalize_gtin
from .platform import Platform, ProductIndexUnavailable
from .runtime import crawl_plan, effective_sources


class Meta(BaseModel):
    catalog_generation: str | None = None
    source_refs: list[Any] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None


class Envelope[T](BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    data: T
    meta: Meta


class NativeError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: NativeError


class Identifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: Literal["gtin", "retailer_sku", "plu"]
    value: str = Field(min_length=1, max_length=160)
    chain_id: str | None = Field(default=None, max_length=160)


class ResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifiers: list[Identifier] = Field(min_length=1, max_length=100)


class EnrichLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1, max_length=160)
    product_id: str | None = Field(default=None, max_length=160)
    store_id: str | None = Field(default=None, max_length=160)
    query: str | None = Field(default=None, max_length=200)


class EnrichInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[EnrichLine] = Field(min_length=1, max_length=100)


class RetailEvidence(BaseModel):
    product_id: str
    store_id: str | None = None
    assortment_status: Literal["unknown", "source_reported", "listed", "historical_only"]
    availability: Literal["unknown", "available", "unavailable", "limited"] = "unknown"
    offers: list[dict[str, Any]] = Field(default_factory=list)
    placements: list[dict[str, Any]] = Field(default_factory=list)
    chain_evidence: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    history_truncated: bool = False
    capabilities: dict[str, bool] = Field(default_factory=dict)


class CatalogHTTPError(Exception):
    def __init__(self, status, code, message, **details):
        self.status = status
        self.error = NativeError(
            code=code, message=message, retryable=status == 503, details=details
        )


def fail(status, code, message, **details):
    raise CatalogHTTPError(status, code, message, **details)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class Cursors:
    """Signed bounded keyset cursors survive restarts; no caller supplied offsets."""

    def __init__(self, directory: Path, clock=time.time):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ".cursor_secret"
        descriptor, temporary = tempfile.mkstemp(prefix=".cursor-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            path.chmod(0o600)
            self.secret = path.read_bytes()
            if len(self.secret) != 32:
                raise ValueError("Invalid installation cursor secret")
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.clock = clock

    def encode(self, payload, lifetime=3600):
        raw = canonical({**payload, "expires": int(self.clock()) + lifetime})
        signature = hmac.digest(self.secret, raw, "sha256")
        return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")

    def decode(self, token, code="CURSOR_EXPIRED"):
        try:
            data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            raw, signature = data[:-32], data[-32:]
            if not hmac.compare_digest(signature, hmac.digest(self.secret, raw, "sha256")):
                raise ValueError
            payload = json.loads(raw)
            if payload["expires"] < self.clock():
                raise ValueError
            return payload
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            fail(409, code, "Cursor is invalid or expired; restart the query.")


def distance_km(lat, lon, other_lat, other_lon):
    phi, other_phi = math.radians(lat), math.radians(other_lat)
    delta_phi = other_phi - phi
    delta_lon = math.radians(other_lon - lon)
    hav = math.sin(delta_phi / 2) ** 2 + math.cos(phi) * math.cos(other_phi) * (
        math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(hav)))


def install_routes(app, settings, authenticate):
    platform = Platform(settings.data_dir)
    cursors = Cursors(settings.data_dir)
    router = APIRouter(dependencies=[Depends(authenticate)])
    errors = {status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 503)}
    # HTTPStatus renamed 422 in newer Python releases; keep the public contract stable.
    errors[422]["description"] = "Unprocessable Content"
    unbound, invalid = object(), object()
    bound_manifest = ContextVar("native_catalog_manifest", default=unbound)

    @app.middleware("http")
    async def bind_generation(request, call_next):
        if not (request.url.path.startswith("/v1/") or request.url.path in ("/live", "/ready")):
            return await call_next(request)
        try:
            snapshot = platform.current() or {}
        except (OSError, ValueError):
            snapshot = invalid
        token = bound_manifest.set(snapshot)
        try:
            return await call_next(request)
        finally:
            bound_manifest.reset(token)

    @app.exception_handler(CatalogHTTPError)
    async def catalog_error(request, error):
        return JSONResponse({"error": error.error.model_dump()}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith("/v1/"):
            return JSONResponse(
                {
                    "error": NativeError(
                        code="INVALID_INPUT", message="Invalid request parameters."
                    ).model_dump()
                },
                status_code=422,
            )
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        if request.url.path.startswith("/v1/"):
            return JSONResponse(
                {
                    "error": NativeError(
                        code="UNAUTHORIZED" if error.status_code == 401 else "REQUEST_FAILED",
                        message=str(error.detail),
                        retryable=error.status_code == 503,
                    ).model_dump()
                },
                status_code=error.status_code,
                headers=error.headers,
            )
        return JSONResponse(
            {"detail": error.detail}, status_code=error.status_code, headers=error.headers
        )

    def manifest():
        snapshot = bound_manifest.get()
        if snapshot is invalid:
            fail(503, "CATALOG_UNAVAILABLE", "Catalog publication is unavailable.")
        if snapshot is unbound:
            try:
                return platform.current() or {}
            except (OSError, ValueError):
                fail(503, "CATALOG_UNAVAILABLE", "Catalog publication is unavailable.")
        return snapshot

    def bound_status():
        return platform.status(manifest())

    def generation():
        return manifest().get("generation")

    def require(pack):
        if pack not in manifest().get("packs", {}):
            fail(
                503,
                "CATALOG_NOT_READY",
                f"The {pack} catalog has not been published yet.",
                pack=pack,
            )

    def rows(kind, gen):
        try:
            return platform.records(kind, generation=gen)
        except (ValueError, FileNotFoundError):
            fail(409, "CURSOR_EXPIRED", "Catalog generation expired; restart the query.")
        except sqlite3.Error:
            fail(503, "CATALOG_UNAVAILABLE", "Catalog is unavailable or the query timed out.")

    def find(kind, identifier, gen):
        try:
            value = platform.get(kind, identifier, generation=gen)
        except (sqlite3.Error, OSError, ValueError):
            fail(503, "CATALOG_UNAVAILABLE", "Catalog is unavailable or the query timed out.")
        if value is None:
            fail(404, "NOT_FOUND", "Catalog entity not found.")
        return value

    def response(data, gen, cursor=None, warnings=None):
        refs = []
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict):
                for ref in item.get("source_refs", []):
                    if ref not in refs:
                        refs.append(ref)
        body = Envelope(
            data=data,
            meta=Meta(
                catalog_generation=gen,
                source_refs=refs,
                warnings=warnings or [],
                next_cursor=cursor,
            ),
        ).model_dump()
        etag = '"' + hashlib.sha256(canonical(body)).hexdigest() + '"'
        return JSONResponse(body, headers={"ETag": etag})

    def page(kind, pack, filters, limit, cursor, predicate, transform=None):
        if len(re.findall(r"[^\W_]+", filters.get("query") or "", flags=re.UNICODE)) > 20:
            fail(422, "INVALID_INPUT", "Use at most 20 search terms.")
        require(pack)
        gen, last = generation(), ""
        digest = hashlib.sha256(canonical({"kind": kind, **filters, "limit": limit})).hexdigest()
        if cursor:
            saved = cursors.decode(cursor)
            if saved.get("filters") != digest:
                fail(409, "CURSOR_CONFLICT", "Cursor parameters changed; restart the query.")
            gen, last = saved["generation"], saved["last"]
        values = []
        try:
            with closing(
                platform.iter_records(
                    kind,
                    generation=gen,
                    last=last,
                    query=filters.get("query"),
                    lat=filters.get("lat"),
                    lon=filters.get("lon"),
                    radius_km=filters.get("radius_km", 10),
                )
            ) as records:
                for record in records:
                    if predicate(record, gen):
                        values.append(transform(record, gen) if transform else record)
                    if len(values) > limit:
                        break
        except (ValueError, FileNotFoundError):
            fail(
                409 if cursor else 503,
                "CURSOR_EXPIRED" if cursor else "CATALOG_UNAVAILABLE",
                "Catalog generation is unavailable; restart the query.",
            )
        except sqlite3.Error:
            fail(503, "CATALOG_UNAVAILABLE", "Catalog is unavailable or the query timed out.")
        token = None
        if len(values) > limit:
            token = cursors.encode(
                {"generation": gen, "last": values[limit - 1]["id"], "filters": digest}
            )
        return response(values[:limit], gen, token)

    @app.get("/live")
    def live():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        published = manifest().get("packs", {})
        required = effective_sources(settings, platform.control)["runtime"]["required_packs"]
        hidden = platform.control.hidden_sources()
        packs = {}
        for pack in required:
            available = pack in published
            reason = None if available else "not_published"
            if available:
                try:
                    path = platform.object_path(published[pack])
                    with closing(
                        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
                    ) as db:
                        table = "metadata" if pack == "usda" else "entities"
                        db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                        if pack == "usda" and hidden & {"usda_fdc", "local_usda"}:
                            available, reason = False, "rights_blocked"
                        elif pack != "usda":
                            pack_sources = {
                                row[0] for row in db.execute("SELECT DISTINCT source FROM entities")
                            }
                            if pack_sources and pack_sources <= hidden:
                                available, reason = False, "rights_blocked"
                except (sqlite3.Error, OSError, ValueError):
                    available, reason = False, "catalog_unavailable"
            packs[pack] = {"available": available, "reason": reason}
        okay = all(item["available"] for item in packs.values())
        return JSONResponse(
            {"status": "ready" if okay else "initializing", "packs": packs},
            status_code=200 if okay else 503,
        )

    @router.get("/v1/system/status", response_model=Envelope[dict[str, Any]], responses=errors)
    def system_status():
        status = bound_status()
        return response(status, status.get("catalog_generation"))

    @router.get("/v1/capabilities", response_model=Envelope[dict[str, Any]], responses=errors)
    def capabilities():
        snapshot = manifest()
        published = snapshot.get("packs", {})
        policy = effective_sources(settings, platform.control)
        source_packs = {
            "usda_fdc": "usda",
            "all_the_places": "stores",
            "usda_snap": "stores",
            "open_food_facts": "products",
            "open_prices": "prices",
            "foodkeeper": "guidance",
            "feed_america": "assistance",
            "community_food_assistance": "assistance",
            "osm_food_assistance": "assistance_osm",
        }
        published_sources = snapshot.get("sources", {})
        checked = {
            (row["source"], row["partition"]): row.get("checked_at")
            for row in bound_status().get("sources", [])
        }
        hidden = platform.control.hidden_sources()
        now = time.time()
        sources = {}
        for source, config in policy["sources"].items():
            partitions, observations, warnings, checks = {}, [], [], []
            for key, state in published_sources.items():
                if not key.startswith(source + ":"):
                    continue
                partition = state.get("partition", key.split(":", 1)[1])
                cursor = state.get("cursor") or {}
                observed = None
                basis = None
                if source == "all_the_places":
                    run = cursor.get("source_run")
                    if isinstance(run, str) and re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?",
                        run,
                    ):
                        try:
                            observed = datetime.fromisoformat(run)
                            observed = (
                                observed.replace(tzinfo=UTC)
                                if observed.tzinfo is None
                                else observed
                            )
                            observed = observed.timestamp()
                            basis = "published_source_run"
                        except ValueError:
                            pass
                elif source in {"osm_food_assistance", "feed_america", "community_food_assistance"}:
                    source_time = cursor.get("source_observed_at")
                    if isinstance(source_time, str):
                        try:
                            parsed = datetime.fromisoformat(source_time)
                            if parsed.tzinfo is not None:
                                observed, basis = parsed.timestamp(), "published_source_snapshot"
                        except ValueError:
                            pass
                elif source == "open_food_facts":
                    watermark = cursor.get("watermark")
                    if type(watermark) in (int, float) and not cursor.get("snapshot_only"):
                        observed, basis = watermark, "processed_delta_watermark"
                    if cursor.get("snapshot_only"):
                        warnings.append(
                            {
                                "code": "DELTA_ALIGNMENT_UNRESOLVED",
                                "partition": partition,
                                "message": "Snapshot extraction boundary is unaligned; delta freshness is unknown.",
                            }
                        )
                if observed is not None and (not math.isfinite(observed) or observed > now):
                    warnings.append(
                        {
                            "code": "SOURCE_TIME_UNVERIFIED",
                            "partition": partition,
                            "message": "Source time cannot establish freshness.",
                        }
                    )
                    observed = None
                checked_at = checked.get((source, partition))
                if checked_at is not None:
                    checks.append(checked_at)
                age = now - observed if observed is not None else None
                evidence_stale = age is not None and age > config.get(
                    "freshness_seconds", config["interval_seconds"]
                )
                feed_stale = (
                    checked_at is not None and now - checked_at > config["interval_seconds"]
                )
                if observed is not None:
                    observations.append(observed)
                partitions[partition] = {
                    "source_observed_at": datetime.fromtimestamp(observed, UTC).isoformat()
                    if observed is not None
                    else None,
                    "source_time_basis": basis if observed is not None else None,
                    "source_age_seconds": age,
                    "evidence_stale": evidence_stale,
                    "last_feed_check_at": datetime.fromtimestamp(checked_at, UTC).isoformat()
                    if checked_at is not None
                    else None,
                    "feed_check_stale": feed_stale,
                }
            oldest = min(observations) if observations else None
            sources[source] = {
                "implemented": True,
                "rights_blocked": source in hidden,
                "enabled": config["enabled"],
                "available": source_packs[source] in published
                and source not in hidden
                and bool(partitions),
                "stale": any(
                    row["evidence_stale"] or row["feed_check_stale"] for row in partitions.values()
                ),
                "evidence_stale": any(row["evidence_stale"] for row in partitions.values()),
                "source_observed_at": datetime.fromtimestamp(oldest, UTC).isoformat()
                if oldest is not None
                else None,
                "source_age_seconds": now - oldest if oldest is not None else None,
                "last_feed_check_at": datetime.fromtimestamp(max(checks), UTC).isoformat()
                if checks
                else None,
                "partitions": partitions,
                "warnings": warnings,
            }
        map_crawl = crawl_plan(settings, control=platform.control)
        return response(
            {
                "packs": {
                    name: {
                        "implemented": True,
                        "available": name in published,
                        "enabled": any(
                            config["enabled"]
                            for source, config in policy["sources"].items()
                            if source_packs[source] == name
                        ),
                    }
                    for name in (
                        "usda",
                        "stores",
                        "products",
                        "prices",
                        "guidance",
                        "maps",
                        "assistance",
                        "assistance_osm",
                    )
                },
                "sources": sources,
                "crawling": {
                    "implemented": True,
                    "enabled": map_crawl["allowed"],
                    "available": "maps" in published
                    and any(key.startswith("woodmans_maps:") for key in published_sources),
                    "blocked_reasons": map_crawl["blocked_reasons"],
                },
                "map_assets": {"implemented": True, "rights_blocked": True},
                "remote_lookup": {"implemented": False, "enabled": False},
            },
            snapshot.get("generation"),
        )

    @router.get(
        "/v1/catalog/generations/current", response_model=Envelope[dict[str, Any]], responses=errors
    )
    def current():
        current_manifest = manifest()
        # Object paths and control database details are private implementation data.
        data = {
            key: current_manifest.get(key)
            for key in ("schema_version", "generation", "created_at", "registry_revision")
        }
        data["sources"] = {
            source: {key: state.get(key) for key in ("release", "parser_version")}
            for source, state in current_manifest.get("sources", {}).items()
        }
        data["packs"] = sorted(current_manifest.get("packs", {}))
        return response(data, current_manifest.get("generation"))

    @router.get(
        "/v1/catalog/changes", response_model=Envelope[list[dict[str, Any]]], responses=errors
    )
    def changes(
        after: Annotated[str | None, Query(max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        start = 0
        if after:
            state = cursors.decode(after, "CHANGE_CURSOR_EXPIRED")
            if state.get("kind") != "changes":
                fail(409, "CHANGE_CURSOR_EXPIRED", "Restart change synchronization.")
            start = state["after"]
        events = platform.changes(after=start, limit=limit)
        next_after = events[-1]["seq"] if events else start
        token = cursors.encode({"kind": "changes", "after": next_after}, 30 * 86400)
        return response(events, generation(), token)

    @router.get("/v1/chains", response_model=Envelope[list[dict[str, Any]]], responses=errors)
    def chains(
        country: Annotated[str, Query(min_length=2, max_length=2)] = "US",
        min_stores: Annotated[int, Query(ge=0)] = 2,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ):
        count_cache = {}

        def matches(row, gen):
            if "observed_store_count" not in row:
                if gen not in count_cache:
                    counts = {}
                    for store in platform.iter_records("store", generation=gen):
                        key = store.get("chain_id")
                        counts[key] = counts.get(key, 0) + 1
                    count_cache[gen] = counts
                row["observed_store_count"] = count_cache[gen].get(row["id"], 0)
                row["observed_count_scope"] = {"country": country, "catalog_generation": gen}
            row.setdefault("reported_store_count", None)
            return row.get("country", "US") == country and row["observed_store_count"] >= min_stores

        return page(
            "chain",
            "stores",
            {"country": country, "min_stores": min_stores},
            limit,
            cursor,
            matches,
        )

    @router.get("/v1/chains/{chain_id}", response_model=Envelope[dict[str, Any]], responses=errors)
    def chain(chain_id: str):
        require("stores")
        gen = generation()
        return response(find("chain", chain_id, gen), gen)

    from .assistance_api import register_assistance_routes

    register_assistance_routes(
        router,
        platform=platform,
        page=page,
        response=response,
        find=find,
        require=require,
        generation=generation,
        fail=fail,
        envelope=Envelope,
        errors=errors,
    )

    @router.get("/v1/stores", response_model=Envelope[list[dict[str, Any]]], responses=errors)
    def stores(
        query: Annotated[str | None, Query(max_length=200)] = None,
        state: Annotated[str | None, Query(max_length=2)] = None,
        chain_id: Annotated[str | None, Query(max_length=160)] = None,
        lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
        lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
        radius_km: Annotated[float, Query(ge=0.1, le=100)] = 10,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ):
        if (lat is None) != (lon is None):
            fail(422, "INVALID_INPUT", "Latitude and longitude must be supplied together.")

        def matches(row, gen):
            address = row.get("address") or {}
            if state and row.get("state", address.get("state", address.get("region"))) != state:
                return False
            if chain_id and row.get("chain_id") != chain_id:
                return False
            if query and query.casefold() not in json.dumps(row, ensure_ascii=False).casefold():
                return False
            if lat is not None:
                location = row.get("coordinates") or row.get("location") or {}
                a = row.get("latitude", location.get("latitude", location.get("lat")))
                b = row.get("longitude", location.get("longitude", location.get("lon")))
                if a is None or b is None or distance_km(lat, lon, a, b) > radius_km:
                    return False
            return True

        filters = {
            "query": query,
            "state": state,
            "chain_id": chain_id,
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
        }
        return page("store", "stores", filters, limit, cursor, matches)

    @router.get("/v1/stores/{store_id}", response_model=Envelope[dict[str, Any]], responses=errors)
    def store(store_id: str):
        require("stores")
        gen = generation()
        return response(find("store", store_id, gen), gen)

    @router.get("/v1/products", response_model=Envelope[list[dict[str, Any]]], responses=errors)
    def products(
        query: Annotated[str | None, Query(max_length=200)] = None,
        category: Annotated[str | None, Query(max_length=160)] = None,
        brand: Annotated[str | None, Query(max_length=160)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ):
        def matches(row, gen):
            return (
                (not query or query.casefold() in json.dumps(row).casefold())
                and (not category or category in row.get("categories", []))
                and (not brand or brand in row.get("brands", []))
            )

        return page(
            "product",
            "products",
            {"query": query, "category": category, "brand": brand},
            limit,
            cursor,
            matches,
        )

    @router.post(
        "/v1/products/resolve", response_model=Envelope[list[dict[str, Any]]], responses=errors
    )
    def resolve(body: ResolveInput):
        require("products")
        gen = generation()
        requested = []
        for item in body.identifiers:
            normal = normalize_gtin(item.value) if item.namespace == "gtin" else item.value
            valid = normal is not None and (item.namespace == "gtin" or bool(item.chain_id))
            requested.append((item, normal, valid, []))
        try:
            for item, normal, valid, found in requested:
                if valid:
                    found.extend(
                        platform.product_candidates(
                            item.namespace, normal, item.chain_id, generation=gen
                        )
                    )
        except ProductIndexUnavailable:
            fail(503, "PRODUCT_INDEX_NOT_READY", "The product identifier index needs rebuilding.")
        except sqlite3.OperationalError:
            fail(503, "CATALOG_UNAVAILABLE", "Product lookup is temporarily unavailable.")
        results = [
            {
                "identifier": item.model_dump(),
                "status": "invalid"
                if not valid
                else "exact"
                if len(found) == 1
                else "candidates"
                if found
                else "not_found",
                "candidates": found,
            }
            for item, normal, valid, found in requested
        ]
        return response(results, gen)

    @router.get(
        "/v1/products/{product_id}", response_model=Envelope[dict[str, Any]], responses=errors
    )
    def product(product_id: str):
        require("products")
        gen = generation()
        return response(find("product", product_id, gen), gen)

    def retail(product_id, store_id, channel, gen):
        product_row = find("product", product_id, gen)
        product_id = product_row["id"]
        redirects = platform.manifest(gen).get("redirects", {})
        canonical_store = redirects.get(store_id, store_id)
        history_truncated = False

        def associated(row):
            matches_product = redirects.get(
                row.get("product_id"), row.get("product_id")
            ) == product_id or (
                product_row.get("gtin14") is not None and row.get("gtin14") == product_row["gtin14"]
            )
            return (
                matches_product
                and (
                    not store_id
                    or redirects.get(row.get("store_id"), row.get("store_id")) == canonical_store
                )
                and (not channel or row.get("channel") == channel)
            )

        def evidence_rows(kind):
            nonlocal history_truncated
            result = []
            try:
                with closing(platform.iter_records(kind, generation=gen)) as iterator:
                    for row in iterator:
                        if associated(row):
                            if len(result) == 100:
                                history_truncated = True
                                break
                            result.append(row)
            except (sqlite3.Error, OSError, ValueError):
                fail(503, "CATALOG_UNAVAILABLE", "Evidence is unavailable or the query timed out.")
            return result

        offers = evidence_rows("price")
        listings = evidence_rows("listing")
        placements = []
        placement_rows = evidence_rows("placement")
        map_versions = {}
        for item in placement_rows:
            if item.get("map_id"):
                linked = platform.get("map", item["map_id"], generation=gen)
                if linked:
                    map_versions[item["map_id"]] = linked.get("version")
        for item in placement_rows:
            if associated(item) and (
                not item.get("map_id")
                or item.get("map_id") in map_versions
                and item.get("map_version") is not None
                and item.get("map_version") == map_versions[item["map_id"]]
            ):
                placements.append(item)
        stock = []
        for item in evidence_rows("stock") if store_id is not None else []:
            if not associated(item) or not item.get("valid_until"):
                continue
            try:
                expiry = datetime.fromisoformat(item["valid_until"])
                if expiry.tzinfo is not None and expiry > datetime.now(UTC):
                    stock.append(item)
            except (ValueError, TypeError):
                continue
        availability = stock[-1].get("availability", "unknown") if stock else "unknown"
        if availability not in ("unknown", "available", "unavailable", "limited"):
            availability = "unknown"
        # Historical prices, purchases and banner tags never assert branch stock.
        data = RetailEvidence(
            product_id=product_id,
            store_id=canonical_store,
            history_truncated=history_truncated,
            availability=availability,
            assortment_status="listed" if listings else "historical_only" if offers else "unknown",
            offers=offers,
            placements=placements,
            chain_evidence=product_row.get("chain_evidence", []),
            reason=None
            if listings or stock
            else "No imported branch listing or current stock evidence.",
            capabilities={
                "listing": bool(listings),
                "price": bool(offers),
                "placement": bool(placements),
                "current_stock": bool(stock),
            },
        )
        return data.model_dump()

    @router.get(
        "/v1/products/{product_id}/retail-evidence",
        response_model=Envelope[RetailEvidence],
        responses=errors,
    )
    def evidence(
        product_id: str,
        store_id: Annotated[str | None, Query(max_length=160)] = None,
        channel: Annotated[str | None, Query(max_length=80)] = None,
    ):
        require("products")
        gen = generation()
        return response(retail(product_id, store_id, channel, gen), gen)

    @router.post(
        "/v1/shopping/enrich", response_model=Envelope[list[dict[str, Any]]], responses=errors
    )
    def enrich(body: EnrichInput):
        require("products")
        gen = generation()
        result = []
        for line in body.lines:
            item = {"line_id": line.line_id, "product": None, "retail_evidence": None}
            if line.product_id:
                item["product"] = find("product", line.product_id, gen)
                item["retail_evidence"] = retail(line.product_id, line.store_id, None, gen)
            result.append(item)
        return response(result, gen)

    def food_record(source_id, record_id, revision, gen):
        if source_id in ("usda", "usda_fdc"):
            if platform.control.hidden_sources() & {"usda_fdc", "local_usda"}:
                fail(403, "RIGHTS_BLOCKED", "Source food access is restricted by policy.")
            require("usda")
            # Read the original source payload; no merged nutrition or unit conversion.
            path = platform.object_path(platform.manifest(gen)["packs"]["usda"])
            with catalog.connect(path) as connection:
                row = connection.execute(
                    "SELECT payload FROM foods WHERE fdc_id = ?", (record_id,)
                ).fetchone()
                if row is None:
                    fail(404, "NOT_FOUND", "Source food not found.")
                raw = catalog.unpack(row["payload"])
            current_revision = hashlib.sha256(canonical(raw)).hexdigest()
            result = {
                "source_id": "usda_fdc",
                "record_id": str(record_id),
                "content_revision": current_revision,
                "data": raw,
                "measures": raw.get("foodPortions", []),
            }
        else:
            require("products")
            try:
                result = platform.get_by_source("food", source_id, record_id, generation=gen)
                if result is None:
                    result = platform.get_by_source("product", source_id, record_id, generation=gen)
            except (sqlite3.Error, OSError, ValueError):
                fail(503, "CATALOG_UNAVAILABLE", "Catalog is unavailable or the query timed out.")
            if result is None:
                fail(404, "NOT_FOUND", "Source food not found.")
        if source_id not in ("usda", "usda_fdc"):
            result = {
                **result,
                "source_id": source_id,
                "record_id": record_id,
                "data": result.get("source_record", result),
            }
        if revision and result.get("content_revision") != revision:
            fail(
                409, "REVISION_EXPIRED", "Selected revision is unavailable; review the food again."
            )
        return result

    @router.get(
        "/v1/foods/{source_id}/{record_id}",
        response_model=Envelope[dict[str, Any]],
        responses=errors,
    )
    def food(
        source_id: str,
        record_id: str,
        revision: Annotated[str | None, Query(max_length=160)] = None,
    ):
        gen = generation()
        return response(food_record(source_id, record_id, revision, gen), gen)

    @router.get(
        "/v1/foods/{source_id}/{record_id}/measures",
        response_model=Envelope[list[dict[str, Any]]],
        responses=errors,
    )
    def measures(
        source_id: str,
        record_id: str,
        revision: Annotated[str | None, Query(max_length=160)] = None,
        form: Annotated[str | None, Query(max_length=80)] = None,
        basis: Annotated[str | None, Query(max_length=80)] = None,
    ):
        gen = generation()
        value = food_record(source_id, record_id, revision, gen)
        values = [
            item
            for item in value.get("measures", [])
            if (not form or item.get("form") == form) and (not basis or item.get("basis") == basis)
        ]
        return response(values, gen)

    @router.get(
        "/v1/stores/{store_id}/maps",
        response_model=Envelope[list[dict[str, Any]]],
        responses=errors,
    )
    def maps(store_id: str, floor: Annotated[str | None, Query(max_length=80)] = None):
        require("stores")
        gen = generation()
        canonical_store = find("store", store_id, gen)["id"]
        redirects = platform.manifest(gen).get("redirects", {})
        values = []
        with closing(platform.iter_records("map", generation=gen)) as iterator:
            for item in iterator:
                if redirects.get(
                    item.get("store_id"), item.get("store_id")
                ) == canonical_store and (not floor or item.get("floor") == floor):
                    values.append({key: value for key, value in item.items() if key != "assets"})
                    if len(values) >= 100:
                        break
        return response(values, gen)

    @router.get("/v1/maps/{map_id}/assets/{variant}", responses=errors)
    def map_asset(map_id: str, variant: Literal["original", "preview", "thumbnail"]):
        require("maps")
        row = find("map", map_id, generation())
        if (
            row.get("rights_status") != "permitted"
            or not row.get("display_permitted")
            or not row.get("storage_permitted")
        ):
            fail(403, "RIGHTS_BLOCKED", "Map asset display has not been permitted.")
        asset = row.get("assets", {}).get(variant)
        if not asset:
            fail(404, "NOT_FOUND", "Map asset is unavailable.")
        digest, media = asset.get("sha256", ""), asset.get("media_type")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            fail(404, "NOT_FOUND", "Map asset is unavailable.")
        if media not in ("application/pdf", "image/png", "image/jpeg", "image/webp"):
            fail(403, "UNSAFE_MEDIA", "This asset media type cannot be served.")
        path = settings.data_dir / "objects" / "media" / digest
        media_root = settings.data_dir.resolve() / "objects" / "media"
        if not path.is_file() or path.is_symlink() or path.resolve().parent != media_root:
            fail(404, "NOT_FOUND", "Map asset is unavailable.")
        if path.stat().st_size > 25 * 1024 * 1024:
            fail(403, "UNSAFE_MEDIA", "Map asset exceeds the serving byte limit.")
        with path.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                fail(503, "ASSET_UNAVAILABLE", "Map asset integrity validation failed.")
        # SVG and PDF rendering are deliberately unsupported; originals are attachments.
        return FileResponse(
            path,
            media_type=media,
            filename=f"map-{variant}",
            content_disposition_type="attachment",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )

    @router.get(
        "/v1/guidance/storage", response_model=Envelope[list[dict[str, Any]]], responses=errors
    )
    def guidance(
        query: Annotated[str | None, Query(max_length=200)] = None,
        form: Annotated[str | None, Query(max_length=80)] = None,
        storage_state: Annotated[str | None, Query(max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ):
        return page(
            "guidance",
            "guidance",
            {"query": query, "form": form, "storage_state": storage_state},
            limit,
            cursor,
            lambda row, gen: (
                (not query or query.casefold() in json.dumps(row).casefold())
                and (not form or row.get("form") == form)
                and (not storage_state or row.get("storage_state") == storage_state)
            ),
        )

    app.include_router(router)
    return platform
