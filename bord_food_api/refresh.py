"""Deterministic field evidence and bounded detail-refresh planning; no network work.

Local first-seen/change clocks schedule audits. They never assert retailer verification.
Only an explicitly supplied last_detail_checked_at records an actual detail check.
"""

import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

NORMALIZER_VERSION = "store-groups-v2"
DAY = 86400
GROUP_FIELDS = {
    "identity": ("chain_id", "chain_key", "banner", "operator", "brand", "store_number"),
    "name": ("name", "alternate_names"),
    "location": (
        "address",
        "latitude",
        "longitude",
        "coordinates",
        "region",
        "country_code",
        "postal_code",
    ),
    "contact": ("phone", "website", "email"),
    "hours": ("hours", "opening_hours", "department_hours", "hours_exceptions", "timezone"),
    "services": (
        "services",
        "amenities",
        "pickup_links",
        "delivery_links",
        "departments",
        "entrances",
        "accessibility",
        "aisle_category_mappings",
    ),
    "operating_status": ("operating_status", "permanently_closed", "lifecycle"),
    "maps": ("map_url", "map_asset_id", "map_version", "map_hash"),
}
INTERVAL_DAYS = {
    "identity": 90,
    "name": 90,
    "location": 180,
    "contact": 30,
    "hours": 60,
    "services": 30,
    "maps": 90,
    "operating_status": 14,
}
IGNORED_FIELDS = {
    "retrieved_at",
    "fetched_at",
    "last_checked_at",
    "job_id",
    "download_progress",
    "source_record",
    "source_properties",
}
TRACKING_PARAMETERS = {"fbclid", "gclid", "msclkid", "dclid"}


def _normalize(value, *, field="", depth=0):
    if depth > 16:
        raise ValueError("Field evidence exceeds nesting limit")
    if isinstance(value, str):
        if len(value) > 65536:
            raise ValueError("Field evidence exceeds string limit")
        value = " ".join(unicodedata.normalize("NFC", value).split())
        if field == "phone":
            text = value.casefold().removeprefix("tel:")
            match = re.search(r"(?:ext\.?|extension|x|#|;ext=)\s*(\d+)$", text)
            extension = match[1] if match else ""
            number = re.sub(r"\D", "", text[: match.start()] if match else text)
            return number + (";ext=" + extension if extension else "") or None
        if field in {"website", "map_url"} and value:
            parsed = urlsplit(value)
            query = [
                (key, item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if not key.casefold().startswith("utm_")
                and key.casefold() not in TRACKING_PARAMETERS
            ]
            return urlunsplit(
                (
                    parsed.scheme.casefold(),
                    parsed.netloc.casefold(),
                    parsed.path.rstrip("/"),
                    urlencode(sorted(query)),
                    "",
                )
            )
        return value.casefold() or None
    if isinstance(value, dict):
        if len(value) > 2048:
            raise ValueError("Field evidence exceeds collection limit")
        return {
            key: normalized
            for key, item in sorted(value.items())
            if key not in IGNORED_FIELDS
            and (normalized := _normalize(item, field=key, depth=depth + 1)) is not None
        }
    if isinstance(value, (list, tuple)):
        if len(value) > 2048:
            raise ValueError("Field evidence exceeds collection limit")
        items = [_normalize(item, field=field, depth=depth + 1) for item in value]
        # These groups represent sets; hours arrays can represent ordered schedules.
        if field in {"services", "amenities", "alternate_names"}:
            unique = {json.dumps(item, sort_keys=True): item for item in items}
            items = [unique[key] for key in sorted(unique)]
        return items
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite field evidence")
        return int(value) if value.is_integer() else value
    if value is None or isinstance(value, (bool, int)):
        return value
    raise TypeError("Unsupported field evidence type")


def _known(value):
    return value is not None and value != "" and value != {} and value != []


def field_groups(record):
    """Return versioned normalized hashes with native known/unknown status."""
    result = {}
    for group, fields in GROUP_FIELDS.items():
        values = {
            field: normalized
            for field in fields
            if (normalized := _normalize(record.get(field), field=field)) is not None
        }
        status = "known" if any(_known(value) for value in values.values()) else "unknown"
        content = json.dumps(
            {"version": NORMALIZER_VERSION, "group": group, "values": values},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        result[group] = {"hash": hashlib.sha256(content.encode()).hexdigest(), "status": status}
    return result


def _metadata(record):
    return record.get("field_refresh", {}).get("groups", record.get("field_groups", {}))


def _time(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Field refresh timestamps must be finite UTC epoch seconds")
    return value


def plan_store_refresh(
    previous,
    incoming,
    now,
    *,
    required_groups=(),
    watched=False,
    crawl_authorized=False,
    required_fields=(),
    maps_requested=False,
):
    """Plan justified changed/missing/due groups without enqueuing any work.

    Required groups/fields are operator policy. Unknown optional groups never
    cause detail work. An authorization gate empties detail_groups when disabled.
    Map not-found checks back off 30, 90, then 180 days; no absence proves closure.
    """
    now = _time(now)
    if now is None:
        raise ValueError("A current UTC timestamp is required")
    previous = previous or {}
    old = field_groups(previous)
    current = field_groups(incoming)
    previous_metadata = _metadata(previous)
    incoming_metadata = _metadata(incoming)
    required = set(required_groups)
    missing_fields = set()
    for field in required_fields:
        match = next((group for group, fields in GROUP_FIELDS.items() if field in fields), None)
        if match is None:
            raise ValueError("Unknown required store field")
        if not _known(_normalize(incoming.get(field), field=field)):
            required.add(match)
            missing_fields.add(match)
    if maps_requested:
        required.add("maps")
    if required - GROUP_FIELDS.keys():
        raise ValueError("Unknown required store group")
    changed, candidates, reasons, due_at, groups = [], [], {}, {}, {}
    for group in GROUP_FIELDS:
        prior = previous_metadata.get(group, {})
        reported = incoming_metadata.get(group, {})
        interval = INTERVAL_DAYS[group] * DAY
        if group == "hours" and watched:
            interval = 14 * DAY
        is_changed = old[group]["hash"] != current[group]["hash"]
        if is_changed:
            changed.append(group)
        first_seen = _time(prior.get("first_seen_at"))
        if first_seen is None:
            first_seen = now
        changed_at = now if is_changed else _time(prior.get("last_changed_at"))
        checked = _time(reported.get("last_detail_checked_at", prior.get("last_detail_checked_at")))
        if checked is not None and checked > now:
            raise ValueError("Detail verification timestamp cannot be in the future")
        anchor = checked if checked is not None else first_seen
        negative = group == "maps" and (
            incoming.get("map_status") == "not_found"
            or reported.get("status") == "not_found"
            or reported.get("evidence_status", prior.get("evidence_status")) == "not_found"
        )
        attempts = reported.get("negative_attempts", prior.get("negative_attempts", 0))
        if type(attempts) is not int or attempts < 0:
            raise ValueError("Map negative attempts must be a nonnegative integer")
        if group == "maps" and negative:
            attempts = max(attempts, 1)
            interval = (30, 90, 180)[min(max(attempts, 1) - 1, 2)] * DAY
        known = current[group]["status"] == "known"
        next_due = anchor + interval if known or group in required else None
        reason = None
        if ((not known and group in required) or group in missing_fields) and (
            not negative or next_due <= now
        ):
            reason = "negative_retry_due" if negative else "missing_required"
        elif previous and is_changed and known:
            reason = "changed"
        elif previous and known and next_due <= now:
            reason = "audit_due"
        elif group in required and negative and next_due <= now:
            reason = "negative_retry_due"
        if reason:
            candidates.append(group)
            reasons[group] = reason
        due_at[group] = next_due
        groups[group] = {
            **current[group],
            "first_seen_at": first_seen,
            "last_changed_at": changed_at,
            "last_detail_checked_at": checked,
            "next_due_at": next_due,
            "negative_attempts": attempts if group == "maps" else 0,
            "evidence_status": "not_found"
            if group == "maps" and negative
            else current[group]["status"],
        }
    return {
        "normalizer_version": NORMALIZER_VERSION,
        "changed_groups": changed,
        "detail_groups": candidates if crawl_authorized else [],
        "detail_candidates": candidates,
        "detail_reasons": reasons,
        "due_at": due_at,
        "groups": groups,
        "requests": [],
        "crawl_authorized": bool(crawl_authorized),
    }
