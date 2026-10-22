"""Repeatable deterministic store cleanup from retained, identity-bound source evidence."""

import copy
import math
import re
from collections import defaultdict
from urllib.parse import urlsplit

from .chain_profiles import VERSION, main_phone, out_of_scope, profile_for
from .domain import content_hash
from .store_discovery import STREET_WORDS, distance, names_compatible, text_key
from .store_enrichment import normalize, public_url

QUALITY_VERSION = "store-quality-v1"


def structured_address(store):
    address = copy.deepcopy(store.get("address"))
    if not isinstance(address, dict):
        return address
    full = address.get("full")
    if isinstance(full, str):
        match = re.fullmatch(r"\s*(.+),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*", full)
        if match:
            for key, value in zip(
                ("street", "city", "region", "postal_code"), match.groups(), strict=True
            ):
                if not address.get(key):
                    address[key] = value.strip()
    return address


def location_key(store):
    a = structured_address(store)
    if not isinstance(a, dict) or not all(a.get(k) for k in ("street", "city", "region")):
        return None
    # PO mailing suffixes and whitespace in a city do not establish a new premise.
    street = re.split(r",?\s+P\.?\s*O\.?\s*(?:Box\s*)?\d+\b", a["street"], flags=re.IGNORECASE)[0]
    if ";" in street or not re.match(r"^\d+[a-z]?(?:[-/]\d+)?\s", street, re.IGNORECASE):
        return None
    tokens = [STREET_WORDS.get(t, t) for t in text_key(street).split()]
    unit = a.get("unit")
    if unit:
        tokens += text_key(unit).split()
    return " ".join(tokens), re.sub(r"\s", "", text_key(a["city"])), a["region"].upper()


def same_brand(a, b):
    pa, pb = profile_for(a), profile_for(b)
    if pa["brand"] and pb["brand"]:
        return pa["brand"] == pb["brand"]
    return names_compatible(a.get("name"), b.get("name"))


def duplicate_candidates(stores):
    by_city = defaultdict(list)
    for r in stores:
        a = structured_address(r) or {}
        by_city[(text_key(a.get("city")).replace(" ", ""), a.get("region"))].append(r)
    found = []
    for group in by_city.values():
        for index, a in enumerate(group):
            for b in group[index + 1 :]:
                if not same_brand(a, b):
                    continue
                same_url = bool(
                    a.get("website")
                    and b.get("website")
                    and public_url(a["website"]) == public_url(b["website"])
                    and urlsplit(a["website"]).path not in ("", "/")
                )
                try:
                    phone = bool(
                        a.get("phone")
                        and b.get("phone")
                        and normalize("phone", a["phone"]) == normalize("phone", b["phone"])
                    )
                except ValueError:
                    phone = False
                key = location_key(a)
                same_address = key is not None and key == location_key(b)
                # A shared chain phone or co-located brands alone never merge.
                if same_url or phone and (same_address or profile_for(a)["brand"] == "fareway"):
                    found.append(
                        {
                            "a": a["id"],
                            "b": b["id"],
                            "signals": {
                                "branch_url": same_url,
                                "address": same_address,
                                "phone": phone,
                            },
                            "binding": content_hash([a, b]),
                        }
                    )
    return found


def clean_store(store):
    row = copy.deepcopy(store)
    p = profile_for(row)
    meta = copy.deepcopy(row.get("quality") or {})
    meta.update(version=QUALITY_VERSION, profile_id=p["id"], profile_version=VERSION)
    address = structured_address(row)
    if address != row.get("address"):
        meta.setdefault("original_address", copy.deepcopy(row.get("address")))
        row["address"] = address
        meta["address_method"] = "parse_explicit_full_postal_address"
    if pattern := out_of_scope(row):
        row["directory_scope"] = {
            "status": "excluded",
            "reason": "chain_format_exclusion",
            "profile": p["id"],
            "pattern": pattern,
            "physical_closure": False,
        }
        row["format"] = "convenience" if "fresh" in pattern else "specialist"
    phone = row.get("phone")
    if isinstance(phone, str):
        try:
            number = normalize("phone", phone)
        except ValueError:
            number = main_phone(phone, p)
            if number:
                meta.setdefault("original_phone", phone)
                row["phone"] = number = normalize("phone", number)
                meta["phone_method"] = "explicit_main_label"
        if number and number in p.get("chain_phones", ()):
            row["contact_channels"] = {
                **row.get("contact_channels", {}),
                "phone": {"scope": "chain", "value": number, "direct_branch_contact": False},
            }
    row["quality"] = meta
    return row


def coordinate_evidence(store, candidates):
    matches = []
    key = location_key(store)
    if key is None:
        return None, "address_unresolved"
    for candidate in candidates:
        payload = candidate["payload"]
        if location_key(payload) != key or not same_brand(store, payload):
            continue
        lat, lon = payload.get("latitude"), payload.get("longitude")
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (lat, lon)) or not (
            -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            continue
        if (structured_address(store) or {}).get("region") == "IA" and not (
            40.3 <= lat <= 43.6 and -96.8 <= lon <= -90.0
        ):
            continue
        # Unknown/missing acquisition times cannot become a newly checked fact.
        stamp = payload.get("source_observed_at") or candidate.get("retrieved_at")
        if not stamp:
            continue
        matches.append(
            {
                "latitude": lat,
                "longitude": lon,
                "source_id": candidate["source"],
                "record_id": candidate["source_key"],
                "source_url": payload.get("source_url"),
                "observed_at": stamp,
                "precision": "provider_reported_branch_point",
            }
        )
    if not matches:
        return None, "no_exact_source_point"
    if any(distance(a, b) > 150 for a in matches for b in matches):
        return None, "coordinate_source_conflict"
    chosen = min(
        matches,
        key=lambda r: (r["source_id"] != "usda_snap_arcgis", r["source_id"], r["record_id"]),
    )
    return {
        **chosen,
        "status": "source_reported",
        "supporting_sources": matches,
        "verified_at": None,
    }, None


def prepare(stores, candidates=(), *, state):
    updated = []
    gaps = []
    for original in stores:
        if (structured_address(original) or {}).get("region") != state:
            continue
        row = clean_store(original)
        if row.get("latitude") is None or row.get("longitude") is None:
            point, reason = coordinate_evidence(row, candidates)
            if point and row.get("directory_scope", {}).get("status") != "excluded":
                row.update(latitude=point["latitude"], longitude=point["longitude"])
                row["quality"]["coordinates"] = point
            else:
                gaps.append({"store_id": row["id"], "reason": reason or "out_of_scope"})
        updated.append(row)
    return {
        "version": QUALITY_VERSION,
        "state": state,
        "records": updated,
        "duplicates": duplicate_candidates(updated),
        "coordinate_gaps": gaps,
        "release": content_hash(updated),
    }


def publish(platform, plan, reviews=(), *, now):
    """Apply payload-bound operator aliases, then atomically publish a replacement pack."""
    from .store_enrichment import publish_enrichment

    if platform.current()["generation"] != plan["base_generation"]:
        raise ValueError("quality_base_generation_changed")
    rows = {r["id"]: r for r in plan["records"]}
    pairs = {frozenset((r["a"], r["b"])): r for r in plan["duplicates"]}
    # Validate every review before changing the identity registry.
    verified = []
    for review in reviews:
        pair = pairs.get(frozenset((review.get("from"), review.get("to"))))
        if (
            not pair
            or pair["binding"] != review.get("binding")
            or not review.get("reviewer")
            or not review.get("reason")
        ):
            raise ValueError("identity_review_must_bind_current_pair")
        if rows[review["from"]].get("directory_scope", {}).get("status") == "excluded":
            raise ValueError("excluded_store_alias_requires_review")
        verified.append(review)
    for review in verified:
        losing, target = rows[review["from"]], rows[review["to"]]
        if target.get("latitude") is None and all(
            type(losing.get(k)) in (int, float) for k in ("latitude", "longitude")
        ):
            target.update(latitude=losing["latitude"], longitude=losing["longitude"])
            target["quality"]["coordinates"] = {
                "status": "source_reported",
                "method": "reviewed_same_physical_branch_alias",
                "source_store_id": losing["id"],
                "source_url": losing.get("source_url"),
                "verified_at": None,
            }
        original = platform.get("store", review["from"])
        with platform.control.connect() as db:
            refs = db.execute(
                "SELECT source,source_key FROM identities WHERE kind='store' AND id=?",
                (review["from"],),
            ).fetchall()
        for source, key in refs:
            platform.control.alias(
                source, "store", key, review["to"], review["reviewer"] + ": " + review["reason"]
            )
        if not original:
            raise ValueError("alias_source_unavailable")
    return publish_enrichment(
        platform,
        plan["records"],
        base_generation=plan["base_generation"],
        release=plan["release"],
        now=now,
    )
