"""Versioned US chain extraction hints. Profiles never authorize network access."""

import re
from urllib.parse import urlsplit

VERSION = "us-store-profiles-v1"
PROFILES = (
    {
        "id": "hy_vee",
        "names": (r"hy[ -]?vee", r"dollar fresh"),
        "spiders": ("hy_vee_us",),
        "domains": ("hy-vee.com", "dollarfreshmarket.com"),
        "brand": "hy_vee",
        "exclude_formats": (r"fast\s*(?:&|and)\s*fresh", r"drug\s*(?:store|town)"),
        "phone_labels": ("Store Phone Number", "Main"),
        "hours_stop": ("Department Phone", "Department Hours", "Store Phone", "Address"),
    },
    {
        "id": "fareway",
        "names": (r"fareway",),
        "spiders": ("fareway_us",),
        "domains": ("fareway.com",),
        "brand": "fareway",
        "exclude_formats": (r"meat market",),
        "phone_labels": ("Store",),
        "hours_stop": ("Meat", "Department", "Shop Online"),
    },
    {
        "id": "aldi",
        "names": (r"\baldi\b",),
        "spiders": ("aldi_sud_us",),
        "domains": ("aldi.us",),
        "brand": "aldi",
        "exclude_formats": (),
        "phone_labels": ("Store Phone",),
        "hours_stop": ("Nearby", "Other Stores"),
        "chain_phones": ("+18559552534",),
    },
    {
        "id": "walmart",
        "names": (r"walmart", r"wal[ -]mart"),
        "spiders": ("walmart", "walmart_us"),
        "domains": ("walmart.com",),
        "brand": "walmart",
        "exclude_formats": (r"\b(?:pharmacy|fuel|optical|auto care)\b",),
        "phone_labels": ("Store Phone", "Main"),
        "hours_stop": ("Pharmacy", "Auto Care", "Vision Center"),
    },
    {
        "id": "target",
        "names": (r"\btarget\b",),
        "spiders": ("target_us",),
        "domains": ("target.com",),
        "brand": "target",
        "exclude_formats": (),
        "phone_labels": ("Store Phone",),
        "hours_stop": ("CVS", "Pharmacy", "Starbucks"),
    },
    {
        "id": "albertsons",
        "names": (r"jewel[ -]?osco", r"safeway", r"albertsons"),
        "spiders": ("albertsons",),
        "domains": ("jewelosco.com", "safeway.com", "albertsons.com"),
        "brand": "albertsons",
        "exclude_formats": (),
        "phone_labels": ("Store", "Grocery"),
        "hours_stop": ("Pharmacy", "Fuel"),
    },
)
DEFAULT = {
    "id": "independent",
    "brand": None,
    "exclude_formats": (),
    "phone_labels": ("Store Phone", "Grocery Phone", "Main Phone", "Phone Number"),
    "hours_stop": ("Pharmacy", "Department Hours", "Fuel Hours"),
}


def profile_for(store):
    name = str(store.get("name") or store.get("expected_branch") or "")
    host = urlsplit(store.get("url") or store.get("website") or "").hostname or ""
    for profile in PROFILES:
        if (
            store.get("spider") in profile["spiders"]
            or any(re.search(p, name, re.IGNORECASE) for p in profile["names"])
            or any(host == d or host.endswith("." + d) for d in profile["domains"])
        ):
            return profile
    return DEFAULT


def out_of_scope(store):
    p = profile_for(store)
    return next(
        (
            pattern
            for pattern in p["exclude_formats"]
            if re.search(pattern, store.get("name", ""), re.IGNORECASE)
        ),
        None,
    )


def main_phone(text, profile):
    pattern = (
        r"(?:"
        + "|".join(re.escape(s) for s in profile["phone_labels"])
        + r")\s*:?\s*(\(?[2-9]\d{2}\)?[ .-]*[2-9]\d{2}[ .-]*\d{4})"
    )
    numbers = set(re.findall(pattern, text, re.IGNORECASE))
    return next(iter(numbers)) if len(numbers) == 1 else None


def store_hours_text(text, profile):
    """Discard competing department sections; never assign their hours to groceries."""
    stops = [
        m.start()
        for label in profile["hours_stop"]
        for m in re.finditer(re.escape(label), text, re.IGNORECASE)
    ]
    return text[: min(stops)] if stops else text
