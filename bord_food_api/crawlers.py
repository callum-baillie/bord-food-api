"""Disabled-by-default bounded retailer extraction, with no built-in network client.

Workers must call CrawlFrontier.fetch immediately before each transport request.
Synthetic documents can be parsed without activating any source.
"""

import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit


class CrawlBlocked(ValueError):
    pass


def safe_link(base, target, *, allow_query=False):
    url = urlsplit(urljoin(base, target))
    origin = urlsplit(base)
    if (
        url.scheme != "https"
        or url.hostname != origin.hostname
        or url.username
        or url.password
        or url.port not in (None, 443)
        or (url.query and not allow_query)
    ):
        raise CrawlBlocked("URL is outside approved same-host scope")
    if re.search(r"/(?:account|cart|checkout|search|login)(?:/|$)", url.path, re.IGNORECASE):
        raise CrawlBlocked("URL is outside store discovery scope")
    return urlunsplit((url.scheme, url.netloc, url.path, url.query if allow_query else "", ""))


@dataclass(frozen=True)
class CrawlPolicy:
    global_enabled: bool = False
    adapter_enabled: bool = False
    source_authorized: bool = False
    terms_reviewed: bool = False
    robots_reviewed: bool = False
    contact: str = ""
    allowed_host: str = ""
    scope_prefix: str = "/"
    max_pages_run: int = 50
    max_pages_day: int = 500
    max_bytes: int = 2 * 1024 * 1024
    min_spacing: float = 5
    max_depth: int = 2
    approved_query_urls: tuple[str, ...] = ()
    owner_public_robots_authorized: bool = False
    robots_allowed: object = field(default=lambda url: False, repr=False)

    def authorize(self, url, depth):
        if not all(
            (
                self.global_enabled,
                self.adapter_enabled,
                self.source_authorized,
                self.terms_reviewed or self.owner_public_robots_authorized,
                self.robots_reviewed,
            )
        ):
            raise CrawlBlocked("Crawling is disabled or source review is incomplete")
        if "@" not in self.contact or any(
            word in self.contact.lower()
            for word in ("example.", "placeholder", "changeme", ".test")
        ):
            raise CrawlBlocked("An identifying operator contact is required")
        parsed = urlsplit(url)
        if (
            not self.allowed_host
            or parsed.hostname != self.allowed_host
            or not parsed.path.startswith(self.scope_prefix)
            or depth > self.max_depth
        ):
            raise CrawlBlocked("Crawl target is outside approved scope")
        safe_link(f"https://{self.allowed_host}/", url, allow_query=url in self.approved_query_urls)
        if not self.robots_allowed(url):
            raise CrawlBlocked("Robots policy does not permit this request")


class CrawlFrontier:
    """Durable URL deduplication and per-host budgets; transport rechecks each redirect.

    Inject the same central safe transport used by bulk acquisition; the transport
    must reject private/rebound addresses and check redirect targets. Redirects are
    disabled here so each redirect needs a new explicit authorization.
    """

    def __init__(self, database: Path, policy: CrawlPolicy, clock=time.time):
        self.database, self.policy, self.clock = database, policy, clock
        self.pages_run = 0
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS crawl_frontier (
                    url TEXT PRIMARY KEY, depth INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', content_hash TEXT);
                CREATE TABLE IF NOT EXISTS crawl_hosts (
                    host TEXT PRIMARY KEY, day INTEGER NOT NULL,
                    requests INTEGER NOT NULL, last_request REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def enqueue(self, base, links, depth=0):
        count = 0
        with self.connect() as connection:
            for target in links:
                try:
                    url = safe_link(base, target)
                    self.policy.authorize(url, depth)
                except CrawlBlocked:
                    continue
                result = connection.execute(
                    "INSERT OR IGNORE INTO crawl_frontier(url,depth) VALUES (?,?)", (url, depth)
                )
                count += result.rowcount
        return count

    def fetch(self, url, transport, depth=0):
        self.policy.authorize(url, depth)  # kill switch enforced at request time
        now = self.clock()
        host = urlsplit(url).hostname
        day = int(now // 86400)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT day,requests,last_request FROM crawl_hosts WHERE host=?", (host,)
            ).fetchone()
            daily = row[1] if row and row[0] == day else 0
            if self.pages_run >= self.policy.max_pages_run or daily >= self.policy.max_pages_day:
                raise CrawlBlocked("Crawl request budget exhausted")
            if row and now - row[2] < max(5, self.policy.min_spacing):
                raise CrawlBlocked("Crawl host spacing/backoff is active")
            connection.execute(
                "INSERT OR REPLACE INTO crawl_hosts VALUES (?,?,?,?)", (host, day, daily + 1, now)
            )
        self.pages_run += 1
        body = transport(
            url,
            max_bytes=min(self.policy.max_bytes, 2 * 1024 * 1024),
            max_redirects=0,
            user_agent=f"BordFoodCatalog/1.0 (+mailto:{self.policy.contact})",
        )
        if len(body) > self.policy.max_bytes:
            raise CrawlBlocked("Crawl response byte limit exceeded")
        with self.connect() as connection:
            connection.execute("UPDATE crawl_frontier SET status='fetched' WHERE url=?", (url,))
        return body


def sitemap_links(document: bytes, base: str, max_urls=10000, max_bytes=2 * 1024 * 1024):
    if (
        len(document) > max_bytes
        or b"<!DOCTYPE" in document.upper()
        or b"<!ENTITY" in document.upper()
    ):
        raise CrawlBlocked("Unsafe or oversized sitemap")
    root = ET.fromstring(document)
    result = []
    seen = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text:
            try:
                value = safe_link(base, node.text.strip())
            except CrawlBlocked:
                continue
            if value not in seen:
                result.append(value)
                seen.add(value)
            if len(result) > max_urls:
                raise CrawlBlocked("Sitemap URL budget exceeded")
    return result


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.scripts, self.anchor, self.script = [], [], None, None
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.anchor = {"href": attrs.get("href", ""), "text": ""}
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.script = ""

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor["text"] += data
        if self.script is not None:
            self.script += data
        else:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.links.append(self.anchor)
            self.anchor = None
        if tag == "script" and self.script is not None:
            self.scripts.append(self.script)
            self.script = None


def parse_page(html):
    if len(html.encode()) > 2 * 1024 * 1024:
        raise CrawlBlocked("HTML byte limit exceeded")
    parser = PageParser()
    parser.feed(html)
    return parser


def map_links(html, branch_url, *, expected_branch, store_id=None):
    """Discover official floorplan links, without downloading assets or granting rights."""
    parser = parse_page(html)
    page_text = " ".join(parser.text).casefold()
    branch_matches = bool(expected_branch and expected_branch.casefold() in page_text)
    candidates = []
    for link in parser.links:
        text = " ".join(link["text"].split())
        role = text.casefold()
        if not re.search(r"(?:store|floor|layout)\s*(?:map|plan)", role) or any(
            word in role for word in ("weekly", "coupon", "directions", "geographic", "ad ")
        ):
            continue
        try:
            url = safe_link(branch_url, link["href"])
        except CrawlBlocked:
            continue
        candidates.append(
            {
                "source_url": url,
                "anchor_text": text,
                "branch_page": branch_url,
                "media_type_hint": "application/pdf"
                if urlsplit(url).path.lower().endswith(".pdf")
                else None,
                "store_id": store_id if branch_matches else None,
                "discovery_status": "discovered" if branch_matches else "ambiguous",
                "rights_status": "pending",
                "display_permitted": False,
                "observed_map_date": None,
                "version": None,
                "layout_validated": False,
            }
        )
    if len(candidates) > 1:
        for candidate in candidates:
            candidate["discovery_status"] = "ambiguous"
    return candidates


def structured_store(html, *, expected_branch):
    """Only explicit Schema.org facts, matched to intended branch; hasMap stays geographic."""
    parser = parse_page(html)
    if not expected_branch.strip():
        raise CrawlBlocked("Branch association evidence is required")
    result = []
    for script in parser.scripts:
        try:
            data = json.loads(script)
        except (ValueError, TypeError):
            continue
        pending = list(data) if isinstance(data, list) else [data]
        while pending:
            row = pending.pop()
            if not isinstance(row, dict):
                continue
            pending.extend(row.get("@graph", []))
            types = row.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if not set(types).intersection(("Store", "GroceryStore", "LocalBusiness")):
                continue
            identity = json.dumps({key: row.get(key) for key in ("name", "address", "branchCode")})
            if expected_branch.casefold() not in identity.casefold():
                continue
            result.append(
                {
                    key: row[key]
                    for key in (
                        "name",
                        "address",
                        "geo",
                        "telephone",
                        "openingHoursSpecification",
                        "branchCode",
                        "url",
                    )
                    if key in row
                }
            )
    return result


def invalidate_anchors(placements, map_id, new_version):
    return [
        {**item, "anchor_status": "stale", "coordinates": None}
        if item.get("map_id") == map_id and item.get("map_version") != new_version
        else dict(item)
        for item in placements
    ]
