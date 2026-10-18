"""Synthetic worker transports only; no source DNS or retailer requests."""

import io
import time

import pytest

from bord_food_api.crawl_runtime import run_map_discovery
from bord_food_api.crawlers import CrawlBlocked
from bord_food_api.platform import Platform
from bord_food_api.transport import TransportError


@pytest.fixture
def pilot(tmp_path):
    platform = Platform(tmp_path)
    platform.sync(
        "fixture",
        "stores",
        "1",
        [{"kind": "store", "source_key": "north", "payload": {"name": "Imaginary North Branch"}}],
    )
    store = platform.records("store")[0]
    platform.control.enqueue("woodmans_maps", "approved_targets", operation="discover_map")
    job = platform.control.claim("synthetic_worker", ttl=600)
    config = {
        "global_enabled": True,
        "adapter_enabled": True,
        "source_authorized": True,
        "terms_reviewed": True,
        "robots_reviewed": True,
        "contact": "ops@bord.org",
        "allowed_host": "retailer.test",
        "scope_prefix": "/store-locations/",
        "approved_targets": [
            {
                "url": "https://retailer.test/store-locations/north/",
                "store_id": store["id"],
                "expected_branch": store["name"],
            }
        ],
    }
    now = [time.time()]

    def sleep(seconds):
        now[0] += seconds

    return platform, job, config, lambda: now[0], sleep


class Response(io.BytesIO):
    def __init__(self, body, media="text/html", headers=None):
        super().__init__(body)
        self.status = 200
        self.headers = {"Content-Type": media, **(headers or {})}


class MockTransport:
    def __init__(
        self,
        policy,
        calls,
        *,
        robots=b"User-agent: *\nAllow: /\n",
        status=200,
        branch=b'<h1>Imaginary North Branch</h1><a href="/maps/north.pdf">Store Map (PDF)</a>'
        b'<a href="/weekly.pdf">Weekly Ad PDF</a><a href="/geo">Geographic Map</a>',
    ):
        self.policy, self.calls = policy, calls
        self.robots, self.robots_status, self.branch = robots, status, branch

    def get(self, url, headers=None):
        self.policy["_check"]()
        self.calls.append(url)
        assert headers["User-Agent"].startswith("BordFoodCatalog/1.0 (+mailto:ops@bord.org)")
        assert self.policy["max_redirects"] == 0
        assert self.policy["max_artifact_bytes"] <= 2 * 1024**2
        assert self.policy["origins"] == ["https://retailer.test"]
        if url.endswith("/robots.txt"):
            if self.robots_status != 200:
                raise TransportError(self.robots_status)
            return Response(self.robots, "text/plain")
        return Response(self.branch)


def run(pilot, factory):
    platform, job, config, clock, sleep = pilot
    return run_map_discovery(
        platform, job, config, transport_factory=factory, clock=clock, sleep=sleep
    )


@pytest.mark.parametrize(
    "gate",
    ["global_enabled", "adapter_enabled", "source_authorized", "terms_reviewed", "robots_reviewed"],
)
def test_disabled_gates_never_construct_transport_even_with_job(pilot, gate):
    platform, _, config, _, _ = pilot
    config[gate] = False
    factories = []
    with pytest.raises(CrawlBlocked):
        run(pilot, lambda policy: factories.append(policy))
    assert factories == [] and platform.records("map") == []


def test_operator_target_contact_scope_and_known_branch_gate_before_transport(pilot):
    _, _, config, _, _ = pilot
    factories = []

    def factory(policy):
        factories.append(policy)

    for update in (
        {"contact": "placeholder@example.com"},
        {"mode": "offline"},
        {"approved_targets": []},
        {"allowed_host": "127.0.0.1"},
    ):
        original = dict(config)
        config.update(update)
        with pytest.raises(ValueError):
            run(pilot, factory)
        config.clear()
        config.update(original)
    config["approved_targets"][0]["store_id"] = "nonexistent"
    with pytest.raises(CrawlBlocked, match="unavailable catalog branch"):
        run(pilot, factory)
    assert factories == []


def test_fenced_discovery_only_requests_robots_and_html_stable_id_and_cached_robots(pilot):
    platform, _, _, _, _ = pilot
    calls = []
    result = run(pilot, lambda policy: MockTransport(policy, calls))
    assert result["pages"] == 1 and result["map_records"] == 1
    maps = platform.records("map")
    assert len(maps) == 1
    assert maps[0]["source_url"] == "https://retailer.test/maps/north.pdf"
    assert maps[0]["discovery_status"] == "discovered" and maps[0]["rights_status"] == "pending"
    assert maps[0]["assets"] == {} and not maps[0]["display_permitted"]
    assert not maps[0]["storage_permitted"] and not (platform.root / "objects/media").exists()
    assert calls == [
        "https://retailer.test/robots.txt",
        "https://retailer.test/store-locations/north/",
    ]
    run(pilot, lambda policy: MockTransport(policy, calls))
    assert len(platform.records("map")) == 1 and platform.records("map")[0]["id"] == maps[0]["id"]
    assert calls.count("https://retailer.test/robots.txt") == 1
    assert not any(url.endswith(".pdf") for url in calls)


@pytest.mark.parametrize("status,body", [(403, b""), (200, b"User-agent: *\nDisallow: /\n")])
def test_robots_denial_never_fetches_branch_or_publishes(pilot, status, body):
    platform, _, _, _, _ = pilot
    calls = []
    with pytest.raises(CrawlBlocked):
        run(pilot, lambda policy: MockTransport(policy, calls, robots=body, status=status))
    assert calls == ["https://retailer.test/robots.txt"]
    assert platform.records("map") == []


def test_pause_or_expired_fence_blocks_before_transport_and_during_html(pilot):
    platform, job, config, _, _ = pilot
    calls = []
    platform.control.set_source(job["source"], False)
    with pytest.raises((CrawlBlocked, ValueError)):
        run(pilot, lambda policy: calls.append(policy))
    assert calls == []
    platform.control.set_source(job["source"], True)
    checks = [0]

    def revoke_during_read():
        checks[0] += 1
        if checks[0] > 15:
            platform.control.set_source(job["source"], False)

    config["_check"] = revoke_during_read
    with pytest.raises((CrawlBlocked, ValueError)):
        run(pilot, lambda policy: MockTransport(policy, calls))
    assert platform.records("map") == []


def test_non_html_branch_response_never_reads_asset_bytes(pilot):
    calls = []

    class RejectAsset(MockTransport):
        def get(self, url, headers=None):
            if url.endswith("/robots.txt"):
                return super().get(url, headers)
            calls.append(url)

            class Asset(Response):
                def read(self, *args):
                    raise AssertionError("Map asset bytes must never be read")

            return Asset(b"%PDF synthetic", "application/pdf")

    with pytest.raises(CrawlBlocked, match="Only robots text"):
        run(pilot, lambda policy: RejectAsset(policy, calls))
    assert pilot[0].records("map") == []


@pytest.mark.parametrize("directive", ["no-store", "no-cache", "max-age=1"])
def test_robots_cache_never_outlives_http_permission(pilot, directive):
    platform, _, _, _, _ = pilot
    calls = []

    class CacheTransport(MockTransport):
        def get(self, url, headers=None):
            response = super().get(url, headers)
            if url.endswith("/robots.txt"):
                response.headers["Cache-Control"] = directive
            return response

    run(pilot, lambda policy: CacheTransport(policy, calls))
    run(pilot, lambda policy: CacheTransport(policy, calls))
    assert calls.count("https://retailer.test/robots.txt") == 2
    if directive in ("no-store", "no-cache"):
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(platform.root / "control/crawl_frontier.sqlite")) as db:
            assert db.execute("SELECT count(*) FROM crawl_robots").fetchone()[0] == 0


def test_request_and_candidate_budgets_preserve_previous_publication(pilot):
    platform, _, config, _, _ = pilot
    before = platform.current()
    calls = []
    config["max_pages_run"] = 1  # Robots consumes this run's only available request.
    with pytest.raises(CrawlBlocked, match="budget"):
        run(pilot, lambda policy: MockTransport(policy, calls))
    assert calls == ["https://retailer.test/robots.txt"]
    assert platform.current() == before
    config["max_pages_run"] = 50
    config["max_map_links_per_page"] = 1
    branch = (
        b"<h1>Imaginary North Branch</h1>"
        b'<a href="/one.pdf">Store Map PDF</a><a href="/two.pdf">Floor Map PDF</a>'
    )
    with pytest.raises(CrawlBlocked, match="candidate limit"):
        run(pilot, lambda policy: MockTransport(policy, calls, branch=branch))
    assert platform.current() == before
