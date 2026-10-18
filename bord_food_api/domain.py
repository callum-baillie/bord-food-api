"""Strict native identifiers and deterministic business-field normalization."""

import hashlib
import json
import re
import unicodedata

HASH_VERSION = "1"
US_STATES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ]
)


def normalize_gtin(value: str) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value):
        return None
    digits = [int(item) for item in value]
    check = sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(digits[:-1])))
    return value.zfill(14) if (check + digits[-1]) % 10 == 0 else None


def canonical(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def encoded(value) -> str:
    return json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def business_payload(payload):
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "id",
            "content_revision",
            "source_refs",
            "fetched_at",
            "last_checked_at",
            "source_observed_at",
            "last_observed_in_source_run",
            "source_record",
            "source_properties",
            "source_run",
            "last_modified_t",
            "revision",
            "field_refresh",
        }
    }
