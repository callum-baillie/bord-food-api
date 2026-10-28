"""Synthetic/mocked image acquisition: no live image or API request in routine tests."""

import fcntl
import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from bord_food_api.api import create_app
from bord_food_api.platform import Platform
from bord_food_api.product_images import (
    AWS,
    ImageCache,
    ImageUnavailable,
    front_references,
    image_policy,
)
from bord_food_api.settings import Settings, load_policy
from bord_food_api.transport import TransportError

CODE = "012345678905"
GTIN = "00012345678905"
OTHER = "00000000000000"


def product(code=CODE, modified=1):
    return {
        "code": code,
        "last_modified_t": modified,
        "images": {
            "uploaded": {"1": {"sizes": {"400": {"w": 400, "h": 300}}}},
            "selected": {"front": {"en": {"imgid": "1", "rev": "3"}}},
        },
    }


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (100, 80), "red").save(out, "JPEG")
    return out.getvalue()


def config(**overrides):
    return image_policy(
        {
            "network": {"mode": "bulk_only"},
            "product_images": {
                "enabled": True,
                "api_fallback": True,
                "free_space_reserve_bytes": 0,
                **overrides,
            },
        }
    )


def test_only_selected_front_images_and_strict_barcode_match():
    refs = front_references(product(), GTIN)
    assert refs[0]["url"] == AWS + "/data/012/345/678/905/1.400.jpg"
    assert all(r["gtin"] == GTIN for r in refs)
    assert front_references(product(), OTHER) == []
    assert front_references({"code": CODE, "images": {"uploaded": {"1": {}}}}) == []
    assert front_references({"code": "../private", "images": product()["images"]}) == []
    bad = product()
    bad["images"]["selected"]["front"]["en"]["imgid"] = "../../private"
    assert front_references(bad) == []
    legacy = {"code": CODE, "images": {"front_en": {"imgid": "1", "rev": "3"}}}
    assert front_references(legacy) == refs


def test_bulk_index_then_local_cache_hit_has_no_network_and_keeps_catalog(tmp_path):
    platform = Platform(tmp_path)
    platform.sync(
        "fixture", "all", "1", [{"kind": "product", "source_key": "one", "payload": {"gtin": GTIN}}]
    )
    pointer = (tmp_path / "current.json").read_bytes()
    calls = []
    cache = ImageCache(
        tmp_path, config(api_fallback=False), fetcher=lambda u, p: calls.append((u, p)) or jpeg()
    )
    assert cache.import_references([product()])["barcodes_with_front_references"] == 1
    data, meta = cache.get(CODE)
    assert meta["license"].endswith("/by-sa/3.0/") and meta["attribution"]
    assert hashlib.sha256(data).hexdigest() == meta["sha256"]
    assert len(calls) == 1 and calls[0][1] == "aws"
    cache.policy["network_enabled"] = False
    assert cache.get(GTIN)[0] == data
    assert len(calls) == 1
    assert (tmp_path / "current.json").read_bytes() == pointer
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG" and image.size == (100, 80)
        assert not image.getexif()


def test_api_only_on_cache_miss_and_rechecks_barcode(tmp_path):
    calls = []

    def fetch(url, provider):
        calls.append((url, provider))
        return (
            json.dumps({"status": "success", "product": product()}).encode()
            if provider == "api"
            else jpeg()
        )

    cache = ImageCache(tmp_path, config(), fetcher=fetch)
    data, meta = cache.get(CODE)
    assert [x[1] for x in calls] == ["api", "aws"]
    assert cache.get(GTIN)[0] == data and len(calls) == 2
    assert meta["source"] == "open_food_facts"
    cache = ImageCache(
        tmp_path / "wrong",
        config(),
        fetcher=lambda u, p: json.dumps({"product": product(OTHER)}).encode(),
    )
    with pytest.raises(ImageUnavailable, match="image_barcode_mismatch"):
        cache.get(CODE)
    assert cache.status()["cached_images"] == 0


def test_missing_and_transient_results_have_distinct_durable_cooldowns(tmp_path):
    calls = []
    now = [10000.0]

    def missing(url, provider):
        calls.append(url)
        raise TransportError(404)

    cache = ImageCache(
        tmp_path, config(negative_ttl_seconds=60), clock=lambda: now[0], fetcher=missing
    )
    for _ in range(2):
        with pytest.raises(ImageUnavailable) as error:
            cache.get(CODE)
        assert error.value.missing
    assert len(calls) == 1
    now[0] += 61
    with pytest.raises(ImageUnavailable):
        cache.get(CODE)
    assert len(calls) == 2
    calls.clear()

    def busy(url, provider):
        calls.append(url)
        raise TransportError(503, "120")

    cache = ImageCache(tmp_path / "transient", config(), clock=lambda: now[0], fetcher=busy)
    with pytest.raises(ImageUnavailable) as error:
        cache.get(CODE)
    assert not error.value.missing and error.value.retry_after >= 120
    with pytest.raises(ImageUnavailable):
        cache.get(OTHER)
    assert len(calls) == 1  # Shared provider cooldown also protects another barcode.


def test_new_bulk_reference_invalidates_old_negative_result(tmp_path):
    now = [10000.0]
    cache = ImageCache(
        tmp_path, config(api_fallback=False), clock=lambda: now[0], fetcher=lambda u, p: jpeg()
    )
    with pytest.raises(ImageUnavailable) as error:
        cache.get(CODE)
    assert error.value.missing
    cache.import_references([product()])
    assert cache.get(CODE)[1]["gtin"] == GTIN


def test_bad_reference_import_does_not_replace_previous_index(tmp_path):
    cache = ImageCache(tmp_path, config())
    cache.import_references([product()])
    before = (cache.root / "references.sqlite").read_bytes()
    bad = product()
    bad["last_modified_t"] = "bad"
    with pytest.raises(ValueError):
        cache.import_references([bad])
    assert (cache.root / "references.sqlite").read_bytes() == before
    cache.import_references([product(), product(modified=2), product()])
    assert len(cache.references(GTIN)) == 2


def test_invalid_image_and_quota_never_publish_an_asset(tmp_path):
    cache = ImageCache(
        tmp_path, config(api_fallback=False), fetcher=lambda u, p: b"<html>not an image</html>"
    )
    cache.import_references([product()])
    with pytest.raises(ImageUnavailable):
        cache.get(CODE)
    assert cache.status()["cached_images"] == 0
    assert list((cache.root / "objects").glob("*.jpg")) == []
    cache = ImageCache(
        tmp_path / "quota",
        config(cache_quota_bytes=1024, api_fallback=False),
        fetcher=lambda u, p: jpeg(),
    )
    cache.import_references([product()])
    # Orphaned files count toward the physical disk quota after an interrupted write.
    (cache.root / "objects" / "orphan.jpg").write_bytes(b"x" * 1024)
    with pytest.raises(ImageUnavailable):
        cache.get(CODE)
    assert cache.status()["cached_images"] == 0


def test_source_revocation_and_disabled_network_keep_cache_rules(tmp_path):
    denied = set()
    calls = []
    cache = ImageCache(
        tmp_path,
        config(api_fallback=False),
        denied=lambda: denied,
        fetcher=lambda u, p: calls.append(u) or jpeg(),
    )
    cache.import_references([product()])
    cache.get(CODE)
    denied.add("open_food_facts")
    with pytest.raises(ImageUnavailable, match="rights_blocked"):
        cache.get(CODE)
    assert len(calls) == 1
    denied.clear()
    cache.policy["enabled"] = False
    with pytest.raises(ImageUnavailable, match="disabled"):
        cache.get(CODE)
    cache.policy["enabled"] = True
    cache.policy["network_enabled"] = False
    assert cache.get(CODE)[0]
    with pytest.raises(ImageUnavailable, match="network_disabled"):
        cache.get(OTHER)


def test_concurrent_miss_is_bounded_and_corrupt_file_is_not_served(tmp_path):
    cache = ImageCache(tmp_path, config(api_fallback=False), fetcher=lambda u, p: jpeg())
    cache.import_references([product()])
    with (cache.root / "acquisition.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ImageUnavailable, match="busy"):
            cache.get(CODE)
    _, meta = cache.get(CODE)
    path = cache.root / "objects" / (meta["sha256"] + ".jpg")
    path.chmod(0o644)
    path.write_bytes(b"corrupt")
    cache.policy["network_enabled"] = False
    with pytest.raises(ImageUnavailable):
        cache.get(CODE)


def test_authenticated_http_image_and_metadata_and_etag(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "product_images": {
                    "enabled": True,
                    "api_fallback": False,
                    "free_space_reserve_bytes": 0,
                }
            }
        )
    )
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(policy))
    cache = ImageCache(tmp_path, config(api_fallback=False), fetcher=lambda u, p: jpeg())
    cache.import_references([product()])
    cache.get(CODE)
    client = TestClient(create_app(Settings(data_dir=tmp_path, api_key="private-test-key")))
    assert client.get("/v1/product-images/" + CODE).status_code == 401
    client.headers["X-Api-Key"] = "private-test-key"
    response = client.get("/v1/product-images/" + CODE)
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "license" in response.headers["link"]
    assert (
        client.get(
            "/v1/product-images/" + CODE, headers={"If-None-Match": response.headers["etag"]}
        ).status_code
        == 304
    )
    meta = client.get("/v1/product-images/" + CODE + "/metadata").json()
    assert meta["gtin"] == GTIN and "private-test-key" not in json.dumps(meta)
    assert client.get("/v1/product-images/1234").status_code == 422
    assert client.get("/v1/product-images/status").json()["cached_images"] == 1


def test_image_policy_validation_and_offline_cache_mode():
    assert not load_policy(Settings())["product_images"]["enabled"]
    for options in [
        {"api_fallback": "yes"},
        {"max_asset_bytes": 10**10},
        {"user_agent": "unsafe\r\nheader"},
    ]:
        with pytest.raises(ValueError):
            config(**options)
    assert not image_policy({"network": {"mode": "offline"}, "product_images": {"enabled": True}})[
        "network_enabled"
    ]
