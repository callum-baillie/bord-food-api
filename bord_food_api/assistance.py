"""Food assistance source assertions, separate from groceries and household pantry data.

No networking. OSM assertions use different kinds/packs from permissively licensed
sources. Missing fields stay unknown; office hours never become distribution hours.
"""

import copy
import json
import math
import re
from datetime import UTC, datetime

from .domain import US_STATES
from .store_enrichment import normalize
from .store_hours import valid_timezone

TYPES = frozenset(
    {
        "pantry",
        "food_bank",
        "meal",
        "community_fridge",
        "mobile_pantry",
        "food_assistance_unspecified",
    }
)
FEED_TYPES = {
    "food_pantry": "pantry",
    "food_bank": "food_bank",
    "soup_kitchen": "meal",
    "mobile_pantry": "mobile_pantry",
    "community_fridge": "community_fridge",
}
ASSISTANCE_KINDS = {
    f"{prefix}{name}": pack
    for prefix, pack in [("assistance_", "assistance"), ("osm_assistance_", "assistance_osm")]
    for name in ("site", "service", "event", "evidence")
}


def kind_for(source, entity):
    return ("osm_assistance_" if source == "osm_food_assistance" else "assistance_") + entity


def iso_time(value, *, allow_future=False):
    """Only retain explicit, credible source clocks, never retrieval as verification."""
    try:
        if not isinstance(value, str) or not value:
            return None
        date = datetime.fromisoformat(value)
        if len(value) == 10:
            date = date.replace(tzinfo=UTC)
        if date.tzinfo is None or (
            not allow_future and date.timestamp() > datetime.now(UTC).timestamp() + 300
        ):
            return None
        return date.isoformat()
    except (ValueError, OverflowError):
        return None


def safe_text(value, maximum=4000):
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value.strip()[:maximum] or None


def optional_contact(field, value):
    if not value:
        return None
    try:
        return normalize(field, value)
    except (ValueError, TypeError, KeyError):
        return None


def coordinates(lat, lon):
    try:
        # bool/None/NaN and out-of-range values must not become a real map point.
        if isinstance(lat, bool) or isinstance(lon, bool):
            return None
        lat, lon = float(lat), float(lon)
        if not (
            math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            return None
        return {"latitude": lat, "longitude": lon}
    except (ValueError, TypeError):
        return None


def provenance(source, key, *, license, attribution, source_url, upstream=None, verified=None):
    return {
        "source_id": source,
        "record_id": str(key),
        "license": license,
        "attribution": attribution,
        "source_url": source_url,
        "upstream_source": upstream,
        "source_claimed_verified_at": iso_time(verified),
    }


def base_payload(name, address, point, reference, *, schedule=None, verified=None):
    return {
        "name": safe_text(name, 500),
        "address": address,
        "coordinates": point,
        "country": "US",
        "source_refs": [reference],
        "source_id": reference["source_id"],
        "source_license": reference["license"],
        "attribution": reference["attribution"],
        "source_url": reference["source_url"],
        "last_verified_at": None,
        "source_claimed_verified_at": iso_time(verified),
        "data_quality": "unverified",
        "operating_status": "unknown",
        "permanently_closed": None,
        "public_access": "unknown",
        "inventory_status": "unknown",
        "schedule": {
            "raw": safe_text(schedule),
            "scope": "unspecified",
            "timezone": None,
            "exceptions": [],
            "verified_at": None,
            "status": "unverified",
        },
        "field_provenance": {},
        "field_conflicts": [],
        "needs_confirmation": True,
    }


def annotate_fields(payload, reference):
    """Source reporting is not independent verification, even with a provider score."""
    payload.setdefault("field_conflicts", [])
    payload["field_provenance"] = {
        field: {"status": "source_reported", "sources": [reference], "verified_at": None}
        for field in (
            "name",
            "address",
            "coordinates",
            "phone",
            "email",
            "website",
            "schedule",
            "timezone",
            "operating_status",
            "eligibility",
            "application_process",
            "documents_required",
            "service_area",
            "languages",
            "accessibility",
            "appointment_required",
        )
        if payload.get(field) is not None
    }
    return payload


def records_for_site(source, key, site, services, events=()):
    """Local native links are resolved into durable IDs by the platform publisher."""
    yield {"kind": kind_for(source, "site"), "source_key": str(key), "payload": site}
    for index, service in enumerate(services):
        service_key = str(service.pop("source_key", f"{key}:service:{index}"))
        yield {
            "kind": kind_for(source, "service"),
            "source_key": service_key,
            "payload": {
                **service,
                "site_key": str(key),
                "source_refs": site["source_refs"],
                "name": site["name"],
                "address": site["address"],
                "coordinates": site["coordinates"],
                "source_license": site["source_license"],
                "source_id": source,
            },
        }
    for event in events:
        event = dict(event)
        event_key = str(event.pop("source_key"))
        starts, ends = (
            iso_time(event.get("starts_at"), allow_future=True),
            iso_time(event.get("ends_at"), allow_future=True),
        )
        if (
            "T" not in str(event.get("starts_at"))
            or "T" not in str(event.get("ends_at"))
            or not starts
            or not ends
            or datetime.fromisoformat(ends) <= datetime.fromisoformat(starts)
        ):
            raise ValueError("assistance_event_requires_ordered_explicit_offset_times")
        yield {
            "kind": kind_for(source, "event"),
            "source_key": event_key,
            "payload": {
                **event,
                "starts_at": starts,
                "ends_at": ends,
                "site_key": str(key),
                "source_refs": site["source_refs"],
                "source_license": site["source_license"],
                "address": event.get("address") or site["address"],
                "coordinates": event.get("coordinates") or site["coordinates"],
                "status": event.get("status", "unknown"),
                "name": site["name"],
            },
        }


def parse_feed_resource(row, *, state, approved_sources):
    source = "feed_america"
    if row.get("resource_type") not in FEED_TYPES:
        return
    if row.get("state") != state:
        raise ValueError("assistance_source_state_mismatch")
    upstream = row.get("data_source")
    if upstream not in approved_sources:
        raise ValueError("assistance_upstream_rights_unreviewed")
    key = row.get("id")
    if key is None or not str(key) or not row.get("name"):
        raise ValueError("assistance_native_identity_missing")
    ref = provenance(
        source,
        key,
        license="CC-BY-4.0",
        attribution="Data from Feed America, feedam.org, EIN 92-1761881",
        source_url=f"https://feedam.org/api/resources/{key}",
        upstream=upstream,
        verified=row.get("last_verified_date"),
    )
    address = {
        "street": safe_text(row.get("address"), 500),
        "city": safe_text(row.get("city"), 200),
        "region": state,
        "postal_code": safe_text(row.get("zip"), 20),
        "country": "US",
    }
    site = base_payload(
        row["name"],
        address,
        coordinates(row.get("lat"), row.get("lng")),
        ref,
        schedule=row.get("hours_json") or row.get("hours"),
        verified=row.get("last_verified_date"),
    )
    site.update(
        phone=optional_contact("phone", row.get("phone")),
        email=optional_contact("email", row.get("email")),
        website=optional_contact("website", row.get("website")),
        operator=safe_text(row.get("organization")),
        service_types=[FEED_TYPES[row["resource_type"]]],
    )
    if row.get("timezone") and valid_timezone(row["timezone"]):
        site["timezone"] = site["schedule"]["timezone"] = row["timezone"]
    if row.get("permanently_closed") is True:
        site.update(operating_status="permanently_closed", permanently_closed=True)
    service = {
        "type": FEED_TYPES[row["resource_type"]],
        "eligibility": safe_text(row.get("eligibility")),
        "application_process": safe_text(row.get("application_process")),
        "documents_required": safe_text(row.get("documents_required")),
        "service_area": safe_text(row.get("service_area")),
        "languages": row.get("languages"),
        "appointment_required": row.get("appointment_required")
        if type(row.get("appointment_required")) is bool
        else None,
        "schedule": {
            **site["schedule"],
            "raw": safe_text(row.get("distribution_hours")),
            "scope": "service",
        },
        "inventory_status": "unknown",
        "public_access": "unknown",
        "data_quality": "unverified",
    }
    # Generic directory hours can mean office hours, especially for warehouses.
    annotate_fields(site, ref)
    annotate_fields(service, ref)
    yield from records_for_site(source, key, site, [service])


def parse_osm_element(row, *, state):
    tags = row.get("tags") or {}
    if tags.get("amenity") == "food_sharing":
        service_type = (
            "community_fridge"
            if tags.get("food_sharing") == "community_fridge"
            else "food_assistance_unspecified"
        )
    elif tags.get("social_facility") == "soup_kitchen":
        service_type = "meal"
    elif tags.get("social_facility") == "food_bank":
        # The OSM tag covers both warehouses and public pantries. Do not guess.
        service_type = "food_assistance_unspecified"
    else:
        return
    if row.get("type") not in {"node", "way", "relation"} or type(row.get("id")) is not int:
        raise ValueError("assistance_osm_native_identity_missing")
    if tags.get("addr:state") and tags["addr:state"] != state:
        raise ValueError("assistance_source_state_mismatch")
    source = "osm_food_assistance"
    key = f"{row['type']}/{row['id']}"
    ref = provenance(
        source,
        key,
        license="ODbL-1.0",
        attribution="© OpenStreetMap contributors",
        source_url="https://www.openstreetmap.org/" + key,
        verified=tags.get("check_date"),
    )
    address = {
        "street": safe_text(
            tags.get("addr:street_address")
            or " ".join(str(tags.get(k, "")) for k in ("addr:housenumber", "addr:street")).strip(),
            500,
        ),
        "city": safe_text(tags.get("addr:city"), 200),
        "region": state,
        "postal_code": safe_text(tags.get("addr:postcode"), 20),
        "country": "US",
    }
    center = row.get("center") or row
    site = base_payload(
        tags.get("name"),
        address,
        coordinates(center.get("lat"), center.get("lon")),
        ref,
        schedule=tags.get("opening_hours"),
        verified=tags.get("check_date"),
    )
    site.update(
        phone=optional_contact("phone", tags.get("contact:phone") or tags.get("phone")),
        email=optional_contact("email", tags.get("contact:email") or tags.get("email")),
        website=optional_contact("website", tags.get("contact:website") or tags.get("website")),
        operator=safe_text(tags.get("operator")),
        accessibility={"wheelchair": tags.get("wheelchair")},
        service_types=[service_type],
        source_properties=tags,
    )
    if tags.get("timezone") and valid_timezone(tags["timezone"]):
        site["timezone"] = site["schedule"]["timezone"] = tags["timezone"]
    site["public_access"] = "restricted" if tags.get("access") in {"private", "no"} else "unknown"
    annotate_fields(site, ref)
    yield from records_for_site(
        source,
        key,
        site,
        [
            {
                "type": service_type,
                "schedule": {
                    "raw": None,
                    "scope": "service",
                    "timezone": site.get("timezone"),
                    "status": "unverified",
                    "verified_at": None,
                },
                "eligibility": safe_text(tags.get("social_facility:for")),
                "appointment_required": None,
                "public_access": site["public_access"],
                "inventory_status": "unknown",
            }
        ],
    )


def freshness(row, *, now):
    """Dynamic freshness can age without catalog writes or fake verification dates."""
    result = copy.deepcopy(row)
    schedule = result.get("schedule")
    if isinstance(schedule, dict):
        confirmed = iso_time(schedule.get("verified_at"))
        age = now - datetime.fromisoformat(confirmed).timestamp() if confirmed else None
        schedule["status"] = (
            "stale"
            if age is not None and age > 7 * 86400
            else "verified"
            if age is not None
            else "unverified"
        )
        schedule["needs_confirmation"] = schedule["status"] != "verified"
    result["needs_confirmation"] = result.get("data_quality") != "verified" or bool(
        isinstance(schedule, dict) and schedule.get("needs_confirmation")
    )
    if result.get("kind") in {"assistance_event", "osm_assistance_event"} and result.get("ends_at"):
        result["expired"] = datetime.fromisoformat(result["ends_at"]).timestamp() < now
    return result


def validate_states(states):
    if (
        not isinstance(states, list)
        or not states
        or len(states) > 51
        or len(set(states)) != len(states)
        or set(states) - (US_STATES | {"DC"})
    ):
        raise ValueError("assistance_explicit_us_states_required")
    return states


def duplicate_candidates(sites):
    """Review suggestions only; never merge co-located but different services or ODbL fields."""
    groups = {}
    for row in sites:
        address = row.get("address") or {}
        key = tuple(
            re.sub(r"[^a-z0-9]", "", str(v).lower())
            for v in (
                row.get("name", ""),
                address.get("street", ""),
                address.get("city", ""),
                address.get("region", ""),
            )
        )
        if all(key):
            groups.setdefault(key, []).append(row["id"])
    return [
        {
            "site_ids": ids,
            "reason": "same_normalized_name_and_premises",
            "action": "review_required",
        }
        for ids in groups.values()
        if len(ids) > 1
    ]


def retain_source_update(previous, incoming):
    """Keep identity relocations for review and retain changed field alternatives."""
    result = dict(incoming)
    old_address, new_address = previous.get("address") or {}, incoming.get("address") or {}
    if any(
        old_address.get(k)
        and new_address.get(k)
        and re.sub(r"\W", "", str(old_address[k]).casefold())
        != re.sub(r"\W", "", str(new_address[k]).casefold())
        for k in ("street", "city", "region")
    ):
        # Hold the whole factual update; do not attach new-premises phones to an old site.
        result = {k: v for k, v in previous.items() if k not in {"id", "content_revision"}}
        result["identity_review"] = {
            "reason": "source_premises_changed",
            "candidate": incoming,
            "action": "review_required",
        }
        return result
    conflicts = list(previous.get("field_conflicts", []))
    for field in ("phone", "email", "website", "schedule", "operating_status"):
        old, new = previous.get(field), incoming.get(field)
        if old and new and old != new:
            item = {
                "field": field,
                "previous_value": old,
                "source_value": new,
                "resolution": "source_revision_changed_unverified",
            }
            if item not in conflicts:
                conflicts.append(item)
    result["field_conflicts"] = conflicts[-100:]
    if previous.get("identity_review"):
        result["identity_review"] = previous["identity_review"]
    return result
