"""Conservative local-time schedules and explicit IANA timezone evidence; no network.

Unknown holiday calendars and split-zone states are never guessed. A schedule does
not establish that a shop is currently operating, or permanently closed.
"""

import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
SCHEMA_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SINGLE_ZONE_US = {
    **dict.fromkeys(
        ("IA", "IL", "WI", "MN", "MO", "AR", "LA", "MS", "AL", "OK"), "America/Chicago"
    ),
    **dict.fromkeys(("CA", "WA"), "America/Los_Angeles"),
    **dict.fromkeys(("CO", "UT", "WY", "MT"), "America/Denver"),
    **dict.fromkeys(
        (
            "GA",
            "NC",
            "SC",
            "VA",
            "WV",
            "DC",
            "OH",
            "PA",
            "NY",
            "NJ",
            "MA",
            "CT",
            "RI",
            "VT",
            "NH",
            "ME",
            "DE",
            "MD",
        ),
        "America/New_York",
    ),
    "HI": "Pacific/Honolulu",
}


def valid_timezone(value):
    if (
        not isinstance(value, str)
        or "/" not in value
        or value.startswith(("Etc/", "posix/", "right/"))
    ):
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return value


def derive_timezone(store):
    region = (store.get("address") or {}).get("region") or store.get("state")
    if store.get("country") == "US" and region in SINGLE_ZONE_US:
        return {
            "value": SINGLE_ZONE_US[region],
            "method": "single-zone-us-region-v1",
            "basis": {"country": "US", "region": region},
            "status": "derived",
        }
    return None


def clock(value, *, closing=False):
    # Some retailer schema.org feeds use explicit meridiem rather than ISO time.
    # Missing meridiem is never guessed for a 12-hour time.
    if isinstance(value, str) and (
        m := re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*", value, re.IGNORECASE)
    ):
        hour, minute = int(m[1]), int(m[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError("invalid_local_time")
        return f"{hour % 12 + (12 if m[3].lower() == 'p' else 0):02d}:{minute:02d}"
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}(?::00)?", value):
        raise ValueError("invalid_local_time")
    hour, minute = map(int, value[:5].split(":"))
    if minute > 59 or hour > 23 and not (closing and hour == 24 and minute == 0):
        raise ValueError("invalid_local_time")
    return value[:5]


def fuller_schedule(candidates):
    """A full source may fill unknown days; partial sources verify only their days."""
    maps = []
    for row in candidates:
        days = {}
        for span in row["value"]:
            days.setdefault(span["day"], set()).add(
                (span["opens"], span["closes"], span.get("closed", False))
            )
        maps.append((row, days))
    full = [(row, days) for row, days in maps if set(days) == set(DAYS)]
    if not full:
        return None
    basis = full[0][1]
    if all(all(basis[d] == spans for d, spans in days.items()) for _, days in maps):
        return full[0][0]
    return None


def _day_values(value):
    values = value if isinstance(value, list) else [value]
    result = []
    for day in values:
        name = str(day).rsplit("/", 1)[-1]
        if name not in SCHEMA_DAYS:
            raise ValueError("invalid_weekday")
        result.append(DAYS[SCHEMA_DAYS.index(name)])
    return sorted(set(result), key=DAYS.index)


def structured_hours(value):
    rows = value if isinstance(value, list) else [value]
    weekly = []
    for row in rows:
        if not isinstance(row, dict) or row.get("validFrom") or row.get("validThrough"):
            raise ValueError("dated_hours_are_not_regular_weekly_hours")
        opening = clock(row.get("opens"))
        closing = clock(row.get("closes"), closing=True)
        for day in _day_values(row.get("dayOfWeek")):
            weekly.append(
                {
                    "day": day,
                    "opens": opening,
                    "closes": closing,
                    "closed": opening == closing == "00:00",
                }
            )
    if not weekly:
        raise ValueError("empty_hours")
    return sorted(weekly, key=lambda r: (DAYS.index(r["day"]), r["opens"], r["closes"]))


def osm_hours(value):
    """Only an unambiguous weekly subset. Complex OSM expressions remain raw."""
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid_hours")
    if value.strip() == "24/7":
        return [{"day": d, "opens": "00:00", "closes": "24:00", "closed": False} for d in DAYS]
    result = []
    for part in value.split(";"):
        match = re.fullmatch(
            r"\s*((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su))*)\s+(off|closed|\d\d:\d\d-\d\d:\d\d(?:,\d\d:\d\d-\d\d:\d\d)*)\s*",
            part,
        )
        if not match:
            raise ValueError("unsupported_hours_expression")
        days = []
        for token in match[1].split(","):
            if "-" in token:
                a, b = map(DAYS.index, token.split("-"))
                days.extend(DAYS[(a + i) % 7] for i in range((b - a) % 7 + 1))
            else:
                days.append(token)
        for day in days:
            if match[2] in ("off", "closed"):
                result.append({"day": day, "opens": "00:00", "closes": "00:00", "closed": True})
            else:
                for span in match[2].split(","):
                    a, b = span.split("-")
                    result.append(
                        {
                            "day": day,
                            "opens": clock(a),
                            "closes": clock(b, closing=True),
                            "closed": False,
                        }
                    )
    if len({(r["day"], r["opens"], r["closes"]) for r in result}) != len(result):
        raise ValueError("duplicate_hours_spans")
    return sorted(result, key=lambda r: (DAYS.index(r["day"]), r["opens"], r["closes"]))


def holiday_exceptions(value):
    result = []
    for row in value if isinstance(value, list) else [value]:
        if not isinstance(row, dict):
            raise TypeError("invalid_hours_exception")
        start, end = (
            date.fromisoformat(row["validFrom"]),
            date.fromisoformat(row.get("validThrough") or row["validFrom"]),
        )
        if start > end or (end - start).days > 366:
            raise ValueError("invalid_exception_date_range")
        opening, closing = clock(row["opens"]), clock(row["closes"], closing=True)
        result.append(
            {
                "valid_from": start.isoformat(),
                "valid_through": end.isoformat(),
                "opens": opening,
                "closes": closing,
                "closed": opening == closing == "00:00",
                "label": row.get("name"),
            }
        )
    return sorted(result, key=lambda r: (r["valid_from"], r["valid_through"], r["opens"]))
