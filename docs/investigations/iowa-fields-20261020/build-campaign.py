"""Prepare a bounded Iowa campaign from published identities and pinned retained places."""

import argparse
import copy
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bord_food_api.store_discovery import address_key, entity_names_compatible
from bord_food_api.store_enrichment import public_url
from bord_food_api.store_sources import place_candidate

BLOCKED_DOMAINS = {
    "facebook.com",
    "fb.com",
    "yelp.com",
    "google.com",
    "business.site",
    "edan.io",
    "justplainbusiness.com",
    "mapquest.com",
    "yellowpages.com",
    "instagram.com",
    "wikipedia.org",
    "waze.com",
    "tripadvisor.com",
    "storelocators.com",
    "scrapehero.com",
}
HERE = Path(__file__).parent


def usable(url, *, probe_https=False):
    try:
        cleaned = public_url(url)
        p = urlsplit(cleaned)
        if any(p.hostname == h or p.hostname.endswith("." + h) for h in BLOCKED_DOMAINS):
            return None
        if p.scheme == "http" and probe_https:
            p = p._replace(scheme="https")
        if p.scheme != "https":
            return None
        if any(
            word in p.path.lower()
            for word in ["/login", "/account", "/checkout", "/cart", "/search"]
        ):
            return None
        return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))
    except (ValueError, TypeError, AttributeError):
        return None


def build(snapshot, places, extract_sha256, campaign_id, canonical=()):
    rows = snapshot["stores"]
    by_address = defaultdict(list)
    for r in rows:
        if k := address_key(r):
            by_address[k].append(r)
    candidates = defaultdict(list)
    for p in places:
        c = place_candidate("overture_places", p)
        if c["category"] == "exclude":
            continue
        found = [
            s
            for s in by_address.get(address_key(c["payload"]), [])
            if entity_names_compatible(s, c["payload"])
        ]
        if len(found) != 1:
            continue
        for raw in p.get("websites") or []:
            if url := usable(raw, probe_https=True):
                candidates[found[0]["id"]].append((url, p["id"], raw))
    overrides = {t["store_id"]: t for t in canonical}
    common = Counter(usable(r.get("website")) for r in rows if usable(r.get("website")))
    targets = []
    gaps = []
    seen = {}
    now = time.time()
    for row in rows:
        identity = row["id"]
        url = usable(row.get("website"))
        evidence = None
        alternatives = sorted(
            candidates[identity],
            key=lambda x: (urlsplit(x[0]).path == "/", -len(urlsplit(x[0]).path), x[0]),
        )
        if url and urlsplit(url).path == "/" and (common[url] > 1 or row.get("chain_id")):
            url = None
        if identity in overrides:
            url = overrides[identity]["url"]
            evidence = copy.deepcopy(overrides[identity]["observed_url_evidence"])
            evidence["source_address"] = row["address"]
        elif not url and alternatives:
            url, record_id, raw = alternatives[0]
            evidence = {
                "kind": "provider_branch_website_candidate",
                "source_id": "overture_places",
                "record_id": record_id,
                "extract_sha256": extract_sha256,
                "provider_reported_url": raw,
                "source_address": row["address"],
                "store_id": identity,
                "url": url,
                "evidence_url": url,
                "reviewed_at": now,
                "normalization": "HTTPS-only probe at same provider-reported host/path; remove known tracking parameters; root slash",
            }
        elif url and url != row.get("website"):
            evidence = {
                "kind": "observed_official_branch_page",
                "source_address": row["address"],
                "store_id": identity,
                "url": url,
                "evidence_url": url,
                "reviewed_at": now,
                "note": "Retained published website; only tracking parameters or root slash normalized",
            }
        if not url or url in seen:
            gaps.append(
                {
                    "store_id": identity,
                    "name": row["name"],
                    "source_address": row["address"],
                    "url": row.get("website"),
                    "reason": "branch_url_missing"
                    if not row.get("website")
                    else "unsafe_or_unsupported_url",
                    "gap_detail": "no unique supported HTTPS branch website in retained sources"
                    if not url
                    else "shared URL requires branch identity review",
                }
            )
            continue
        seen[url] = identity
        t = {
            "store_id": identity,
            "name": row["name"],
            "chain_id": row.get("chain_id"),
            "spider": row.get("spider"),
            "source_website": row.get("website"),
            "url": url,
            "source_address": row["address"],
            "expected_branch": " ".join(
                x for x in [row.get("chain_name"), row.get("name"), row["address"].get("city")] if x
            ),
            "country": "US",
        }
        if evidence:
            t["observed_url_evidence"] = evidence
        if evidence and evidence.get("kind") == "provider_branch_website_candidate":
            t["source_authority"] = "community"
        if urlsplit(url).path == "/":
            t["single_store_site"] = True
        t["missing_field_priority"] = sum(
            weight
            for field, weight in [
                ("phone", 5),
                ("website", 5),
                ("opening_hours", 3),
                ("email", 1),
                ("departments", 1),
            ]
            if not row.get(field)
        )
        targets.append(t)
    targets.sort(
        key=lambda t: (bool(t.get("chain_id")), -t["missing_field_priority"], t["store_id"])
    )
    base = json.loads((HERE / "pilot1-config.json").read_text())
    scope_template = next(iter(base["scopes"].values()))
    scopes = {}
    for t in targets:
        host = urlsplit(t["url"]).hostname
        if host in scopes:
            continue
        s = copy.deepcopy(scope_template)
        s["review_evidence"] = (
            "Owner-authorized Iowa public source branch refresh; pinned SNAP/OSM/Overture evidence; robots required at request time; no product inventory or pricing"
        )
        s["crawl"].update(
            allowed_host=host,
            scope_prefix="/",
            page_cache_enabled=True,
            report_redirects=True,
            max_pages_run=3,
            max_run_seconds=600,
            max_total_bytes=6291456,
            robots_redirect_hosts=[host.removeprefix("www.")]
            if host.startswith("www.")
            else ["www." + host]
            if host.count(".") == 1
            else ["www.aldi.us"]
            if host in {"stores.aldi.us", "info.aldi.us"}
            else [],
        )
        scopes[host] = s
    base.update(
        canonical_followup_enabled=True,
        campaign_id=campaign_id,
        targets=targets,
        scopes=scopes,
        duration_seconds=7 * 86400,
        directory_stores=len(rows),
        missing_branch_urls=len(gaps),
        coverage_gaps=gaps,
    )
    base["decisions"].update(
        global_budget_nanousd=15000000000,
        budget_nanousd=5000000000,
        max_calls=500,
        review_every_page=False,
    )
    return base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--places", type=Path, required=True)
    p.add_argument("--canonical", type=Path)
    p.add_argument("--campaign-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    sha = hashlib.sha256(a.places.read_bytes()).hexdigest()
    places = [json.loads(l) for l in a.places.read_text().splitlines() if l.strip()]
    config = build(
        json.loads(a.snapshot.read_text()),
        places,
        sha,
        a.campaign_id,
        json.loads(a.canonical.read_text()) if a.canonical else [],
    )
    a.output.write_text(json.dumps(config, indent=2) + "\n")
    print(
        json.dumps(
            {
                "targets": len(config["targets"]),
                "coverage_gaps": len(config["coverage_gaps"]),
                "hosts": len(config["scopes"]),
                "directory_stores": config["directory_stores"],
                "network": False,
            }
        )
    )


if __name__ == "__main__":
    main()
