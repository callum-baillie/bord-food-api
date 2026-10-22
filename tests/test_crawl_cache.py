import sqlite3

import pytest

from bord_food_api.crawl_cache import PageCache, retry_until
from bord_food_api.crawlers import CrawlBlocked, CrawlFrontier, CrawlPolicy


def test_cache_is_bound_to_identity_validators_rights_and_size(tmp_path):
    f = CrawlFrontier(tmp_path / "frontier.sqlite", CrawlPolicy(), clock=lambda: 1000)
    c = PageCache(f, enabled=True)
    t = {
        "store_id": "one",
        "url": "https://fixture.test/stores/one",
        "source_address": {"street": "1 Main St"},
    }
    c.save(t, b"branch", {"ETag": '"v1"'})
    assert c.load(t, 100)["body"] == b"branch"
    assert c.load({**t, "store_id": "two"}, 100) is None
    assert c.load(t, 3) is None
    with sqlite3.connect(f.database) as db:
        db.execute("UPDATE crawl_pages SET sha256=?", ("corrupt",))
    assert c.load(t, 100) is None
    for headers in [
        {"Cache-Control": "no-store", "ETag": "v2"},
        {"cache-control": "no-store", "etag": "v2"},
        {"Vary": "Cookie", "ETag": "v2"},
        {"ETag": "bad\nheader"},
    ]:
        c.save(t, b"branch", headers)
        assert c.load(t, 100) is None


def test_retry_after_and_shared_backoff_prevent_any_transport_attempt(tmp_path):
    assert retry_until("7200", 1000) == 8200
    assert retry_until("Thu, 01 Jan 1970 04:00:00 GMT", 1000) == 14400
    assert retry_until("untrusted", 1000) == 4600
    policy = CrawlPolicy(
        global_enabled=True,
        adapter_enabled=True,
        source_authorized=True,
        terms_reviewed=True,
        robots_reviewed=True,
        contact="ops@fixture.org",
        allowed_host="fixture.test",
        robots_allowed=lambda _: True,
        scope_prefix="/",
    )
    f = CrawlFrontier(tmp_path / "frontier.sqlite", policy, clock=lambda: 1000)
    with sqlite3.connect(f.database) as db:
        db.execute("INSERT INTO crawl_host_backoff VALUES(?,?,?)", ("fixture.test", 8200, 429))
    with pytest.raises(CrawlBlocked, match="backoff"):
        f.fetch(
            "https://fixture.test/one",
            lambda *_args, **_kwargs: pytest.fail("backoff must precede transport"),
        )
