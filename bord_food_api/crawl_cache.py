"""Operator-only bounded HTTP validators; never part of a serving catalog."""

import gzip
import hashlib
import json
from datetime import UTC
from email.utils import parsedate_to_datetime


class PageCache:
    def __init__(self, frontier, *, enabled=False):
        self.frontier, self.enabled = frontier, enabled
        with frontier.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS crawl_pages(
              url TEXT PRIMARY KEY,identity TEXT,body BLOB,sha256 TEXT,etag TEXT,
              modified TEXT,checked REAL)""")

    @staticmethod
    def identity(target):
        return hashlib.sha256(
            json.dumps([target["store_id"], target.get("source_address")], sort_keys=True).encode()
        ).hexdigest()

    def load(self, target, limit):
        if not self.enabled:
            return None
        with self.frontier.connect() as db:
            row = db.execute(
                "SELECT identity,body,sha256,etag,modified,checked FROM crawl_pages WHERE url=?",
                (target["url"],),
            ).fetchone()
        if (
            not row
            or row[0] != self.identity(target)
            or not 0 <= self.frontier.clock() - row[5] <= 30 * 86400
        ):
            return None
        try:
            import io

            with gzip.GzipFile(fileobj=io.BytesIO(row[1])) as stream:
                body = stream.read(limit + 1)
            if len(body) > limit or hashlib.sha256(body).hexdigest() != row[2]:
                return None
        except (ValueError, OSError, EOFError):
            return None
        return {"body": body, "etag": row[3], "modified": row[4]}

    def save(self, target, body, headers):
        if not self.enabled:
            return
        headers = {str(key).lower(): value for key, value in headers.items()}
        with self.frontier.connect() as db:
            db.execute("DELETE FROM crawl_pages WHERE url=?", (target["url"],))
            controls = (headers.get("cache-control") or "").lower()
            vary = {s.strip().lower() for s in (headers.get("vary") or "").split(",")}
            if (
                "no-store" in controls
                or "*" in vary
                or vary - {"", "accept-encoding", "user-agent", "accept-language"}
            ):
                return

            def header(name):
                value = headers.get(name.lower())
                return (
                    value
                    if isinstance(value, str)
                    and len(value) <= 1024
                    and not any(ord(c) < 32 for c in value)
                    else None
                )

            etag, modified = header("ETag"), header("Last-Modified")
            if not etag and not modified:
                return
            db.execute(
                "INSERT INTO crawl_pages VALUES(?,?,?,?,?,?,?)",
                (
                    target["url"],
                    self.identity(target),
                    gzip.compress(body),
                    hashlib.sha256(body).hexdigest(),
                    etag,
                    modified,
                    self.frontier.clock(),
                ),
            )
            # LRU bound in compressed bytes; old pages may be fetched normally.
            rows = db.execute(
                "SELECT url,length(body) FROM crawl_pages ORDER BY checked DESC,url"
            ).fetchall()
            total = 0
            for url, size in rows:
                total += size
                if total > 64 * 1024**2:
                    db.execute("DELETE FROM crawl_pages WHERE url=?", (url,))


def retry_until(value, now, *, fallback=3600):
    try:
        if isinstance(value, str) and value.strip().isdigit():
            return now + max(fallback, int(value.strip()))
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return max(now + fallback, stamp.timestamp())
    except (ValueError, TypeError, OverflowError):
        return now + fallback
