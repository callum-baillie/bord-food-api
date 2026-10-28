"""Barcode-matched image references and a bounded cache, separate from catalog packs."""

import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .domain import normalize_gtin
from .platform import _sqlite, fsync_dir
from .transport import PolicyError, Transport, TransportError

AWS = "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com"
CDN = "https://images.openfoodfacts.org"
API = "https://world.openfoodfacts.org"
LICENSE = "https://creativecommons.org/licenses/by-sa/3.0/"
ATTRIBUTION = "Open Food Facts contributors"
DEFAULTS = {
    "enabled": False,
    "api_fallback": False,
    "user_agent": "BordFoodAPI/1.0 (https://github.com/callum-baillie/bord-food-api)",
    "max_asset_bytes": 2 * 1024**2,
    "cache_quota_bytes": 1024**3,
    "free_space_reserve_bytes": 5 * 1024**3,
    "negative_ttl_seconds": 86400,
    "error_ttl_seconds": 300,
    "api_daily_limit": 500,
    "asset_daily_limit": 10000,
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS assets(hash TEXT PRIMARY KEY,bytes INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS cache(gtin TEXT PRIMARY KEY,state TEXT NOT NULL,payload TEXT NOT NULL,
 retry_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS budgets(provider TEXT PRIMARY KEY,day TEXT NOT NULL,used INTEGER NOT NULL,
 next_at REAL NOT NULL DEFAULT 0);
"""


class ImageUnavailable(Exception):
    def __init__(self, reason, *, missing=False, retry_after=300):
        self.reason, self.missing, self.retry_after = reason, missing, retry_after
        super().__init__(reason)


def image_policy(policy):
    config = {**DEFAULTS, **policy.get("product_images", {})}
    for name in ("enabled", "api_fallback"):
        if type(config[name]) is not bool:
            raise ValueError("Product image activation flags must be boolean")
    bounds = {
        "max_asset_bytes": (1024, 8 * 1024**2),
        "cache_quota_bytes": (1024, 20 * 1024**3),
        "free_space_reserve_bytes": (0, 1024**4),
        "negative_ttl_seconds": (60, 30 * 86400),
        "error_ttl_seconds": (1, 86400),
        "api_daily_limit": (0, 10000),
        "asset_daily_limit": (0, 100000),
    }
    for name, (low, high) in bounds.items():
        value = config[name]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid product image resource limit: " + name)
    agent = config["user_agent"]
    if (
        not isinstance(agent, str)
        or not 10 <= len(agent) <= 240
        or any(ord(c) < 32 or ord(c) > 126 for c in agent)
    ):
        raise ValueError("Invalid image acquisition User-Agent")
    config["network_enabled"] = policy.get("network", {}).get("mode") == "bulk_only"
    return config


def barcode_path(code):
    if normalize_gtin(code) is None:
        raise ValueError("Invalid image source barcode")
    return code if len(code) <= 8 else "/".join((code[:3], code[3:6], code[6:9], code[9:]))


def front_references(product, expected=None):
    """Use the selected front's original image ID, never an arbitrary first photo."""
    code = product.get("code") or product.get("_id")
    gtin = normalize_gtin(code)
    if not gtin or (expected is not None and expected != gtin):
        return []
    images = product.get("images") or {}
    if not isinstance(images, dict):
        return []
    selected = (
        images.get("selected", {}).get("front", {})
        if isinstance(images.get("selected"), dict)
        else {}
    )
    fronts = []
    if isinstance(selected, dict):
        fronts.extend((lang, entry) for lang, entry in selected.items())
    fronts.extend(
        (key[6:] if key.startswith("front_") else "", entry)
        for key, entry in images.items()
        if key == "front" or key.startswith("front_")
    )
    result, seen = [], set()
    for lang, entry in sorted(fronts, key=lambda x: (x[0] != "en", x[0])):
        if not isinstance(entry, dict) or not re.fullmatch(r"[a-z]{0,3}", lang):
            continue
        image_id, revision = str(entry.get("imgid", "")), str(entry.get("rev", ""))
        if not re.fullmatch(r"[0-9]{1,10}", image_id) or not re.fullmatch(r"[0-9]{1,10}", revision):
            continue
        path = barcode_path(code)
        name = "front" + ("_" + lang if lang else "") + "." + revision + ".400.jpg"
        # The bulk mirror reliably carries uploaded originals and 400px derivatives.
        # imgid is explicitly the source photo selected as the front image.
        urls = [f"{AWS}/data/{path}/{image_id}.400.jpg", f"{CDN}/images/products/{path}/{name}"]
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            result.append(
                {
                    "gtin": gtin,
                    "code": code,
                    "url": url,
                    "language": lang,
                    "kind": "selected_front_source" if url.startswith(AWS) else "front",
                    "source_revision": revision,
                    "image_id": image_id,
                }
            )
    return result[:6]


def thumbnail(data):
    """Decode bounded raster input and strip metadata by writing a small fresh JPEG."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > 16_000_000 or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Unsupported image dimensions/animation")
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((600, 600))
            if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                rgba = image.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
            else:
                clean = image.convert("RGB")
            output = io.BytesIO()
            clean.save(output, format="JPEG", quality=85)
            return output.getvalue(), clean.width, clean.height
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ImageUnavailable("invalid_source_image") from error


class ImageCache:
    def __init__(self, root, policy, *, denied=lambda: set(), clock=time.time, fetcher=None):
        self.root = Path(root) / "product-images"
        self.policy, self.denied, self.clock = policy, denied, clock
        self.fetcher = fetcher or self._download
        self._initialized = False
        self._init_lock = threading.Lock()

    def _init(self):
        with self._init_lock:
            if not self._initialized:
                (self.root / "objects").mkdir(parents=True, exist_ok=True)
                with _sqlite(self.root / "cache.sqlite") as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    db.executescript(SCHEMA)
                self._initialized = True

    def _check(self):
        if not self.policy["enabled"]:
            raise ImageUnavailable("product_images_disabled")
        if "open_food_facts" in self.denied() or "open_food_facts_images" in self.denied():
            raise ImageUnavailable("image_source_rights_blocked")

    @contextmanager
    def _network_lock(self):
        self._init()
        with (self.root / "acquisition.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ImageUnavailable("image_acquisition_busy", retry_after=1) from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _reserve(self, provider):
        self._check()
        if not self.policy["network_enabled"]:
            raise ImageUnavailable("image_network_disabled")
        now = self.clock()
        day = datetime.fromtimestamp(now, UTC).date().isoformat()
        interval = {"api": 5, "cdn": 1, "aws": 0.2}[provider]
        limit = self.policy["api_daily_limit" if provider == "api" else "asset_daily_limit"]
        with _sqlite(self.root / "cache.sqlite") as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT day,used,next_at FROM budgets WHERE provider=?", (provider,)
            ).fetchone()
            used = row[1] if row and row[0] == day else 0
            if row and row[2] > now:
                raise ImageUnavailable(
                    "image_source_cooldown", retry_after=max(1, int(row[2] - now + 1))
                )
            if used >= limit:
                raise ImageUnavailable("image_daily_budget_exhausted", retry_after=3600)
            db.execute(
                "INSERT OR REPLACE INTO budgets VALUES (?,?,?,?)",
                (provider, day, used + 1, now + interval),
            )

    def _cooldown(self, provider, retry_after):
        delay = 60
        try:
            delay = int(retry_after)
        except (ValueError, TypeError):
            try:
                delay = int(parsedate_to_datetime(retry_after).timestamp() - self.clock())
            except (ValueError, TypeError, OverflowError):
                pass
        delay = min(86400, max(5, delay))
        with _sqlite(self.root / "cache.sqlite") as db:
            db.execute(
                "UPDATE budgets SET next_at=max(next_at,?) WHERE provider=?",
                (self.clock() + delay, provider),
            )
        return delay

    def _download(self, url, provider):
        origin = {"api": API, "cdn": CDN, "aws": AWS}[provider]
        if not url.startswith(origin + "/"):
            raise ImageUnavailable("unapproved_image_origin")
        transport = Transport(
            {
                "mode": "bulk_only",
                "origins": [origin],
                "timeout": 3,
                "max_redirects": 0,
                "max_requests": 1,
                "max_seconds": 8,
                "max_artifact_bytes": self.policy["max_asset_bytes"],
                "_check": self._check,
            }
        )
        with transport.get(url, headers={"User-Agent": self.policy["user_agent"]}) as response:
            chunks = []
            while chunk := response.read(65536):
                chunks.append(chunk)
            return b"".join(chunks)

    def _read(self, url, provider):
        self._reserve(provider)
        try:
            data = self.fetcher(url, provider)
            if not isinstance(data, bytes) or len(data) > self.policy["max_asset_bytes"]:
                raise ImageUnavailable("image_byte_limit")
            return data
        except TransportError as error:
            if error.status == 404:
                raise ImageUnavailable("image_not_found", missing=True) from error
            retry = (
                self._cooldown(provider, error.retry_after) if error.status in (429, 503) else 300
            )
            raise ImageUnavailable("image_source_unavailable", retry_after=retry) from error
        except (OSError, PolicyError) as error:
            raise ImageUnavailable("image_source_unavailable") from error

    def _record(self, gtin, state, payload, retry_at=0):
        with _sqlite(self.root / "cache.sqlite") as db:
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                (gtin, state, json.dumps(payload), retry_at),
            )

    def cached(self, gtin):
        self._check()
        if not (self.root / "cache.sqlite").exists():
            return None
        with _sqlite(self.root / "cache.sqlite") as db:
            row = db.execute(
                "SELECT state,payload,retry_at FROM cache WHERE gtin=?", (gtin,)
            ).fetchone()
        if not row:
            return None
        state, raw, retry = row
        if state != "ready":
            if retry > self.clock():
                raise ImageUnavailable(
                    state,
                    missing=state == "not_found",
                    retry_after=max(1, int(retry - self.clock())),
                )
            return None
        meta = json.loads(raw)
        digest = meta.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        try:
            fd = os.open(self.root / "objects" / (digest + ".jpg"), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                data = source.read(self.policy["max_asset_bytes"] + 1)
            if hashlib.sha256(data).hexdigest() != digest or len(data) != meta["bytes"]:
                return None
        except OSError:
            return None
        return data, meta

    def references(self, gtin):
        path = self.root / "references.sqlite"
        if not path.exists():
            return []
        with _sqlite(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute(
                "SELECT payload FROM references_index WHERE gtin=?", (gtin,)
            ).fetchone()
            provenance = db.execute("SELECT payload FROM provenance").fetchone()
        refs = json.loads(row[0]) if row else []
        for ref in refs:
            ref["reference_provenance"] = json.loads(provenance[0])
        return refs

    def import_references(self, records, provenance=None):
        """Build and atomically replace a metadata-only index; serving packs are untouched."""
        self._init()
        with self._network_lock():
            fd, name = tempfile.mkstemp(prefix=".references-", dir=self.root)
            os.close(fd)
            try:
                count = scanned = 0
                with _sqlite(name) as db:
                    db.execute(
                        "CREATE TABLE references_index(gtin TEXT PRIMARY KEY,payload TEXT,modified INTEGER)"
                    )
                    db.execute("CREATE TABLE provenance(payload TEXT NOT NULL)")
                    db.execute("INSERT INTO provenance VALUES (?)", (json.dumps(provenance or {}),))
                    for product in records:
                        scanned += 1
                        if scanned % 1000 == 0 and (
                            Path(name).stat().st_size > self.policy["cache_quota_bytes"]
                            or shutil.disk_usage(self.root).free
                            < self.policy["free_space_reserve_bytes"]
                        ):
                            raise ImageUnavailable("image_reference_disk_budget")
                        refs = front_references(product)
                        if not refs:
                            continue
                        modified = product.get("last_modified_t") or 0
                        if type(modified) is not int:
                            raise ValueError("Invalid image metadata modification time")
                        db.execute(
                            "INSERT INTO references_index VALUES (?,?,?) ON CONFLICT(gtin) DO UPDATE SET payload=excluded.payload,modified=excluded.modified WHERE excluded.modified>modified",
                            (refs[0]["gtin"], json.dumps(refs), modified),
                        )
                    count = db.execute("SELECT count(*) FROM references_index").fetchone()[0]
                with open(name, "rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(name, self.root / "references.sqlite")
                fsync_dir(self.root)
                with _sqlite(self.root / "cache.sqlite") as db:
                    db.execute("DELETE FROM cache WHERE state != 'ready'")
                return {"scanned": scanned, "barcodes_with_front_references": count}
            finally:
                Path(name).unlink(missing_ok=True)

    def _store(self, gtin, raw, ref):
        data, width, height = thumbnail(raw)
        if len(data) > self.policy["max_asset_bytes"]:
            raise ImageUnavailable("image_byte_limit")
        self._check()
        digest = hashlib.sha256(data).hexdigest()
        target = self.root / "objects" / (digest + ".jpg")
        used = sum(
            path.stat().st_size
            for path in (self.root / "objects").glob("*.jpg")
            if path.is_file() and not path.is_symlink()
        )
        if used + (0 if target.exists() else len(data)) > self.policy["cache_quota_bytes"]:
            raise ImageUnavailable("image_cache_quota")
        if shutil.disk_usage(self.root).free < self.policy["free_space_reserve_bytes"] + len(data):
            raise ImageUnavailable("image_free_space_reserve")
        target = self.root / "objects" / (digest + ".jpg")
        fd, name = tempfile.mkstemp(prefix=".image-", dir=self.root / "objects")
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, target)
            target.chmod(0o444)
            fsync_dir(target.parent)
        finally:
            Path(name).unlink(missing_ok=True)
        meta = {
            "gtin": gtin,
            "sha256": digest,
            "bytes": len(data),
            "width": width,
            "height": height,
            "source": "open_food_facts",
            "source_url": ref["url"],
            "product_url": "https://world.openfoodfacts.org/product/" + ref["code"],
            "license": LICENSE,
            "attribution": ATTRIBUTION,
            "kind": ref["kind"],
            "source_revision": ref["source_revision"],
            "reference_provenance": ref.get("reference_provenance", {"method": "api"}),
            "retrieved_at": self.clock(),
            "transformation": "EXIF orientation, maximum 600px, JPEG; metadata removed",
            "url": "/v1/product-images/" + gtin,
        }
        with _sqlite(self.root / "cache.sqlite") as db:
            db.execute("INSERT OR IGNORE INTO assets VALUES (?,?)", (digest, len(data)))
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?,0)", (gtin, "ready", json.dumps(meta))
            )
        return data, meta

    def get(self, barcode, *, fetch=True):
        gtin = normalize_gtin(barcode)
        if not gtin:
            raise ValueError("Invalid GTIN")
        self._check()
        result = self.cached(gtin)
        if result:
            return result
        if not fetch:
            raise ImageUnavailable("image_not_cached", missing=True)
        if not self.policy["network_enabled"]:
            raise ImageUnavailable("image_network_disabled")
        with self._network_lock():
            result = self.cached(gtin)
            if result:
                return result
            tried, errors = set(), []

            def attempt(refs):
                for ref in refs:
                    if ref["url"] in tried:
                        continue
                    tried.add(ref["url"])
                    provider = "aws" if ref["url"].startswith(AWS + "/") else "cdn"
                    try:
                        return self._store(gtin, self._read(ref["url"], provider), ref)
                    except ImageUnavailable as error:
                        if not error.missing:
                            errors.append(error)
                return None

            result = attempt(self.references(gtin))
            if result:
                return result
            if self.policy["api_fallback"]:
                try:
                    code = gtin.removeprefix("0")
                    url = API + "/api/v3.6/product/" + code + ".json?fields=code,images"
                    body = json.loads(self._read(url, "api"))
                    product = body.get("product")
                    if isinstance(product, dict):
                        refs = front_references(product, gtin)
                        if refs:
                            result = attempt(refs)
                            if result:
                                return result
                        elif normalize_gtin(product.get("code") or product.get("_id")) != gtin:
                            errors.append(ImageUnavailable("image_barcode_mismatch"))
                    elif body.get("status") not in (0, "failure") and not body.get("errors"):
                        errors.append(ImageUnavailable("invalid_image_api_response"))
                except ImageUnavailable as error:
                    if not error.missing:
                        errors.append(error)
                except (ValueError, TypeError, AttributeError):
                    errors.append(ImageUnavailable("invalid_image_api_response"))
            if errors:
                error = errors[-1]
                delay = (
                    error.retry_after
                    if error.reason in {"image_source_cooldown", "image_acquisition_busy"}
                    else max(self.policy["error_ttl_seconds"], error.retry_after)
                )
                self._record(gtin, "temporarily_unavailable", {}, self.clock() + delay)
                raise ImageUnavailable(error.reason, retry_after=delay)
            ttl = self.policy["negative_ttl_seconds"]
            self._record(gtin, "not_found", {}, self.clock() + ttl)
            raise ImageUnavailable("image_not_found", missing=True, retry_after=ttl)

    def status(self):
        if not (self.root / "cache.sqlite").exists():
            return {"enabled": self.policy["enabled"], "cached_images": 0, "bytes": 0}
        with _sqlite(self.root / "cache.sqlite") as db:
            return {
                "enabled": self.policy["enabled"],
                "api_fallback": self.policy["api_fallback"],
                "cached_images": db.execute(
                    "SELECT count(*) FROM cache WHERE state='ready'"
                ).fetchone()[0],
                "bytes": db.execute("SELECT coalesce(sum(bytes),0) FROM assets").fetchone()[0],
                "budgets": [
                    dict(zip(("provider", "day", "requests", "next_at"), row))
                    for row in db.execute("SELECT * FROM budgets")
                ],
            }
