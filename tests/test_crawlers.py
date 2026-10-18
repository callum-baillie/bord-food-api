from dataclasses import replace

import pytest

from bord_food_api.crawlers import (
    CrawlBlocked,
    CrawlFrontier,
    CrawlPolicy,
    invalidate_anchors,
    map_links,
    safe_link,
    sitemap_links,
    structured_store,
)


def test_disabled_frontier_cannot_request_even_accidental_job(tmp_path):
    frontier = CrawlFrontier(tmp_path / "crawler.sqlite", CrawlPolicy())
    calls = []
    with pytest.raises(CrawlBlocked, match="disabled"):
        frontier.fetch("https://retailer.test/stores/a", lambda *a, **k: calls.append(a))
    assert calls == []


def enabled():
    return CrawlPolicy(
        global_enabled=True,
        adapter_enabled=True,
        source_authorized=True,
        terms_reviewed=True,
        robots_reviewed=True,
        contact="ops@bord.org",
        allowed_host="retailer.test",
        scope_prefix="/stores/",
        robots_allowed=lambda url: True,
    )


def test_robots_spacing_daily_run_budget_and_dedup(tmp_path):
    now = [1000]
    policy = replace(enabled(), max_pages_run=2, max_pages_day=2)
    frontier = CrawlFrontier(tmp_path / "crawler.sqlite", policy, clock=lambda: now[0])
    assert frontier.enqueue("https://retailer.test/stores/", ["a", "a", "/cart", "b"]) == 2
    calls = []

    def transport(url, **kwargs):
        calls.append(kwargs)
        return b"fixture"

    assert frontier.fetch("https://retailer.test/stores/a", transport) == b"fixture"
    with pytest.raises(CrawlBlocked, match="spacing"):
        frontier.fetch("https://retailer.test/stores/b", transport)
    now[0] += 5
    frontier.fetch("https://retailer.test/stores/b", transport)
    now[0] += 5
    with pytest.raises(CrawlBlocked, match="budget"):
        frontier.fetch("https://retailer.test/stores/c", transport)
    assert calls[0]["max_redirects"] == 0
    frontier.policy = replace(policy, robots_allowed=lambda url: False)
    with pytest.raises(CrawlBlocked, match="Robots"):
        frontier.fetch("https://retailer.test/stores/a", transport)


def test_url_scope_and_sitemap_xml_entities():
    for target in (
        "http://retailer.test/a",
        "https://127.0.0.1/a",
        "https://user:pass@retailer.test/a",
        "/stores/a?token=secret",
        "https://metadata.google.internal/a",
        "//other.test/a",
    ):
        with pytest.raises(CrawlBlocked):
            safe_link("https://retailer.test/", target)
    assert sitemap_links(
        b"<urlset><url><loc>https://retailer.test/stores/a</loc></url>"
        b"<url><loc>https://retailer.test/stores/a</loc></url></urlset>",
        "https://retailer.test/",
    ) == ["https://retailer.test/stores/a"]
    with pytest.raises(CrawlBlocked):
        sitemap_links(
            b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>',
            "https://retailer.test/",
        )


def test_synthetic_map_roles_branch_association_and_unknown_rights():
    html = """<h1>Imaginary North Branch</h1>
    <a href="/stores/north/map.pdf">Store Map (PDF)</a>
    <a href="https://geography.test/">Geographic Map</a>
    <a href="/stores/north/ad.pdf">Weekly Ad PDF</a>"""
    maps = map_links(
        html,
        "https://retailer.test/stores/north/",
        expected_branch="Imaginary North Branch",
        store_id="s_north",
    )
    assert len(maps) == 1
    assert maps[0]["source_url"].endswith("/map.pdf")
    assert maps[0]["rights_status"] == "pending"
    assert not maps[0]["layout_validated"] and not maps[0]["display_permitted"]
    ambiguous = map_links(
        html,
        "https://retailer.test/stores/north/",
        expected_branch="Other Branch",
        store_id="s_other",
    )
    assert ambiguous[0]["store_id"] is None
    assert ambiguous[0]["discovery_status"] == "ambiguous"


def test_structured_branch_details_and_anchor_invalidation():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"GroceryStore",
    "name":"Imaginary North Branch","hasMap":"https://geo.test/map",
    "address":{"streetAddress":"12 Fixture Street"}}]}</script>"""
    parsed = structured_store(html, expected_branch="12 Fixture Street")
    assert len(parsed) == 1 and "hasMap" not in parsed[0]
    assert structured_store(html, expected_branch="different address") == []
    old = {"map_id": "m", "map_version": "old", "coordinates": [1, 2]}
    assert invalidate_anchors([old], "m", "new")[0]["coordinates"] is None
    assert old["coordinates"] == [1, 2]


def test_frontier_closes_connections_after_success_and_failure(tmp_path, monkeypatch):
    import sqlite3
    from types import SimpleNamespace

    from bord_food_api import crawlers

    connections = []

    def tracked_connect(*args, **kwargs):
        connection = sqlite3.connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(crawlers, "sqlite3", SimpleNamespace(connect=tracked_connect))
    frontier = CrawlFrontier(tmp_path / "crawler.sqlite", enabled())
    assert frontier.enqueue("https://retailer.test/stores/", ["a"]) == 1
    with pytest.raises(RuntimeError, match="synthetic failure"), frontier.connect() as connection:
        connection.execute("INSERT INTO crawl_frontier(url,depth) VALUES ('fixture',0)")
        raise RuntimeError("synthetic failure")
    assert len(connections) == 3
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
