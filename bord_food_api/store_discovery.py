"""Iowa public-directory discovery, completeness checks and conservative reconciliation.

No networking on import. Provider IDs/provenance stay distinct from canonical IDs;
name or proximity alone never merges store identities. Inventory is never parsed.
"""

import hashlib
import json
import math
import re
import sqlite3
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

from .platform import atomic_json
from .transport import Transport

SNAP_LAYER = "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0"
SNAP_ITEM = "https://www.arcgis.com/sharing/rest/content/items/8b260f9a10b0459aa441ad8588c2251c"
OSM_ENDPOINT = "https://overpass-api.de/api/interpreter"
OSM_QUERY = """[out:json][timeout:120];area["ISO3166-2"="US-IA"]["admin_level"="4"]->.ia;
nwr["shop"~"^(supermarket|grocery|wholesale|general|department_store)$"](area.ia);out center tags;"""
SOURCE = "iowa_store_discovery"
EXCLUDED_NAMES = re.compile(
    r"\b(?:dollar\s*(?:general|tree)|family\s*dollar|walgreens|cvs|casey'?s|kwik\s*(?:star|trip)|"
    r"7\s*eleven|dollarama|five\s*below|hartig\s*drug|"
    r"hy[ -]*vee\s*drug\s*(?:store|town)|fast\s*(?:and|&)\s*fresh)\b",
    re.IGNORECASE,
)
STREET_WORDS = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "drive": "dr",
    "boulevard": "blvd",
    "highway": "hwy",
    "lane": "ln",
    "court": "ct",
    "parkway": "pkwy",
    "place": "pl",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    "suite": "ste",
}


def text_key(value):
    return " ".join(
        re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(value or "")).casefold())
    )


def name_key(value):
    return re.sub(r"[^a-z]", "", text_key(value))


def address_key(payload):
    address = payload.get("address") or {}
    street, city = address.get("street"), address.get("city")
    if not street or not city:
        full = address.get("full") or ""
        match = re.fullmatch(
            r"\s*(.+),\s*([^,]+),\s*(?:IA|Iowa)\s+\d{5}(?:-\d{4})?\s*", full, re.IGNORECASE
        )
        if match:
            street, city = match.groups()
    if not street or not city:
        return None
    tokens = text_key(street).split()
    street = " ".join(STREET_WORDS.get(t, t) for t in tokens)
    street = re.sub(r"\b([ns]) ([ew])\b", r"\1\2", street)
    # Explicit unit information must participate in identity matching.
    unit = address.get("unit")
    if unit:
        street += " " + " ".join(STREET_WORDS.get(t, t) for t in text_key(unit).split())
    if not re.match(r"^\d+[a-z]?(?:[-/]\d+)?\s", street):
        return None
    return street, text_key(city), "IA"


def address_review_key(payload):
    """A coarse blocking key only: never sufficient to merge store identities."""
    key = address_key(payload)
    if not key:
        return None
    street = re.split(r"\b(?:ste|unit|stop)\b", key[0])[0].strip()
    ignored = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "us", "ia", "state"}
    ignored.update(STREET_WORDS.values())
    words = street.split()
    return words[0], " ".join(w for w in words[1:] if w not in ignored), key[1]


def names_compatible(a, b):
    a, b = name_key(a), name_key(b)
    return bool(
        a and b and (a == b or min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))
    )


def entity_names_compatible(a, b):
    return any(
        names_compatible(x, y)
        for x in (a.get("name"), a.get("chain_name"))
        for y in (b.get("name"), b.get("chain_name"))
    )


def identity_needs_review(a, b):
    gap = distance(a, b)
    if gap < 30:
        return True
    if not entity_names_compatible(a, b):
        return False
    if gap < 150:
        return True
    ak, bk = address_review_key(a), address_review_key(b)
    if ak and bk:
        return ak == bk or math.isinf(gap) and ak[2] == bk[2]
    return False


def distance(a, b):
    coords = [a.get(k) for k in ("latitude", "longitude")] + [
        b.get(k) for k in ("latitude", "longitude")
    ]
    if not all(type(n) in (int, float) and math.isfinite(n) for n in coords):
        return math.inf
    lat1, lon1, lat2, lon2 = map(math.radians, coords)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def valid_coordinates(payload):
    lat, lon = payload.get("latitude"), payload.get("longitude")
    if lat is None and lon is None:
        return True  # An evidenced postal address can stand without coordinates.
    return (
        all(type(n) in (int, float) and math.isfinite(n) for n in (lat, lon))
        and 40.3 <= lat <= 43.6
        and -96.8 <= lon <= -90.0
    )


def specialist_name(name):
    return bool(
        re.search(r"\b(?:meats?|butcher|locker|liquor|fleet\s*farm)\b", name, re.IGNORECASE)
        and not re.search(r"\bgrocer(?:y|ies)\b", name, re.IGNORECASE)
    )


class PublicJSON:
    """Bounded allowlisted public bulk transport; no credentials or retailer pages."""

    def __init__(
        self, directory, contact, *, transport_factory=Transport, sleep=time.sleep, clock=time.time
    ):
        if "@" not in contact or any(x in contact for x in ("example.", "placeholder")):
            raise ValueError("real_operator_contact_required")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sleep, self.clock, self.last = sleep, clock, {}
        self.transport = transport_factory(
            {
                "mode": "bulk_only",
                "can_fetch": True,
                "origins": [
                    "https://www.arcgis.com",
                    "https://services1.arcgis.com",
                    "https://overpass-api.de",
                ],
                "max_redirects": 0,
                "max_requests": 50,
                "max_artifact_bytes": 8 * 1024**2,
                "max_total_bytes": 24 * 1024**2,
                "max_seconds": 180,
                "timeout": 150,
            }
        )
        self.agent = "BordFoodCatalog/1.0 (+mailto:" + contact + ")"

    def __call__(self, url):
        from urllib.parse import urlsplit

        host = urlsplit(url).hostname
        wait = 2 - (self.clock() - self.last.get(host, 0))
        if wait > 0:
            self.sleep(wait)
        self.last[host] = self.clock()
        key = hashlib.sha256(url.encode()).hexdigest()
        try:
            with self.transport.get(url, headers={"User-Agent": self.agent}) as response:
                raw = response.read(8 * 1024**2 + 1)
            if len(raw) > 8 * 1024**2:
                raise ValueError("discovery_response_too_large")
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("error"):
                raise ValueError("source_returned_error")
            (self.directory / (key + ".json")).write_bytes(raw)
            atomic_json(
                self.directory / (key + ".receipt.json"),
                {
                    "url": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                    "retrieved_at": self.clock(),
                    "state": "succeeded",
                },
            )
            return value
        except BaseException as error:
            atomic_json(
                self.directory / (key + ".receipt.json"),
                {
                    "url": url,
                    "state": "failed",
                    "error_type": type(error).__name__,
                    "http_status": getattr(error, "status", None),
                    "retrieved_at": self.clock(),
                },
            )
            raise


def acquire_snap(fetch):
    """Fetch all Iowa rows by frozen OID set; truncated/moving snapshots fail closed."""
    item = fetch(SNAP_ITEM + "?f=json")
    if (
        item.get("owner") != "FNS_SNAP_RPMD"
        or item.get("url", "").rstrip("/") != SNAP_LAYER.rsplit("/", 1)[0]
    ):
        raise ValueError("snap_owner_or_service_changed")
    before = fetch(SNAP_LAYER + "?f=json")
    required = {
        "Record_ID",
        "Store_Name",
        "Store_Street_Address",
        "City",
        "State",
        "Store_Type",
        "ObjectId",
    }
    if not required <= {f["name"] for f in before.get("fields", [])}:
        raise ValueError("snap_schema_changed")
    stamp = (before.get("editingInfo") or {}).get("dataLastEditDate")
    if type(stamp) is not int:
        raise ValueError("snap_source_clock_missing")

    def query(**params):
        return fetch(
            SNAP_LAYER + "/query?" + urlencode({"where": "State='IA'", "f": "json", **params})
        )

    count = query(returnCountOnly="true").get("count")
    ids = query(returnIdsOnly="true").get("objectIds")
    if (
        type(count) is not int
        or not 1 <= count <= 10000
        or not isinstance(ids, list)
        or len(set(ids)) != len(ids)
        or len(ids) != count
        or any(type(i) is not int for i in ids)
    ):
        raise ValueError("snap_reference_count_mismatch")
    rows = []
    # Keep GET URLs below common proxy/ArcGIS URL limits. Freeze IDs rather
    # than trusting offset pagination while the provider's table can change.
    for offset in range(0, len(ids), 100):
        page_ids = sorted(ids)[offset : offset + 100]
        page = query(objectIds=",".join(map(str, page_ids)), outFields="*", returnGeometry="false")
        if page.get("exceededTransferLimit"):
            raise ValueError("snap_truncated_page")
        attributes = [f["attributes"] for f in page.get("features", [])]
        if len(attributes) != len(page_ids) or {a.get("ObjectId") for a in attributes} != set(
            page_ids
        ):
            raise ValueError("snap_page_identity_mismatch")
        rows.extend(attributes)
    after = fetch(SNAP_LAYER + "?f=json")
    if stamp != (after.get("editingInfo") or {}).get("dataLastEditDate"):
        raise ValueError("snap_snapshot_changed_during_download")
    if len({a.get("Record_ID") for a in rows}) != count or any(
        a.get("Record_ID") is None for a in rows
    ):
        raise ValueError("snap_duplicate_native_ids")
    return rows, {
        "source": "usda_snap_arcgis",
        "state": "IA",
        "source_clock": stamp,
        "reference_rows": count,
        "complete_reference": True,
        "all_grocery_census_complete": False,
        "source_url": SNAP_LAYER,
        "attribution": "USDA Food and Nutrition Service",
    }


def snap_candidates(rows, metadata):
    candidates = []
    for row in rows:
        if row.get("State") != "IA":
            raise ValueError("snap_outside_iowa")
        category, reason = "review", "store_type_requires_review"
        kind, name = row.get("Store_Type"), row.get("Store_Name") or ""
        if kind in {
            "Grocery Store",
            "Supermarket",
            "Super Store",
            "Large Grocery Store",
            "Medium Grocery Store",
            "Small Grocery Store",
        }:
            category, reason = "include", "provider_grocery_classification"
        elif kind in {"Convenience Store", "Farmers and Markets", "Specialty Store"}:
            category, reason = "exclude", "outside_store_format_scope"
        if EXCLUDED_NAMES.search(name):
            category, reason = "exclude", "excluded_retailer_format"
        elif category != "exclude" and specialist_name(name):
            category, reason = "review", "possible_specialist_format"
        payload = {
            "name": name,
            "source_id": str(row["Record_ID"]),
            "country": "US",
            "address": {
                "street": row.get("Store_Street_Address"),
                "unit": row.get("Additonal_Address"),
                "city": row.get("City"),
                "region": "IA",
                "postal_code": row.get("Zip_Code"),
            },
            "latitude": row.get("Latitude"),
            "longitude": row.get("Longitude"),
            "county": row.get("County"),
            "format": "superstore" if kind == "Super Store" else "grocery",
            "source_record": row,
            "attribution": metadata["attribution"],
            "source_url": SNAP_LAYER,
            "source_observed_at": metadata["source_clock"],
            "snap": {
                "native_record_id": str(row["Record_ID"]),
                "authorized_in_snapshot": True,
                "store_type": kind,
            },
            "license": "US-government-data",
        }
        if not name or not address_key(payload):
            category, reason = "review", "required_address_or_name_missing"
        if not valid_coordinates(payload):
            category, reason = "review", "invalid_or_outside_iowa_coordinates"
        candidates.append(
            {
                "source": "usda_snap_arcgis",
                "source_key": "snap:" + str(row["Record_ID"]),
                "category": category,
                "reason": reason,
                "payload": payload,
            }
        )
    return candidates


def osm_candidates(document):
    if (
        document.get("remark")
        or not isinstance(document.get("elements"), list)
        or not document.get("osm3s", {}).get("timestamp_osm_base")
    ):
        raise ValueError("osm_incomplete_query")
    result, seen = [], set()
    for element in document["elements"]:
        native = f"{element.get('type')}/{element.get('id')}"
        if (
            element.get("type") not in {"node", "way", "relation"}
            or type(element.get("id")) is not int
            or native in seen
        ):
            raise ValueError("osm_invalid_or_duplicate_identity")
        seen.add(native)
        tags = element.get("tags") or {}
        center = element.get("center") or element
        payload = {
            "name": tags.get("name") or tags.get("brand"),
            "country": "US",
            "source_id": native,
            "address": {
                "street": " ".join(
                    str(tags[k]) for k in ("addr:housenumber", "addr:street") if tags.get(k)
                ),
                "unit": tags.get("addr:unit"),
                "city": tags.get("addr:city"),
                "region": "IA",
                "postal_code": tags.get("addr:postcode"),
            },
            "latitude": center.get("lat"),
            "longitude": center.get("lon"),
            "website": tags.get("website") or tags.get("contact:website"),
            "format": tags.get("shop"),
            "attribution": "© OpenStreetMap contributors",
            "license": "ODbL-1.0",
            "source_url": "https://www.openstreetmap.org/" + native,
            "source_observed_at": document["osm3s"]["timestamp_osm_base"],
            "source_record": tags,
        }
        category, reason = "include", "osm_supermarket_in_iowa_area"
        if tags.get("shop") not in {"supermarket", "grocery"}:
            category, reason = "review", "store_type_requires_review"
        if EXCLUDED_NAMES.search(payload["name"] or ""):
            category, reason = "exclude", "excluded_retailer_format"
        elif specialist_name(payload["name"] or ""):
            category, reason = "review", "possible_specialist_format"
        if tags.get("addr:state") not in (None, "IA", "Iowa"):
            category, reason = "review", "conflicting_state"
        if not payload["name"] or not address_key(payload):
            category, reason = "review", "required_address_or_name_missing"
        if not valid_coordinates(payload):
            category, reason = "review", "invalid_or_outside_iowa_coordinates"
        result.append(
            {
                "source": "openstreetmap",
                "source_key": "osm:" + native,
                "category": category,
                "reason": reason,
                "payload": payload,
            }
        )
    return result


def catalog_stores(root, *, state="IA"):
    root = Path(root)
    manifest = json.loads((root / "current.json").read_text())
    with sqlite3.connect(
        (root / manifest["packs"]["stores"]).resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        return [
            {**json.loads(raw), "catalog_source": source, "catalog_source_key": key}
            for raw, source, key in db.execute(
                "SELECT payload,source,source_key FROM entities WHERE kind='store'"
            )
            if state is None
            or str((json.loads(raw).get("address") or {}).get("region", "")).upper()
            in ({"IA", "IOWA"} if state.upper() in {"IA", "IOWA"} else {state.upper()})
        ]


def reclassify(candidates, metadata):
    """Replay classification from pinned raw assertions, without source requests."""
    result = []
    for candidate in candidates:
        payload = candidate["payload"]
        if candidate["source"] == "usda_snap_arcgis":
            result.extend(snap_candidates([payload["source_record"]], metadata))
        elif candidate["source"] == "openstreetmap":
            kind, key = payload["source_id"].split("/")
            result.extend(
                osm_candidates(
                    {
                        "osm3s": {"timestamp_osm_base": payload["source_observed_at"]},
                        "elements": [
                            {
                                "type": kind,
                                "id": int(key),
                                "tags": payload["source_record"],
                                "lat": payload.get("latitude"),
                                "lon": payload.get("longitude"),
                            }
                        ],
                    }
                )
            )
        else:
            raise ValueError("unknown_discovery_provider")
    return result


def apply_reviews(candidates, decisions, candidate_sha256):
    if decisions.get("candidate_sha256") != candidate_sha256:
        raise ValueError("review_bundle_binding_invalid")
    index = {c["source_key"]: c for c in candidates}
    seen = set()
    for decision in decisions.get("decisions", []):
        key = decision["source_key"]
        candidate = index[key]
        digest = hashlib.sha256(
            json.dumps(candidate["payload"], sort_keys=True).encode()
        ).hexdigest()
        if key in seen or digest != decision.get("payload_sha256"):
            raise ValueError("review_identity_binding_invalid")
        seen.add(key)
        if (
            not decision.get("evidence_urls")
            or not decision.get("reviewed_at")
            or not decision.get("reason")
        ):
            raise ValueError("review_evidence_required")
        if decision.get("action") != "include" or candidate["reason"] not in {
            "store_type_requires_review",
            "possible_specialist_format",
        }:
            raise ValueError("review_cannot_override_identity_or_scope")
        candidate.update(category="include", reason="operator_format_review")
        candidate["payload"]["format_review"] = decision
    return candidates


def reconcile(existing, candidates):
    candidates = [dict(c) for c in candidates]
    classified = defaultdict(list)
    for candidate in candidates:
        if candidate["category"] == "include" and (key := address_key(candidate["payload"])):
            classified[key].append(candidate)
    # A second provider's explicit grocery classification can resolve SNAP's
    # broad "Other" category only at the same full address and compatible name.
    for candidate in candidates:
        if candidate["reason"] != "store_type_requires_review":
            continue
        corroborated = [
            c
            for c in classified.get(address_key(candidate["payload"]), [])
            if c["source"] != candidate["source"]
            and entity_names_compatible(c["payload"], candidate["payload"])
        ]
        if corroborated:
            candidate["category"] = "include"
            candidate["reason"] = "cross_provider_grocery_classification"
    by_address, aliases = defaultdict(list), {}
    for row in existing:
        key = address_key(row)
        if key:
            by_address[key].append(row)
        for alias in row.get("discovery_keys", []):
            aliases[alias] = row
    groups, crosswalk, reviews, excluded, updates = [], [], [], [], {}
    resolved_evidence = []
    for candidate in sorted(
        candidates, key=lambda c: (0 if c["source"] == "usda_snap_arcgis" else 1, c["source_key"])
    ):
        payload, native = candidate["payload"], candidate["source_key"]
        if candidate["category"] == "exclude":
            excluded.append(candidate)
            continue
        if candidate["reason"] in {
            "invalid_or_outside_iowa_coordinates",
            "conflicting_state",
            "required_address_or_name_missing",
        }:
            reviews.append(candidate)
            continue
        key = address_key(payload)
        known = aliases.get(native)
        exact = by_address.get(key, []) if key else []
        if known and address_key(known) != key:
            reviews.append({**candidate, "reason": "native_identity_location_changed"})
            continue
        if known and not entity_names_compatible(known, payload):
            reviews.append({**candidate, "reason": "native_identity_name_changed"})
            continue
        matches = [r for r in exact if entity_names_compatible(r, payload)]
        if known:
            matches = [known]
        if len(matches) == 1:
            matched = matches[0]
            resolved_evidence.append(
                {**payload, "id": matched["id"], "chain_name": matched.get("chain_name")}
            )
            if (
                matched.get("catalog_source") == SOURCE
                and matched.get("catalog_source_key") == native
                and entity_names_compatible(matched, payload)
            ):
                updated = {
                    k: v
                    for k, v in matched.items()
                    if k not in {"catalog_source", "catalog_source_key"}
                }
                updated.update({k: v for k, v in payload.items() if v is not None})
                updates[native] = {"kind": "store", "source_key": native, "payload": updated}
            crosswalk.append(
                {
                    "source_key": native,
                    "canonical_id": matches[0]["id"],
                    "state": "matched_existing",
                    "evidence": "native_identity" if known else "exact_address_and_compatible_name",
                }
            )
            continue
        if exact or len(matches) > 1:
            reviews.append({**candidate, "reason": "address_identity_conflict"})
            continue
        nearby = [r for r in existing + resolved_evidence if identity_needs_review(r, payload)]
        if nearby:
            reviews.append(
                {
                    **candidate,
                    "reason": "nearby_identity_requires_review",
                    "candidate_ids": sorted({r["id"] for r in nearby}),
                }
            )
            continue
        if candidate["category"] != "include" or key is None:
            reviews.append(candidate)
            continue
        same = [g for g in groups if address_key(g["payload"]) == key]
        if same:
            if len(same) == 1 and names_compatible(same[0]["payload"]["name"], payload["name"]):
                same[0]["payload"]["discovery_keys"].append(native)
                same[0]["payload"]["discovery_sources"].append(
                    {
                        "source_id": candidate["source"],
                        "record_id": native,
                        "url": payload["source_url"],
                        "license": payload["license"],
                    }
                )
                crosswalk.append(
                    {
                        "source_key": native,
                        "proposed_key": same[0]["source_key"],
                        "state": "matched_new",
                        "evidence": "exact_address_and_compatible_name",
                    }
                )
            else:
                reviews.append({**candidate, "reason": "new_address_identity_conflict"})
            continue
        nearby_new = [g for g in groups if identity_needs_review(g["payload"], payload)]
        if nearby_new:
            reviews.append(
                {
                    **candidate,
                    "reason": "nearby_new_identity_requires_review",
                    "candidate_keys": [g["source_key"] for g in nearby_new],
                }
            )
            continue
        record = {
            "kind": "store",
            "source_key": native,
            "payload": {
                **payload,
                "discovery_keys": [native],
                "discovery_sources": [
                    {
                        "source_id": candidate["source"],
                        "record_id": native,
                        "url": payload["source_url"],
                        "license": payload["license"],
                    }
                ],
                "discovery_status": "source_assertion",
                "open_status": "unknown",
            },
        }
        chains = {
            r.get("chain_id"): r.get("chain_name")
            for r in existing
            if r.get("chain_id") and names_compatible(payload["name"], r.get("chain_name") or "")
        }
        if len(chains) == 1:
            chain_id, chain_name = next(iter(chains.items()))
            record["payload"].update(chain_id=chain_id, chain_name=chain_name)
        groups.append(record)
        crosswalk.append(
            {
                "source_key": native,
                "proposed_key": native,
                "state": "new",
                "evidence": "provider_identity_and_full_address",
            }
        )
    return {
        "records": groups + list(updates.values()),
        "crosswalk": crosswalk,
        "reviews": reviews,
        "excluded": excluded,
        "summary": {
            "existing_records": len(existing),
            "candidate_assertions": len(candidates),
            "new_records": len(groups),
            "matched_assertions": sum(c["state"] != "new" for c in crosswalk),
            "review_assertions": len(reviews),
            "excluded_assertions": len(excluded),
            "census_complete": False,
            "state": "IA",
        },
    }
