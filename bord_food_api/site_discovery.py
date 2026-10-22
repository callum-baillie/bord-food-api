"""Offline, state-independent website discovery from retained public source panels.

Candidates are a queue, not facts, permissions or automatic crawl activations.
"""

import hashlib
import re
from urllib.parse import urljoin, urlsplit

from .domain import content_hash
from .store_enrichment import public_url
from .store_pages import Page, links, visible
from .store_quality import location_key

VERSION = "store-site-discovery-v1"
NETWORKS = {"ncg": ("ncg.coop",), "iga": ("iga.com",), "civic_directory": ()}
SOCIAL = ("facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com")


def tokens(value):
    from .store_discovery import STREET_WORDS

    return " ".join(STREET_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", value.lower()))


def platform_profile(html):
    if re.search(r"(?:Associated Wholesale Grocers|awginc\.com)", html, re.IGNORECASE):
        return {"id": "awg_public_locations", "version": VERSION}
    return {"id": "public_contact_panels", "version": VERSION}


def directory_candidates(html, source_url, stores, *, state, source_id, retrieved_at):
    if source_id not in NETWORKS:
        raise ValueError("unsupported_discovery_source")
    public_url(source_url)
    host = urlsplit(source_url).hostname
    if NETWORKS[source_id] and not any(
        host == d or host.endswith("." + d) for d in NETWORKS[source_id]
    ):
        raise ValueError("discovery_source_host_mismatch")
    if len(html.encode()) > 2 * 1024**2:
        raise ValueError("discovery_document_limit")
    page = Page()
    page.feed(html)
    page.close()
    digest = hashlib.sha256(html.encode()).hexdigest()
    source_panels = []
    for n in page.nodes:
        if n["tag"] not in {"li", "article", "section", "div", "td"} or re.search(
            r"/(?:nav|footer|header)/", n["path"]
        ):
            continue
        text = visible(n)
        if len(text) <= 6000:
            source_panels.append((n, text, tokens(text)))
    result = []
    for r in stores:
        address = r.get("address") or {}
        if address.get("region") != state or not location_key(r):
            continue
        street = tokens(address["street"])
        postal = str(address.get("postal_code") or "").split("-")[0]
        panels = []
        for n, text, plain in source_panels:
            if (
                len(text) > 6000
                or f" {street} " not in f" {plain} "
                or not postal
                or not re.search(r"\b" + re.escape(postal) + r"\b", text)
            ):
                continue
            if tokens(address.get("city") or "") not in plain:
                continue
            # Address plus a distinctive business-name token, never proximity.
            names = [
                w
                for w in tokens(r["name"]).split()
                if w
                not in {
                    "llc",
                    "inc",
                    "store",
                    "food",
                    "foods",
                    "market",
                    "grocery",
                    "community",
                    "coop",
                    "co",
                    "op",
                }
                and len(w) > 3
            ]
            if not names or not any(re.search(r"\b" + re.escape(w) + r"\b", plain) for w in names):
                continue
            panels.append((len(text), n))
        if not panels:
            continue
        n = min(panels, key=lambda p: p[0])[1]
        urls = set()
        for link in links(n):
            try:
                u = public_url(urljoin(source_url, link["href"]))
            except ValueError:
                continue
            p = urlsplit(u)
            if (
                p.scheme not in {"http", "https"}
                or p.hostname == host
                or any(p.hostname == d or p.hostname.endswith("." + d) for d in SOCIAL)
            ):
                continue
            if re.search(
                r"\.(?:pdf|png|jpe?g|svg)(?:$|\?)", p.path, re.IGNORECASE
            ) or p.hostname.endswith(("google.com", "deals.coop")):
                continue
            urls.add(u)
        for u in sorted(urls):
            binding = {
                "store_id": r["id"],
                "source_address": address,
                "url": u,
                "evidence_sha256": digest,
            }
            result.append(
                {
                    **binding,
                    "version": VERSION,
                    "source_id": source_id,
                    "record_id": n["path"],
                    "evidence_url": source_url,
                    "retrieved_at": retrieved_at,
                    "store_revision": r.get("content_revision"),
                    "binding": content_hash(binding),
                    "status": "candidate_requires_review",
                    "site_scope": "unknown",
                    "single_store_site": False,
                }
            )
    return result


def contact_followups(html, target):
    """Observed, same-origin contact/location links only; no guessed paths/fetches."""
    page = Page()
    page.feed(html)
    page.close()
    origin = urlsplit(target["url"])
    result = []
    for item in links(page.root):
        if not re.search(
            r"\b(?:contact|locations?|store info|about us)\b", item["text"], re.IGNORECASE
        ):
            continue
        try:
            url = public_url(urljoin(target["url"], item["href"]))
        except ValueError:
            continue
        p = urlsplit(url)
        if (
            p.scheme == "https"
            and p.netloc == origin.netloc
            and not p.query
            and url != public_url(target["url"])
        ):
            result.append(
                {
                    "url": url,
                    "evidence_url": target["url"],
                    "anchor": item["text"],
                    "store_id": target["store_id"],
                    "source_address": target["source_address"],
                    "evidence_sha256": hashlib.sha256(html.encode()).hexdigest(),
                    "status": "candidate_requires_fresh_robots_and_branch_review",
                }
            )
    return list({r["url"]: r for r in result}.values())[:3]


def reviewed_candidate(target, branch):
    """Operator-reviewed discovery proof bound to exact branch and source bytes."""
    proof = target.get("observed_url_evidence") or {}
    binding = {k: proof.get(k) for k in ("store_id", "source_address", "url", "evidence_sha256")}
    try:
        public_url(proof.get("evidence_url"))
    except ValueError:
        return False
    return bool(
        branch
        and proof.get("kind") == "directory_branch_website_candidate"
        and proof.get("source_id") in NETWORKS | {"retailer_site": ()}
        and proof.get("binding") == content_hash(binding)
        and re.fullmatch(r"[a-f0-9]{64}", str(proof.get("evidence_sha256") or ""))
        and proof.get("store_id") == target["store_id"]
        and proof.get("url") == target["url"]
        and proof.get("source_address") == branch.get("address")
        and proof.get("reviewer")
        and proof.get("reviewed_at")
    )
