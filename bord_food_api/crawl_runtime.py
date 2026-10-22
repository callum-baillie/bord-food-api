"""Explicitly activated map-link discovery; never downloads or rehosts map assets."""

import hashlib
import math
import random
import re
import time
from dataclasses import replace
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .crawl_cache import PageCache, retry_until
from .crawlers import CrawlBlocked, CrawlFrontier, CrawlPolicy
from .crawlers import map_links as discover_woodmans_maps
from .transport import RedirectNotice, Transport, TransportError, approved_url


def _positive(config, key, default, maximum):
    value = config.get(key, default)
    if type(value) is not int or value <= 0:
        raise CrawlBlocked("Crawl budgets must be positive integers")
    return min(value, maximum)


def validate_map_discovery(config):
    """Network-free activation checks, shared with operator CLI planning."""
    if (
        config.get("mode", "bulk_only") == "offline"
        or config.get("can_fetch", True) not in (True, "allow")
        or config.get("can_store_normalized", True) not in (True, "allow")
    ):
        raise CrawlBlocked("Crawling is disabled by effective network policy")
    gates = (
        "global_enabled",
        "adapter_enabled",
        "source_authorized",
        "robots_reviewed",
    )
    if not all(config.get(name) is True for name in gates) or not (
        config.get("terms_reviewed") is True or config.get("owner_public_robots_authorized") is True
    ):
        raise CrawlBlocked("Crawling is disabled or source review is incomplete")
    host = config.get("allowed_host", "")
    origin = f"https://{host}"
    approved_url(origin, [origin])
    spacing = config.get("min_spacing", 5)
    if type(spacing) not in (int, float) or not math.isfinite(spacing) or spacing < 0:
        raise CrawlBlocked("Invalid host request spacing")
    jitter = config.get("spacing_jitter_seconds", 0)
    if type(jitter) not in (int, float) or not math.isfinite(jitter) or not 0 <= jitter <= 300:
        raise CrawlBlocked("Invalid host request spacing jitter")
    policy = CrawlPolicy(
        global_enabled=True,
        adapter_enabled=True,
        source_authorized=True,
        terms_reviewed=config.get("terms_reviewed") is True,
        owner_public_robots_authorized=config.get("owner_public_robots_authorized") is True,
        robots_reviewed=True,
        contact=config.get("contact") or "",
        allowed_host=host,
        scope_prefix=config.get("scope_prefix", "/store-locations/"),
        max_pages_run=_positive(config, "max_pages_run", 50, 50),
        max_pages_day=_positive(config, "max_pages_day", 500, 500),
        max_bytes=_positive(config, "max_bytes", 2 * 1024**2, 2 * 1024**2),
        min_spacing=max(5, spacing),
        robots_allowed=lambda _url: True,
    )
    targets = config.get("approved_targets")
    if not isinstance(targets, list) or not targets or len(targets) > policy.max_pages_run:
        raise CrawlBlocked("A bounded list of approved branch targets is required")
    if config.get("allow_exact_target_queries") is True:
        # Query-bearing branch URLs must be individually operator-approved. This
        # does not authorize following query links or generating variants.
        policy = replace(
            policy,
            approved_query_urls=tuple(
                target["url"]
                for target in targets
                if isinstance(target, dict) and isinstance(target.get("url"), str)
            ),
        )
    seen = set()
    for target in targets:
        if not isinstance(target, dict) or not all(
            isinstance(target.get(key), str) and target[key].strip()
            for key in ("url", "store_id", "expected_branch")
        ):
            raise CrawlBlocked("Each approved target requires branch identity evidence")
        url = target["url"]
        approved_url(url, [origin])
        policy.authorize(url, 0)
        if url in seen or re.search(r"\.(?:pdf|svg|png|jpe?g|webp)(?:$|[?#])", url, re.IGNORECASE):
            raise CrawlBlocked("Targets must be distinct approved branch HTML pages")
        seen.add(url)
    return policy, targets


def run_map_discovery(
    platform,
    job,
    config,
    *,
    transport_factory=Transport,
    entity_kind="store",
    clock=time.time,
    sleep=time.sleep,
    random_uniform=random.uniform,
):
    """Fetch approved HTML only, after every independent gate, under a fenced job.

    ``config`` is operator-owned, never an API request body. ``_check`` can supply
    the worker's lease/policy callback. The default transport pins public DNS/IPs,
    refuses redirects and never forwards credentials. Robots failures fail closed.
    """
    if entity_kind not in {"store", "assistance_site", "osm_assistance_site"}:
        raise CrawlBlocked("Unsupported crawl entity kind")
    policy, targets = validate_map_discovery(config)  # No transport construction before gates.
    started = clock()
    run_seconds = _positive(config, "max_run_seconds", 300, 900)
    max_map_links = _positive(config, "max_map_links_per_page", 20, 100)

    def check():
        config.get("_check", lambda: None)()
        platform.control.check_fence(job)
        if not platform.control.enabled(job["source"]) or job[
            "source"
        ] in platform.control.hidden_sources("can_fetch"):
            raise CrawlBlocked("Crawl source is disabled by policy")
        if clock() - started > run_seconds:
            raise CrawlBlocked("Crawl run time budget exhausted")

    check()
    generation = (platform.current() or {}).get("generation")
    for target in targets:
        if platform.get(entity_kind, target["store_id"], generation=generation) is None:
            raise CrawlBlocked("Approved target references an unavailable catalog branch")
    origin = f"https://{policy.allowed_host}"
    robots_url = origin + "/robots.txt"
    aliases = config.get("robots_redirect_hosts", [])
    if not isinstance(aliases, list) or len(aliases) > 3:
        raise CrawlBlocked("Invalid reviewed robots redirect hosts")
    for host in aliases:
        approved_url("https://" + host + "/robots.txt", ["https://" + host])
    robots_urls = {robots_url, *("https://" + host + "/robots.txt" for host in aliases)}
    frontier = CrawlFrontier(
        platform.root / "control" / "crawl_frontier.sqlite", policy, clock=clock
    )
    with frontier.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS crawl_robots(
            host TEXT PRIMARY KEY, body TEXT NOT NULL, status INTEGER NOT NULL,
            expires REAL NOT NULL)""")
    cache_ttl = config.get("robots_ttl_seconds", 3600)
    if type(cache_ttl) is not int or cache_ttl < 0:
        raise CrawlBlocked("Robots cache lifetime must be a nonnegative integer")
    robots_cache = {"seconds": min(cache_ttl, 86400)}
    page_cache = PageCache(
        frontier,
        enabled=config.get("page_cache_enabled") is True
        and config.get("can_store_raw", True) in (True, "allow"),
    )
    targets_by_url = {t["url"]: t for t in targets}
    if config.get("can_store_raw", True) not in (True, "allow"):
        with frontier.connect() as db:
            db.executemany("DELETE FROM crawl_pages WHERE url=?", [(t["url"],) for t in targets])
    transport = transport_factory(
        {
            "mode": "bulk_only",
            "origins": [
                origin,
                *("https://" + host for host in aliases if host != policy.allowed_host),
            ],
            "max_redirects": 0,
            "report_redirects": config.get("report_redirects") is True or bool(aliases),
            "max_artifact_bytes": policy.max_bytes,
            "max_total_bytes": _positive(
                config,
                "max_total_bytes",
                policy.max_bytes * policy.max_pages_run,
                policy.max_bytes * policy.max_pages_run,
            ),
            "max_requests": policy.max_pages_run,
            "max_seconds": 60,
            "timeout": 30,
            "can_fetch": True,
            "_check": check,
        }
    )

    def fetch_bytes(url, *, max_bytes, max_redirects, user_agent):
        check()
        if max_redirects != 0:
            raise CrawlBlocked("Crawler redirects are not permitted")
        target = targets_by_url.get(url)
        cached = page_cache.load(target, max_bytes) if target else None
        headers = {"User-Agent": user_agent}
        if cached:
            if cached["etag"]:
                headers["If-None-Match"] = cached["etag"]
            elif cached["modified"]:
                headers["If-Modified-Since"] = cached["modified"]
        try:
            response = transport.get(url, headers=headers)
        except TransportError as error:
            if error.status in {429, 500, 502, 503, 504}:
                until = retry_until(
                    error.retry_after, clock(), fallback=3600 if error.status == 429 else 900
                )
                with frontier.connect() as db:
                    db.execute(
                        "INSERT INTO crawl_host_backoff VALUES(?,?,?) ON CONFLICT(host) DO UPDATE SET until=max(until,excluded.until),status=excluded.status",
                        (policy.allowed_host, until, error.status),
                    )
            raise
        with response:
            if getattr(response, "status", 200) == 304:
                if not cached:
                    raise CrawlBlocked("Unexpected crawl response status")
                if hasattr(response, "review_cached"):
                    response.review_cached(cached["body"])
                effective = {"ETag": cached["etag"], "Last-Modified": cached["modified"]}
                effective.update(dict(response.headers))
                page_cache.save(target, cached["body"], effective)
                return cached["body"]
            if getattr(response, "status", 200) != 200:
                raise CrawlBlocked("Unexpected crawl response status")
            media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            allowed = (
                ("text/plain",) if url in robots_urls else ("text/html", "application/xhtml+xml")
            )
            if media not in allowed:
                raise CrawlBlocked("Only robots text and approved branch HTML can be fetched")
            if url in robots_urls:
                controls = response.headers.get("Cache-Control", "").lower()
                if any(token in controls for token in ("no-store", "no-cache")):
                    robots_cache["seconds"] = 0
                match = re.search(r"(?:^|,)\s*max-age\s*=\s*\"?(\d+)", controls)
                if match:
                    robots_cache["seconds"] = min(robots_cache["seconds"], int(match[1]))
            maximum = min(max_bytes, 64 * 1024) if url in robots_urls else max_bytes
            body = bytearray()
            while chunk := response.read(min(65536, maximum + 1 - len(body))):
                check()
                body.extend(chunk)
                if len(body) > maximum:
                    raise CrawlBlocked("Crawl response byte limit exceeded")
            check()
            if target:
                page_cache.save(target, bytes(body), response.headers)
            return bytes(body)

    last_attempt = [None]

    def paced_fetch(url):
        # Draw once per request, never once per polling iteration. Add jitter to
        # the effective minimum, including any stricter robots directives.
        spacing = frontier.policy.min_spacing + random_uniform(
            0, config.get("spacing_jitter_seconds", 0)
        )
        while True:
            check()
            with frontier.connect() as db:
                row = db.execute(
                    "SELECT last_request FROM crawl_hosts WHERE host=?", (urlsplit(url).hostname,)
                ).fetchone()
            prior = max(
                [t for t in [row[0] if row else None, last_attempt[0]] if t is not None],
                default=None,
            )
            wait = spacing - (clock() - prior) if prior is not None else 0
            if wait <= 0:
                break
            sleep(min(wait, 1))
        check()
        try:
            return frontier.fetch(url, fetch_bytes)
        finally:
            last_attempt[0] = clock()

    with frontier.connect() as db:
        if config.get("can_store_raw", True) not in (True, "allow"):
            db.execute("DELETE FROM crawl_robots WHERE host=?", (policy.allowed_host,))
            cached = None
        else:
            cached = db.execute(
                "SELECT body,status,expires FROM crawl_robots WHERE host=?", (policy.allowed_host,)
            ).fetchone()
    if cached and cached[2] > clock():
        robots_body, status = cached[:2]
    else:
        frontier.policy = replace(
            policy, scope_prefix="/", robots_allowed=lambda url: url == robots_url
        )
        try:
            try:
                body = paced_fetch(robots_url)
            except RedirectNotice as notice:
                if notice.target not in robots_urls or notice.target == robots_url:
                    raise
                # Exactly one operator-reviewed robots destination. This never
                # authorizes a redirected branch request or forwards secrets.
                frontier.policy = replace(
                    policy,
                    allowed_host=urlsplit(notice.target).hostname,
                    scope_prefix="/",
                    robots_allowed=lambda url, destination=notice.target: url == destination,
                )
                body = paced_fetch(notice.target)
            robots_body = body.decode("utf-8")
            status = 200
        except TransportError as error:
            robots_body, status = "", error.status
        except UnicodeError:
            raise CrawlBlocked("Robots policy is not valid text") from None
        with frontier.connect() as db:
            if robots_cache["seconds"] and config.get("can_store_raw", True) in (True, "allow"):
                db.execute(
                    "INSERT OR REPLACE INTO crawl_robots VALUES (?,?,?,?)",
                    (policy.allowed_host, robots_body, status, clock() + robots_cache["seconds"]),
                )
            else:
                db.execute("DELETE FROM crawl_robots WHERE host=?", (policy.allowed_host,))
    if status != 200:
        raise CrawlBlocked("Robots policy is unavailable or denies discovery")
    parser = RobotFileParser(robots_url)
    parser.parse(robots_body.splitlines())
    agent = f"BordFoodCatalog/1.0 (+mailto:{policy.contact})"
    spacing = max(policy.min_spacing, parser.crawl_delay(agent) or 0)
    request_rate = parser.request_rate(agent)
    if request_rate and request_rate.requests:
        spacing = max(spacing, request_rate.seconds / request_rate.requests)
    frontier.policy = replace(
        policy, min_spacing=spacing, robots_allowed=lambda url: parser.can_fetch(agent, url)
    )
    for target in targets:
        frontier.policy.authorize(target["url"], 0)
    records = []
    visited = 0
    for target in targets:
        check()
        html = paced_fetch(target["url"]).decode("utf-8", errors="replace")
        check()
        # Reviewed transports finish their model gate before yielding EOF. This
        # optional sink keeps richer evidence separate from accepted map facts.
        if config.get("_evidence_sink"):
            config["_evidence_sink"](html, target)
            check()
        maps = discover_woodmans_maps(
            html,
            target["url"],
            expected_branch=target["expected_branch"],
            store_id=target["store_id"],
        )
        if len(maps) > max_map_links:
            raise CrawlBlocked("Map discovery candidate limit exceeded")
        if not maps:
            maps = [
                {
                    "source_url": None,
                    "branch_page": target["url"],
                    "store_id": target["store_id"],
                    "discovery_status": "not_found",
                    "rights_status": "pending",
                    "display_permitted": False,
                }
            ]
        for found in maps:
            key = hashlib.sha256(
                (target["url"] + "\0" + (found["source_url"] or "not_found")).encode()
            ).hexdigest()
            records.append(
                {
                    "kind": "map",
                    "source_key": key,
                    "payload": {
                        **found,
                        "storage_permitted": False,
                        "assets": {},
                        "rights_policy_id": config.get("rights_policy_id"),
                        "source_observed_at": None,
                        "last_checked_at": clock(),
                        "intended_store_id": target["store_id"],
                    },
                }
            )
        visited += 1
    check()
    if config.get("_fields_only") is True:
        # Field campaigns retain map candidates for review, without publishing
        # map records through the separate map acceptance workflow.
        return {"pages": visited, "map_records": 0, "changed": 0}
    release = hashlib.sha256(
        str([(r["source_key"], r["payload"]) for r in records]).encode()
    ).hexdigest()
    result = platform.sync(
        job["source"],
        job.get("partition", "approved_targets"),
        release,
        records,
        complete=False,
        parser_version="woodmans-map-links-v1",
        cursor={"target_count": visited},
        fence=job,
    )
    return {**result, "pages": visited, "map_records": len(records)}
