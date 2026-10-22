"""Source-backed store field assertions, conservative promotion, and conflict retention.

No networking. Model scores never authorize promotion or establish source independence.
The serving catalog remains immutable; publication uses a private pack replacement.
"""

import copy
import hashlib
import ipaddress
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from .domain import content_hash
from .store_hours import (
    derive_timezone,
    fuller_schedule,
    holiday_exceptions,
    osm_hours,
    structured_hours,
    valid_timezone,
)

VERSION = "store-field-evidence-v4"
FIELDS = frozenset(
    {
        "phone",
        "email",
        "website",
        "opening_hours",
        "hours_exceptions",
        "timezone",
        "operating_status",
        "pickup_links",
        "delivery_links",
        "departments",
        "entrances",
        "accessibility",
        "aisle_category_mappings",
    }
)
REVIEW_FIELDS = frozenset({"entrances", "aisle_category_mappings"})
# A validated provider branch report may fill a gap, without becoming verification.
# Closure and reviewed spatial fields keep their stronger gates.
REPORTED_FIELDS = FIELDS - REVIEW_FIELDS - {"operating_status"}
REPORT_SOURCES = frozenset(
    {"retailer_page", "openstreetmap", "overture_places", "foursquare_os", "all_the_places"}
)
FRESHNESS = {
    "phone": 30,
    "email": 30,
    "website": 30,
    "operating_status": 30,
    "opening_hours": 30,
    "hours_exceptions": 14,
    "pickup_links": 30,
    "delivery_links": 30,
}
STATUS = frozenset({"open", "temporarily_closed", "permanently_closed", "unknown"})


def epoch(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return None
            value = parsed.timestamp()
        except ValueError:
            return None
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        return None
    return value / 1000 if value > 1e12 else value


def public_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("invalid_contact_url")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid_contact_url")
    if parsed.hostname == "localhost" or parsed.hostname.endswith((".local", ".internal")):
        raise ValueError("nonpublic_contact_url")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise ValueError("nonpublic_contact_url")
    except ValueError as error:
        if str(error) == "nonpublic_contact_url":
            raise
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(
        re.search(r"password|secret|token|session|api.?key|auth", k, re.IGNORECASE)
        for k, _ in pairs
    ):
        raise ValueError("credential_bearing_url")
    pairs = [
        (k, v)
        for k, v in pairs
        if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
    ]
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            urlencode(sorted(pairs)),
            "",
        )
    )


def normalize(field, value, country="US"):
    if field not in FIELDS:
        raise ValueError("unsupported_store_field")
    if field == "phone":
        if not isinstance(value, str):
            raise ValueError("invalid_phone")
        raw = unquote(value.strip().removeprefix("tel:"))
        ext = re.search(r"(?:ext\.?|x|;ext=)\s*(\d+)$", raw, re.IGNORECASE)
        number = re.sub(r"\D", "", raw[: ext.start()] if ext else raw)
        if country == "US" and len(number) == 10:
            number = "1" + number
        if not 8 <= len(number) <= 15 or not (
            raw.startswith("+") or country == "US" and len(number) == 11 and number.startswith("1")
        ):
            raise ValueError("invalid_phone")
        if (
            number.startswith("0")
            or country == "US"
            and len(number) == 11
            and (number[1] not in "23456789" or number[4] not in "23456789")
        ):
            raise ValueError("invalid_phone")
        return "+" + number + (";ext=" + ext[1] if ext else "")
    if field == "email":
        value = unquote(value) if isinstance(value, str) else value
        if not isinstance(value, str) or not re.fullmatch(
            r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value.strip().removeprefix("mailto:")
        ):
            raise ValueError("invalid_email")
        local, domain = value.strip().removeprefix("mailto:").rsplit("@", 1)
        return local + "@" + domain.lower()
    if field == "website":
        return public_url(value)
    if field == "timezone":
        if not (zone := valid_timezone(value)):
            raise ValueError("invalid_iana_timezone")
        return zone
    if field == "operating_status":
        if value not in STATUS or value == "unknown":
            raise ValueError("unknown_or_invalid_operating_status")
        return value
    if field == "opening_hours":
        if isinstance(value, str):
            return osm_hours(value)
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return osm_hours("; ".join(value))
        if (
            isinstance(value, list)
            and value
            and all(isinstance(v, dict) and "day" in v for v in value)
        ):
            # Round-trip through the strict schema parser; never trust pre-normalized data.
            names = {
                "Mo": "Monday",
                "Tu": "Tuesday",
                "We": "Wednesday",
                "Th": "Thursday",
                "Fr": "Friday",
                "Sa": "Saturday",
                "Su": "Sunday",
            }
            return structured_hours(
                [
                    {"dayOfWeek": names[v["day"]], "opens": v["opens"], "closes": v["closes"]}
                    for v in value
                ]
            )
        return structured_hours(value)
    if field == "hours_exceptions":
        if isinstance(value, list) and value and "valid_from" in value[0]:
            value = [
                {
                    "validFrom": r["valid_from"],
                    "validThrough": r["valid_through"],
                    "opens": r["opens"],
                    "closes": r["closes"],
                    "name": r.get("label"),
                }
                for r in value
            ]
        return holiday_exceptions(value)
    if field in {"pickup_links", "delivery_links"}:
        values = value if isinstance(value, list) else [value]
        return sorted({public_url(v) for v in values})
    # Complex structured fields remain bounded, lossless JSON assertions. Their
    # semantic scope comes from the adapter; entrances/mappings require review.
    if (
        not isinstance(value, (dict, list))
        or not value
        or len(json.dumps(value, allow_nan=False)) > 32768
    ):
        raise ValueError("invalid_or_oversized_structured_field")
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def assertion(
    store_id,
    field,
    value,
    *,
    source_id,
    record_id,
    source_url,
    checked_at,
    observed_at=None,
    lineage=None,
    branch_match="unresolved",
    authority="community",
    source_revision=None,
    source_path=None,
    country="US",
    scope="branch",
):
    raw = redact_evidence(value)
    row = {
        "store_id": store_id,
        "field": field,
        "raw_value": raw,
        "source_id": source_id,
        "record_id": redact_evidence(str(record_id)),
        "source_url": redact_evidence(source_url),
        "checked_at": epoch(checked_at),
        "observed_at": epoch(observed_at),
        "lineage": lineage,
        "branch_match": branch_match,
        "authority": authority,
        "source_revision": source_revision,
        "source_path": source_path,
        "scope": scope,
    }
    try:
        candidate = value
        if (
            field == "opening_hours"
            and source_id == "openstreetmap"
            and isinstance(value, str)
            and re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}(?:,\d{2}:\d{2}-\d{2}:\d{2})*", value)
        ):
            # An OSM time selector without weekdays applies every day. Bare
            # retailer prose has no such guarantee and keeps the strict parser.
            candidate = "Mo-Su " + value
            row["normalization_method"] = "osm_explicit_daily_time_selector"
        row["value"] = redact_evidence(normalize(field, candidate, country))
        if not row["value"]:
            raise ValueError("empty_value")
        row["validation"] = "valid"
    except (ValueError, TypeError, KeyError):
        row["value"] = None
        row["validation"] = "invalid_or_unsupported"
    # Content identity is stable across repeated retrievals. Every source version
    # remains separate, allowing superseded evidence to be inspected.
    row["id"] = content_hash(
        {k: v for k, v in row.items() if k not in {"checked_at", "observed_at"}}
    )
    return row


def reparse_assertions(store):
    """Revisit retained invalid syntax without changing observation/retrieval clocks."""
    result = []
    for old in store.get("field_evidence", []):
        if old.get("field") != "opening_hours" or old.get("validation") == "valid":
            continue
        row = assertion(
            store["id"],
            old["field"],
            old.get("raw_value"),
            **{
                k: old.get(k)
                for k in (
                    "source_id",
                    "record_id",
                    "source_url",
                    "checked_at",
                    "observed_at",
                    "lineage",
                    "branch_match",
                    "authority",
                    "source_revision",
                    "source_path",
                    "scope",
                )
            },
            country=store.get("country", "US"),
        )
        if row["validation"] == "valid":
            row["reparsed_from"] = old["id"]
            row["withdrawn"] = old.get("withdrawn", False)
            result.append(row)
    return result


def snapshot_assertions(store, *, source_id=None, record_id=None, checked_at=None):
    refs = store.get("source_refs") or []
    first = refs[0] if refs else {}
    url = store.get("source_url") or store.get("website") or ""
    source_id = source_id or (
        "openstreetmap" if "openstreetmap.org/" in url else first.get("source_id") or "unknown"
    )
    if source_id == "iowa_store_discovery":
        source_id = "openstreetmap" if "openstreetmap.org/" in url else "usda_snap_arcgis"
    lineage = (
        "retailer:" + (urlsplit(url).hostname or "unresolved").removeprefix("www.")
        if source_id == "all_the_places"
        else source_id
    )
    values = {
        k: store[k]
        for k in FIELDS
        if store.get(k) not in (None, "", "unknown") and k not in store.get("field_provenance", {})
    }
    if "opening_hours" not in values and store.get("hours"):
        values["opening_hours"] = store["hours"]
    return [
        assertion(
            store["id"],
            field,
            value,
            source_id=source_id,
            record_id=record_id or first.get("record_id") or store.get("source_id") or store["id"],
            source_url=url,
            checked_at=checked_at or store.get("source_observed_at"),
            observed_at=store.get("source_observed_at"),
            lineage=lineage,
            branch_match="canonical_source_identity",
            source_revision=first.get("release_id"),
            source_path="catalog/" + field,
            country=store.get("country", "US"),
        )
        for field, value in values.items()
    ]


def reconcile_fields(store, assertions, *, now, reviews=()):
    now = epoch(now)
    if now is None:
        raise ValueError("current_time_required")
    result = copy.deepcopy(store)
    retained = {}
    for row in [*store.get("field_evidence", []), *assertions]:
        if row.get("store_id") != store["id"] or row.get("field") not in FIELDS:
            raise ValueError("evidence_identity_or_field_mismatch")
        if row.get("id") in retained:
            previous = retained[row["id"]]
            if (epoch(row.get("checked_at")) or 0) <= (epoch(previous.get("checked_at")) or 0):
                continue
        retained[row["id"]] = copy.deepcopy(row)
    if len(retained) > 2048:
        raise ValueError("per_store_evidence_limit_archive_required")
    evidence = sorted(retained.values(), key=lambda r: r["id"])
    # ATP and provider copies of it can use a vendor/API host, a bare domain or
    # the retailer's new canonical host. These remain one retailer family.
    for row in evidence:
        if row.get("field") == "phone":
            from .chain_profiles import profile_for

            if row.get("value") in profile_for(store).get("chain_phones", ()):
                row["scope"] = "chain"
                row["contact_role"] = "customer_service"
            elif profile_for(store)["id"] == "aldi" and re.match(
                r"\+1(?:800|833|844|855|866|877|888)", str(row.get("value") or "")
            ):
                row["scope"] = "unresolved_contact_scope"
                row["contact_role"] = "toll_free_routing_not_confirmed_direct_branch"
        family = row.get("lineage")
        if store.get("chain_id") and (
            row.get("source_id") in {"all_the_places", "retailer_page"}
            or row.get("source_id") == "overture_places"
            and str(family or "").startswith("retailer:")
        ):
            family = "retailer-chain:" + store["chain_id"]
        row["verification_family"] = family
    reviewed = {}
    prior_reviews = [
        r for p in store.get("field_provenance", {}).values() for r in p.get("reviews", [])
    ]
    for review in [*prior_reviews, *reviews]:
        row = retained.get(review.get("assertion_id"))
        stamp = epoch(review.get("reviewed_at"))
        if (
            not row
            or not review.get("reviewer")
            or not review.get("reason")
            or stamp is None
            or stamp > now
            or review.get("decision") != "accept"
        ):
            raise ValueError("review_must_bind_retained_assertion_and_reviewer")
        reviewed[row["id"]] = review
    # A newer assertion supersedes the old assertion of this same field/provider
    # record. Retain both, but do not count history as independent corroboration.
    newest = {}
    for row in evidence:
        key = (row["field"], row["source_id"], row["record_id"])
        stamp = epoch(row.get("checked_at")) or epoch(row.get("observed_at")) or 0
        newest[key] = max(newest.get(key, 0), stamp)
    by_field = defaultdict(list)
    direct_checks = {}
    for row in evidence:
        stamp = epoch(row.get("checked_at"))
        if (
            row.get("source_id") == "retailer_page"
            and not row.get("withdrawn")
            and row.get("authority") == "official"
            and row.get("branch_match") == "exact_address"
            and row.get("validation") == "valid"
            and stamp is not None
            and 0 <= now - stamp <= FRESHNESS.get(row["field"], 90) * 86400
        ):
            key = (row["field"], row.get("verification_family"))
            direct_checks[key] = max(direct_checks.get(key, 0), stamp)
    for row in evidence:
        key = (row["field"], row["source_id"], row["record_id"])
        stamp = epoch(row.get("checked_at")) or epoch(row.get("observed_at"))
        row["superseded"] = bool(stamp is not None and stamp < newest[key])
        if (
            row.get("source_id") == "all_the_places"
            and row.get("verification_family")
            and stamp is not None
            and direct_checks.get((row["field"], row["verification_family"]), 0) > stamp
        ):
            row["superseded"] = True
            row["superseded_reason"] = "newer_direct_report_from_same_retailer_family"
        row["fresh"] = bool(
            stamp is not None and 0 <= now - stamp <= FRESHNESS.get(row["field"], 90) * 86400
        )
        row["eligible"] = (
            row.get("validation") == "valid"
            and row.get("branch_match")
            in {"exact_address", "canonical_source_identity", "reviewed_crosswalk"}
            and row.get("scope") == "branch"
            and row["fresh"]
            and not row["superseded"]
            and not row.get("withdrawn")
            and row.get("source_id") not in {"jev", "openai", "model"}
        )
        by_field[row["field"]].append(row)
    provenance, conflicts = {}, []
    for field, candidates in by_field.items():
        groups = defaultdict(list)
        for row in candidates:
            if row["eligible"]:
                groups[content_hash(row["value"])].append(row)
        chosen = None
        compatible_full = None
        state = "unverified" if any(r["fresh"] for r in candidates) else "stale"
        accepted_reviews = [
            r
            for r in candidates
            if r["id"] in reviewed and r["validation"] == "valid" and r["fresh"]
        ]
        if len({content_hash(r["value"]) for r in accepted_reviews}) > 1:
            raise ValueError("conflicting_operator_reviews")
        if accepted_reviews:
            chosen = accepted_reviews[0]
            state = "reviewed"
        elif len(groups) > 1:
            state = "conflicted"
            if field == "opening_hours":
                compatible_full = fuller_schedule([r for r in candidates if r["eligible"]])
                if compatible_full and compatible_full["source_id"] in REPORT_SOURCES:
                    chosen, state = compatible_full, "source_reported"
        elif len(groups) == 1 and field not in REVIEW_FIELDS:
            supporting = next(iter(groups.values()))
            roots = {
                r.get("verification_family")
                for r in supporting
                if r.get("verification_family")
                and r.get("verification_family")
                not in {"unknown", "unknown:unresolved", "retailer:unresolved"}
            }
            # Closure is especially consequential: require explicit official
            # evidence plus another provenance family, or an operator review.
            closure_ok = field != "operating_status" or any(
                r.get("authority") == "official" for r in supporting
            )
            if len(roots) >= 2 and closure_ok:
                chosen, state = supporting[0], "corroborated"
            elif field in REPORTED_FIELDS:
                reported = [r for r in supporting if r.get("source_id") in REPORT_SOURCES]
                reported.sort(key=lambda r: (r.get("authority") != "official", r["id"]))
                if reported:
                    try:
                        existing_value = (
                            normalize(field, result[field], store.get("country", "US"))
                            if result.get(field)
                            else None
                        )
                    except (ValueError, TypeError, KeyError):
                        existing_value = result.get(field)
                    old_state = store.get("field_provenance", {}).get(field, {}).get("status")
                    if (
                        existing_value is None
                        or existing_value == reported[0]["value"]
                        or old_state == "source_reported"
                    ):
                        chosen, state = reported[0], "source_reported"
        if len(groups) > 1:
            conflicts.append(
                {
                    "field": field,
                    "assertion_ids": [r["id"] for group in groups.values() for r in group],
                    "resolution": "compatible_partial_schedule"
                    if compatible_full
                    else "operator_review"
                    if state == "reviewed"
                    else "retained_existing_value",
                }
            )
        entry = {
            "status": state,
            "assertion_ids": [r["id"] for r in candidates],
            "supporting_ids": [],
            "verified_at": None,
            "method": None,
            "verified_until": None,
        }
        if chosen:
            supporting = groups.get(content_hash(chosen["value"]), [chosen])
            if state == "source_reported":
                supporting = [r for r in supporting if r.get("source_id") in REPORT_SOURCES]
            result[field] = copy.deepcopy(chosen["value"])
            entry["verified_until"] = min(
                (r.get("checked_at") or r.get("observed_at")) + FRESHNESS.get(field, 90) * 86400
                for r in supporting
            )
            method = "agreement_across_provenance_families"
            if state == "reviewed":
                method = "operator_review"
            elif state == "source_reported":
                method = (
                    "direct_official_branch_observation"
                    if chosen.get("authority") == "official"
                    else "provider_branch_report"
                )
            entry.update(
                supporting_ids=[r["id"] for r in supporting],
                verified_at=max(
                    (epoch(reviewed[r["id"]]["reviewed_at"]) for r in accepted_reviews), default=now
                ),
                method=method,
            )
            entry["last_checked_at"] = max(
                r.get("checked_at") or r.get("observed_at") for r in supporting
            )
            if compatible_full:
                entry["method"] = "fuller_compatible_weekly_source"
                entry["partial_supporting_ids"] = [
                    r["id"] for r in candidates if r["eligible"] and r not in supporting
                ]
            if state == "source_reported":
                entry["observed_until"] = entry["verified_until"]
                entry["verified_at"] = entry["verified_until"] = None
            old = store.get("field_provenance", {}).get(field, {})
            if old.get("status") == state and old.get("supporting_ids") == entry["supporting_ids"]:
                entry["verified_at"] = old.get("verified_at")
            if accepted_reviews:
                entry["reviews"] = [reviewed[r["id"]] for r in accepted_reviews]
        provenance[field] = entry
        if (
            not chosen
            and store.get("field_provenance", {}).get(field, {}).get("status") == "source_reported"
            and all(r.get("withdrawn") for r in candidates)
        ):
            baseline = store.get("field_baselines", {}).get(field, {})
            if baseline.get("present"):
                result[field] = copy.deepcopy(baseline["value"])
            else:
                result.pop(field, None)
            entry["status"] = "withdrawn"
    if not result.get("timezone") and (derived := derive_timezone(store)):
        result["timezone"] = derived["value"]
        provenance["timezone"] = {
            **derived,
            "verified_at": None,
            "assertion_ids": [],
            "supporting_ids": [],
        }
    elif (
        result.get("timezone")
        and store.get("field_provenance", {}).get("timezone", {}).get("status") == "derived"
        and "timezone" not in provenance
    ):
        provenance["timezone"] = copy.deepcopy(store["field_provenance"]["timezone"])
    elif result.get("timezone") and not valid_timezone(result["timezone"]):
        provenance["timezone"] = {
            "status": "invalid",
            "verified_at": None,
            "assertion_ids": [],
            "supporting_ids": [],
        }
    operating = result.get("operating_status", "unknown")
    if provenance.get("operating_status", {}).get("status") in {"corroborated", "reviewed"}:
        result["permanently_closed"] = operating == "permanently_closed"
        result["lifecycle"] = (
            "closed"
            if operating == "permanently_closed"
            else "active"
            if operating == "open"
            else "temporarily_closed"
        )
        result["closure_reported_at"] = min(
            (
                r.get("observed_at") or r.get("checked_at")
                for r in by_field["operating_status"]
                if r["id"] in provenance["operating_status"]["supporting_ids"]
            ),
            default=None,
        )
    else:
        result.setdefault("operating_status", "unknown")
        result.setdefault("permanently_closed", None)
    result["field_evidence"] = evidence
    result["field_provenance"] = provenance
    result["field_conflicts"] = conflicts
    result["field_enrichment_version"] = VERSION
    if result.get("opening_hours"):
        try:
            days = sorted({r["day"] for r in normalize("opening_hours", result["opening_hours"])})
        except (ValueError, TypeError, KeyError):
            days = []
        result["field_provenance"].setdefault("opening_hours", {}).update(
            covered_days=days,
            complete_week=len(days) == 7,
            unknown_days=[d for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su") if d not in days],
        )
    result["contact_channels"] = {
        **result.get("contact_channels", {}),
        "phones": [
            {
                "value": r["value"],
                "scope": r.get("scope"),
                "role": r.get("contact_role", "unspecified"),
                "assertion_id": r["id"],
                "source_id": r["source_id"],
            }
            for r in evidence
            if r["field"] == "phone" and r.get("validation") == "valid"
        ],
    }
    if result.get("phone"):
        try:
            selected_phone = normalize("phone", result["phone"])
        except ValueError:
            selected_phone = None
        scoped = [
            r
            for r in evidence
            if r["field"] == "phone"
            and r.get("value") == selected_phone
            and r.get("scope") != "branch"
        ]
        if scoped:
            result["contact_channels"]["phone"] = {
                "value": selected_phone,
                "scope": scoped[0]["scope"],
                "direct_branch_contact": False,
            }
    # Current-source assertions remain independently visible in source_record.
    result["last_verified_at"] = max(
        (p["verified_at"] for p in provenance.values() if p.get("verified_at")), default=None
    )
    return result


def enrichment_digest(records):
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def retain_verified_update(previous, incoming, source, *, checked_at=None, source_snapshot=None):
    """A roster update cannot silently erase field verification or conflicts."""
    if not previous.get("field_enrichment_version"):
        return incoming
    candidate = {
        **(source_snapshot if source_snapshot is not None else incoming),
        "id": previous["id"],
    }
    candidate["field_provenance"] = {
        k: v
        for k, v in candidate.get("field_provenance", {}).items()
        if candidate.get(k) == previous.get(k)
    }
    fresh = snapshot_assertions(candidate, source_id=source, checked_at=checked_at)
    base = copy.deepcopy(incoming)
    base["id"] = previous["id"]
    for key in (
        "field_evidence",
        "field_provenance",
        "field_baselines",
        "field_enrichment_version",
    ):
        base[key] = copy.deepcopy(previous.get(key, {} if key != "field_evidence" else []))
    for field, state in previous.get("field_provenance", {}).items():
        if field in previous and state.get("status") in {
            "corroborated",
            "reviewed",
            "derived",
            "conflicted",
            "source_reported",
        }:
            base[field] = copy.deepcopy(previous[field])
    if previous.get("quality"):
        from .store_quality import location_key

        if location_key(previous) == location_key(base) and location_key(base) is not None:
            base["quality"] = copy.deepcopy(previous["quality"])
    return reconcile_fields(
        base, fresh, now=checked_at or max((r.get("checked_at") or 0 for r in fresh), default=0)
    )


def publish_enrichment(platform, updates, *, base_generation, release, now, fence=None, hook=None):
    """Publish a single replacement stores pack, preserving identities/other packs."""
    import shutil
    import sqlite3
    import tempfile
    from contextlib import closing
    from pathlib import Path

    from .domain import encoded
    from .refresh import plan_store_refresh

    allowed = FIELDS | {
        "field_evidence",
        "field_provenance",
        "field_conflicts",
        "field_enrichment_version",
        "last_verified_at",
        "dataset_links",
        "permanently_closed",
        "operating_status",
        "lifecycle",
        "closure_reported_at",
        "address",
        "latitude",
        "longitude",
        "quality",
        "directory_scope",
        "format",
        "contact_channels",
    }
    updates = {row["id"]: row for row in updates}
    with platform.writer():
        platform._recover()
        current = platform.current()
        if (
            not current
            or current["generation"] != base_generation
            or "stores" not in current["packs"]
        ):
            raise ValueError("enrichment_base_generation_changed")
        if (
            shutil.disk_usage(platform.root).free
            < platform.object_path(current["packs"]["stores"]).stat().st_size * 2 + 64 * 1024**2
        ):
            raise ValueError("enrichment_disk_budget_exceeded")
        with tempfile.TemporaryDirectory(dir=platform.root / "staging") as directory:
            path = Path(directory) / "stores.sqlite"
            shutil.copyfile(platform.object_path(current["packs"]["stores"]), path)
            events = []
            chain_deltas = defaultdict(int)
            with closing(sqlite3.connect(path)) as db, db:
                for identity, enriched in updates.items():
                    row = db.execute(
                        "select source,payload from entities where kind='store' and id=?",
                        (identity,),
                    ).fetchone()
                    if row is None or row[0] in platform.control.hidden_sources():
                        raise ValueError("enrichment_store_unavailable")
                    previous = json.loads(row[1])
                    payload = copy.deepcopy(previous)
                    baselines = payload.setdefault("field_baselines", {})
                    for field in FIELDS:
                        if (
                            field in enriched
                            and enriched.get(field) != previous.get(field)
                            and field not in baselines
                        ):
                            baselines[field] = {
                                "source_id": row[0],
                                "present": field in previous,
                                "value": copy.deepcopy(previous.get(field)),
                            }
                    payload.update(
                        {k: copy.deepcopy(v) for k, v in enriched.items() if k in allowed}
                    )
                    for field in FIELDS:
                        if (
                            enriched.get("field_provenance", {}).get(field, {}).get("status")
                            == "withdrawn"
                            and field not in enriched
                        ):
                            payload.pop(field, None)
                    payload["field_refresh"] = {
                        "normalizer_version": "store-groups-v2",
                        "groups": plan_store_refresh(
                            previous, payload, now, crawl_authorized=False
                        )["groups"],
                    }
                    revision = platform._revision("store", payload)
                    if revision == previous["content_revision"]:
                        continue
                    payload["content_revision"] = revision
                    if (
                        previous.get("chain_id")
                        and previous.get("directory_scope", {}).get("status") != "excluded"
                        and payload.get("directory_scope", {}).get("status") == "excluded"
                    ):
                        chain_deltas[previous["chain_id"]] -= 1
                    was_closed = (
                        previous.get("permanently_closed") is True
                        or previous.get("lifecycle") == "closed"
                    )
                    is_closed = (
                        payload.get("permanently_closed") is True
                        or payload.get("lifecycle") == "closed"
                    )
                    if previous.get("chain_id") and was_closed != is_closed:
                        chain_deltas[previous["chain_id"]] += -1 if is_closed else 1
                    db.execute(
                        "update entities set payload=?,revision=? where kind='store' and id=?",
                        (encoded(payload), revision, identity),
                    )
                    rowid = db.execute(
                        "select rowid from entities where kind='store' and id=?", (identity,)
                    ).fetchone()[0]
                    db.execute("delete from spatial where rowid=?", (rowid,))
                    lat, lon = payload.get("latitude"), payload.get("longitude")
                    if (
                        type(lat) in (int, float)
                        and type(lon) in (int, float)
                        and -90 <= lat <= 90
                        and -180 <= lon <= 180
                    ):
                        db.execute(
                            "insert into spatial values(?,?,?,?,?)", (rowid, lat, lat, lon, lon)
                        )
                    db.execute("delete from search where kind='store' and id=?", (identity,))
                    db.execute(
                        "insert into search values(?,?,?)",
                        (
                            "store",
                            identity,
                            " ".join(
                                str(payload.get(k, ""))
                                for k in ("name", "address", "phone", "website")
                            ),
                        ),
                    )
                    events.append(
                        {
                            "id": identity,
                            "kind": "store",
                            "operation": "field_evidence_updated",
                            "revision": revision,
                        }
                    )
                platform._project_aliases(db, events)
                # Adjust only counts affected by explicit scope/closure changes.
                for identity, delta in chain_deltas.items():
                    raw = db.execute(
                        "select payload from entities where kind='chain' and id=?", (identity,)
                    ).fetchone()
                    if raw is None:
                        continue
                    chain = json.loads(raw[0])
                    if "observed_store_count" not in chain:
                        continue
                    chain["observed_store_count"] = max(0, chain["observed_store_count"] + delta)
                    chain["content_revision"] = platform._revision("chain", chain)
                    db.execute(
                        "update entities set payload=?,revision=? where kind='chain' and id=?",
                        (encoded(chain), chain["content_revision"], identity),
                    )
                    events.append(
                        {
                            "id": identity,
                            "kind": "chain",
                            "operation": "updated",
                            "revision": chain["content_revision"],
                        }
                    )
            if not events:
                return {"changed": 0, "no_change": True, "manifest": current}
            relative = platform._seal(path)
            manifest = platform._publish(
                {"stores": relative},
                "store_field_verification",
                "all",
                release,
                {"method": VERSION},
                VERSION,
                events,
                fence,
                hook,
            )
            return {
                "changed": sum(e["kind"] == "store" for e in events),
                "no_change": False,
                "manifest": manifest,
            }


def redact_evidence(value, depth=0):
    """Public evidence must not preserve credential-shaped URL or object values."""
    if depth > 16:
        return "[depth limit]"
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        try:
            p = urlsplit(value)
            netloc = p.netloc.split("@")[-1]
            pairs = [
                (
                    k,
                    "[redacted]"
                    if re.search(r"password|secret|token|session|api.?key|auth", k, re.IGNORECASE)
                    else v,
                )
                for k, v in parse_qsl(p.query, keep_blank_values=True)
            ]
            return urlunsplit((p.scheme, netloc, p.path, urlencode(pairs), p.fragment))
        except ValueError:
            return "[invalid URL]"
    if isinstance(value, dict):
        return {
            k: "[redacted]"
            if re.search(
                r"password|secret|authorization|api.?key|access.?token|refresh.?token|cookie|session",
                str(k),
                re.IGNORECASE,
            )
            else redact_evidence(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_evidence(v, depth + 1) for v in value]
    return copy.deepcopy(value)


def publish_crawl_evidence(platform, evidence, *, now, fence=None):
    """Run after page/map publication; no extra fetch or AI decision is requested."""
    before = platform.current()
    store = platform.get("store", evidence["store_id"], generation=before["generation"])
    if store is None:
        raise ValueError("branch_no_longer_available")
    assertions = evidence.get("field_assertions") or []
    incoming_ids = {r["id"] for r in assertions}
    for row in store.get("field_evidence", []):
        if (
            row.get("source_id") == "retailer_page"
            and row.get("record_id") == evidence["source_url"]
            and row["id"] not in incoming_ids
        ):
            row.update(
                withdrawn=True,
                withdrawn_at=now,
                withdrawal_reason="reparsed_or_refreshed_page_no_longer_supports_assertion",
            )
    enriched = reconcile_fields(store, [*snapshot_assertions(store), *assertions], now=now)
    return publish_enrichment(
        platform,
        [enriched],
        base_generation=before["generation"],
        release=content_hash(
            {
                "version": VERSION,
                "html_sha256": evidence.get("html_sha256"),
                "store_id": store["id"],
            }
        ),
        now=now,
        fence=fence,
    )
