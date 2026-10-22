"""Documented retained-place adapters. No crawler, paid connector or data download.

OSM, Overture and Foursquare observations remain provider assertions, never a
retailer inventory. A crosswalk must independently resolve the physical branch.
"""

import re
from urllib.parse import urlsplit

from .store_enrichment import assertion, epoch


def overture_lineage(row, field):
    """A computed Overture confidence/status is not another provider fact vote."""
    property_name = {"phone": "phones", "email": "emails", "website": "websites"}.get(field, field)
    sources = row.get("sources") or []
    specific = [
        s for s in sources if str(s.get("property") or "").rstrip("/").endswith("/" + property_name)
    ]
    applicable = specific or [s for s in sources if not s.get("property")]
    providers = {str(s.get("dataset") or s.get("provider") or "").lower() for s in applicable}
    providers -= {"overture", "overture-signals", ""}
    if len(providers) != 1:
        return None
    provider = next(iter(providers))
    if "foursquare" in provider or provider == "fsq":
        return "foursquare_os"
    if "openstreetmap" in provider or provider == "osm":
        return "openstreetmap"
    if provider.replace("_", "") in {"alltheplaces", "atp"}:
        websites = row.get("websites") or []
        host = (urlsplit(websites[0]).hostname or "").removeprefix("www.") if websites else ""
        return "retailer:" + host if host else None
    return "provider:" + provider


def osm_fields(tags):
    values = {}
    for field, keys in {
        "phone": ("contact:phone", "phone"),
        "email": ("contact:email", "email"),
        "website": ("contact:website", "website"),
        "opening_hours": ("opening_hours",),
        "timezone": ("timezone",),
        "pickup_links": ("contact:website:pickup", "website:pickup"),
        "delivery_links": ("contact:website:delivery", "website:delivery"),
    }.items():
        value = next((tags[k] for k in keys if tags.get(k)), None)
        if value is not None:
            values[field] = value
    access = {
        k: v
        for k, v in tags.items()
        if k
        in {
            "wheelchair",
            "wheelchair:description",
            "wheelchair:access",
            "toilets:wheelchair",
            "hearing_loop",
            "tactile_paving",
            "ramp",
            "automatic_door",
            "door:width",
            "level",
            "step_count",
        }
    }
    if access:
        values["accessibility"] = access
    # Lifecycle tags report an assertion of non-use, not an exact closure date.
    if tags.get("abandoned:shop") or tags.get("demolished:shop"):
        values["operating_status"] = "permanently_closed"
    elif tags.get("disused:shop"):
        values["operating_status"] = "not_operating_unspecified"
    if tags.get("entrance") and tags.get("entrance") != "no":
        values["entrances"] = [
            {
                "kind": tags["entrance"],
                "access": tags.get("access"),
                "wheelchair": tags.get("wheelchair"),
                "association": "business_feature_only_requires_review",
            }
        ]
    return values


def source_assertions(
    source, row, store, *, record_id, source_url, checked_at, branch_match, source_revision=None
):
    """Turn an identity-bound provider row into field-specific retained assertions."""
    values = {}
    lineage, observed = source, None
    if source == "openstreetmap":
        tags = row.get("tags") or row.get("source_record") or row
        values = osm_fields(tags)
        observed = row.get("timestamp") or tags.get("check_date") or tags.get("survey:date")
        origin = tags.get("source") or tags.get("source:contact")
        if isinstance(origin, str) and origin.startswith(("https://", "http://")):
            lineage = "retailer:" + (urlsplit(origin).hostname or "").removeprefix("www.")
    elif source == "overture_places":
        for field, key in (("phone", "phones"), ("email", "emails"), ("website", "websites")):
            if row.get(key):
                values[field] = row[key][0]
        if row.get("operating_status") in {"open", "temporarily_closed", "permanently_closed"}:
            values["operating_status"] = row["operating_status"]
        sources = row.get("sources") or []
        # A combined place record is not an independent vote from its providers.
        providers = {str(s.get("dataset") or s.get("provider") or "").lower() for s in sources}
        if any("foursquare" in p or p == "fsq" for p in providers):
            lineage = "foursquare_os"
        elif any("osm" in p or "openstreetmap" in p for p in providers):
            lineage = "openstreetmap"
        elif len(providers) != 1 or not providers - {""}:
            lineage = None
        observed = max((epoch(s.get("update_time")) or 0 for s in sources), default=0) or None
    elif source == "foursquare_os":
        for field, key in (("phone", "tel"), ("email", "email"), ("website", "website")):
            if row.get(key):
                values[field] = row[key]
        if row.get("date_closed"):
            values["operating_status"] = "permanently_closed"
        observed = row.get("date_refreshed")
        # date_closed is a provider reporting date, not the store's actual date.
    else:
        raise ValueError("unsupported_place_source")
    rows = [
        assertion(
            store["id"],
            field,
            value,
            source_id=source,
            record_id=record_id,
            source_url=source_url,
            checked_at=checked_at,
            observed_at=observed,
            lineage=overture_lineage(row, field) if source == "overture_places" else lineage,
            branch_match=branch_match,
            source_revision=source_revision,
            source_path=field,
            country=store.get("country", "US"),
        )
        for field, value in values.items()
    ]
    name = str((row.get("names") or {}).get("primary") or row.get("name") or "")
    if re.search(
        r"\b(?:pharmacy|vision center|garden center|money transfer|fuel station)\b",
        name,
        re.IGNORECASE,
    ):
        for item in rows:
            if item["field"] == "phone":
                item.update(scope="department", contact_role="department")
    return rows


def place_candidate(source, row):
    if source == "overture_places":
        identity = row["id"]
        addresses = row.get("addresses") or []
        address = addresses[0] if len(addresses) == 1 else {}
        names = row.get("names") or {}
        geometry = row.get("geometry") or {}
        coords = geometry.get("coordinates") if geometry.get("type") == "Point" else None
        payload = {
            "name": names.get("primary"),
            "country": address.get("country"),
            "address": {
                "street": address.get("freeform"),
                "city": address.get("locality"),
                "region": address.get("region"),
                "postal_code": address.get("postcode"),
            },
            "longitude": coords[0] if coords else None,
            "latitude": coords[1] if coords else None,
        }
    elif source == "foursquare_os":
        identity = row["fsq_place_id"]
        payload = {
            "name": row.get("name"),
            "country": row.get("country"),
            "address": {
                "street": row.get("address"),
                "city": row.get("locality"),
                "region": row.get("region"),
                "postal_code": row.get("postcode"),
            },
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
        }
    else:
        raise ValueError("unsupported_place_source")
    if not isinstance(identity, str) or not identity:
        raise ValueError("place_requires_native_identifier")
    category, reason = "review", "identity_crosswalk_required"
    if source == "overture_places" and "taxonomy" in row:
        primary = str((row.get("taxonomy") or {}).get("primary") or "")
        if not (
            primary.endswith("grocery_store")
            or primary in {"supermarket", "superstore", "warehouse_club_store", "department_store"}
        ):
            category, reason = "exclude", "outside_grocery_place_scope"
    return {
        "source": source,
        "source_key": identity,
        "payload": payload,
        "source_record": row,
        "category": category,
        "reason": reason,
    }


def osm_verification_query(native_ids):
    """Target known provider IDs, so lifecycle changes are visible after shop removal."""
    import re

    ids = list(dict.fromkeys(native_ids))
    if not 1 <= len(ids) <= 50 or any(
        not isinstance(v, str) or not re.fullmatch(r"(node|way|relation)/[1-9][0-9]*", v)
        for v in ids
    ):
        raise ValueError("bounded_osm_native_ids_required")
    clauses = "".join(
        kind + "(" + identity + ");" for kind, identity in (v.split("/") for v in ids)
    )
    return "[out:json][timeout:25];(" + clauses + ");out meta center tags;"
