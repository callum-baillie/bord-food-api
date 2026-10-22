"""Bounded public structured evidence, kept separate from accepted catalog facts.

Extraction never follows links, infers stock, grants media rights or edits household data.
"""

import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit

from .crawlers import map_links, parse_page
from .site_discovery import contact_followups, platform_profile
from .sources import strict_gtin
from .store_enrichment import assertion
from .store_microdata import stores as microdata_stores
from .store_pages import branch_html, department_tables, structured_nodes

STORE_FIELDS = (
    "name",
    "branchCode",
    "address",
    "geo",
    "telephone",
    "email",
    "url",
    "openingHours",
    "openingHoursSpecification",
    "specialOpeningHoursSpecification",
    "department",
    "additionalProperty",
    "amenityFeature",
    "paymentAccepted",
    "currenciesAccepted",
    "businessStatus",
    "hasEntrance",
    "timeZone",
    "timezone",
)


def _types(node):
    value = node.get("@type", [])
    return (
        {value}
        if isinstance(value, str)
        else {x for x in value if isinstance(x, str)}
        if isinstance(value, list)
        else set()
    )


def _nodes(scripts):
    """Walk structured objects with source JSON pointers and bounded complexity."""
    count = 0
    for index, script in enumerate(scripts):
        try:
            root = json.loads(script, parse_float=str)
        except (ValueError, TypeError):
            continue
        pending = [(root, f"jsonld/{index}", 0)]
        while pending:
            node, path, depth = pending.pop()
            count += 1
            if count > 5000 or depth > 30:
                raise ValueError("structured_evidence_limit")
            if isinstance(node, dict):
                yield path, node
                pending.extend(
                    (v, path + "/" + str(k).replace("~", "~0").replace("/", "~1"), depth + 1)
                    for k, v in node.items()
                    if isinstance(v, (dict, list))
                )
            elif isinstance(node, list):
                pending.extend(
                    (v, path + f"/{i}", depth + 1)
                    for i, v in enumerate(node)
                    if isinstance(v, (dict, list))
                )


def _equal(a, b):
    return bool(
        a
        and b
        and re.sub(r"\s+", " ", str(a)).strip().casefold()
        == re.sub(r"\s+", " ", str(b)).strip().casefold()
    )


def _branch_match(node, target):
    address, expected = node.get("address"), target.get("source_address") or {}
    if not isinstance(address, dict):
        return False
    expected = dict(expected)
    if not expected.get("street") and expected.get("full"):
        match = re.fullmatch(
            r"\s*(.+),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*", expected["full"]
        )
        if match:
            expected.update(
                zip(("street", "city", "region", "postal_code"), match.groups(), strict=True)
            )
    expected["street"] = expected.get("street") or expected.get("street_address")
    expected["city"] = expected.get("city") or expected.get("locality")
    # Names/coordinates alone never assign a branch. Require full street and a
    # second independently explicit address component, without fuzzy geocoding.
    from .store_discovery import STREET_WORDS

    def street(value):
        words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
        return " ".join(STREET_WORDS.get(w, w) for w in words)

    postal = lambda value: str(value or "").split("-")[0].strip()
    return (
        bool(street(address.get("streetAddress")))
        and street(address.get("streetAddress")) == street(expected.get("street"))
        and (
            bool(postal(address.get("postalCode")))
            and postal(address.get("postalCode")) == postal(expected.get("postal_code"))
            or _equal(address.get("addressLocality"), expected.get("city"))
            and _equal(address.get("addressRegion"), expected.get("region"))
        )
    )


def _layout_properties(value):
    values = value if isinstance(value, list) else [value]
    return [
        item
        for item in values
        if isinstance(item, dict)
        and re.search(
            r"\b(?:aisle|shelf|department|section|floor)\b",
            str(item.get("name") or item.get("propertyID") or ""),
            re.IGNORECASE,
        )
    ]


def _store_fields(node):
    fields = {key: node[key] for key in STORE_FIELDS if key in node}
    if "department" in fields:
        departments = fields["department"]
        departments = departments if isinstance(departments, list) else [departments]
        fields["department"] = [
            {
                key: value
                for key, value in department.items()
                if key in STORE_FIELDS and key != "department"
            }
            for department in departments
            if isinstance(department, dict)
        ]
    return fields


def collect_evidence(html, target, *, retrieved_at):
    parser = parse_page(html)
    page, hydration = structured_nodes(html)
    nodes = list(_nodes(parser.scripts)) + microdata_stores(html) + hydration
    html_store, branch_links, html_path = branch_html(page, target, _branch_match)
    stores = [
        (path, node)
        for path, node in nodes
        if _types(node) & {"Store", "GroceryStore", "LocalBusiness", "Supermarket"}
        and _branch_match(node, target)
    ]
    # Exact duplicate schema/microdata roots are one observation, not independent votes.
    stores = list({json.dumps(n, sort_keys=True): (path, n) for path, n in stores}.values())
    # Several contradictory store descriptions require review, even on one page.
    primary = [
        (path, n)
        for path, n in stores
        if "/department/" not in path and "/department" != path[-11:]
    ]
    grocery = [(path, n) for path, n in primary if _types(n) & {"GroceryStore", "Supermarket"}]
    hydration_stores = [(path, n) for path, n in primary if path.startswith("html/")]
    selected = (
        hydration_stores
        if len(hydration_stores) == 1
        else grocery
        if len(grocery) == 1
        else primary
    )
    store = selected[0][1] if len(selected) == 1 else None
    selected_path = selected[0][0] if store else None
    if not stores and html_store:
        store, selected_path = html_store, html_path
        stores = [(html_path, html_store)]
    assertions = (
        retailer_assertions(store, selected_path, branch_links, target, retrieved_at, html)
        if store
        else []
    )
    if store and html_store and selected_path != html_path:
        existing = {r["field"] for r in assertions if r["validation"] == "valid"}
        assertions.extend(
            r
            for r in retailer_assertions(
                html_store, html_path, branch_links, target, retrieved_at, html
            )
            if r["field"] not in existing
        )
    assertions.extend(page_contact_assertions(parser.links, target, retrieved_at))
    tables = department_tables(page, store, target) if store else []
    if not any(r["field"] == "departments" and r["validation"] == "valid" for r in assertions):
        for path, departments in tables:
            assertions.extend(
                retailer_assertions(
                    {"department": departments}, path, [], target, retrieved_at, html
                )
            )
    placements = []
    for path, node in nodes:
        properties = _layout_properties(node.get("additionalProperty"))
        if "Product" not in _types(node) or not properties:
            continue
        gtin_raw = next(
            (node[key] for key in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin") if node.get(key)),
            None,
        )
        placements.append(
            {
                "source_path": path,
                "name": node.get("name"),
                "sku": node.get("sku"),
                "gtin_raw": gtin_raw,
                "gtin": strict_gtin(str(gtin_raw)) if gtin_raw is not None else None,
                "placement_properties": properties,
                "status": "unverified",
                "branch_association": "page_context_requires_review" if store else "unresolved",
                "route_geometry_validated": False,
            }
        )
    return {
        "profile": "public-store-layout-evidence-v1",
        "store_id": target["store_id"],
        "source_url": target["url"],
        "retrieved_at": retrieved_at,
        "source_observed_at": None,
        "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "parser_version": "branch-fields-v9",
        "site_platform": platform_profile(html),
        "contact_page_candidates": contact_followups(html, target),
        "field_assertions": assertions,
        "selected_store_path": selected_path,
        "acceptance_status": "review_required",
        "branch_match": "exact_address" if store else "ambiguous_or_missing",
        "store_candidates": [
            {"source_path": path, "fields": _store_fields(n)} for path, n in stores
        ],
        "layout_evidence": [
            {
                "source_path": path + "/" + key,
                "field": key,
                "value": _store_fields(node)[key],
                "status": "unverified",
                "route_geometry_validated": False,
            }
            for path, node in stores
            for key in ("department", "additionalProperty")
            if key in node
        ]
        + [
            {
                "source_path": path,
                "field": "department_hours_table",
                "value": values,
                "status": "unverified",
                "route_geometry_validated": False,
            }
            for path, values in tables
        ],
        "timezone": store.get("timeZone", store.get("timezone")) if store else None,
        "hours_status": "unverified_timezone_and_exceptions",
        "geographic_map_links": [n["hasMap"] for _, n in stores if n.get("hasMap")],
        "interior_map_candidates": map_links(
            html,
            target["url"],
            expected_branch=target["expected_branch"],
            store_id=target["store_id"],
        ),
        "item_placement_candidates": placements,
        "capture_policy": {
            "product_catalog": False,
            "product_inventory": False,
            "prices": False,
            "product_page_fetches": False,
        },
        "inventory_status": "unknown",
        "placement_status": "unverified",
        "rights": {
            "license": None,
            "media_storage_permitted": False,
            "media_display_permitted": False,
        },
        "limitations": [
            "Structured source assertions require review; not accepted catalog facts",
            "Incidental item references support placement review only; no product catalog, price or inventory capture",
            "No media downloaded; geographic hasMap is not an interior route graph",
        ],
    }


def retailer_assertions(store, path, links, target, retrieved_at, html=""):
    """Extract only identity-bound branch values. Links are retained, never fetched."""
    values = {}
    for field, key in {
        "phone": "telephone",
        "email": "email",
        "website": "url",
        "opening_hours": "openingHoursSpecification",
        "hours_exceptions": "specialOpeningHoursSpecification",
        "timezone": "timeZone",
        "departments": "department",
        "accessibility": "amenityFeature",
        "entrances": "hasEntrance",
        "pickup_links": "pickupLinks",
        "delivery_links": "deliveryLinks",
    }.items():
        if store.get(key) is not None:
            values[field] = store[key]
    if "opening_hours" not in values and store.get("openingHours"):
        values["opening_hours"] = store["openingHours"]
    if "timezone" not in values and store.get("timezone"):
        values["timezone"] = store["timezone"]
    explicit_status = str(store.get("businessStatus") or "").lower().replace(" ", "_")
    if explicit_status in {"open", "temporarily_closed", "permanently_closed"}:
        values["operating_status"] = explicit_status
    for link in links:
        label = " ".join(str(link.get("text") or "").lower().split())
        href = link.get("href") or ""
        if not store.get("pickupLinks") and re.search(r"\b(?:pick.?up|curbside)\b", label):
            values.setdefault("pickup_links", []).append(urljoin(target["url"], href))
        if not store.get("deliveryLinks") and re.search(r"\bdelivery\b", label):
            values.setdefault("delivery_links", []).append(urljoin(target["url"], href))
    root = "retailer:" + (urlsplit(target["url"]).hostname or "").removeprefix("www.")
    return [
        assertion(
            target["store_id"],
            field,
            value,
            source_id="retailer_page",
            record_id=target["url"],
            source_url=target["url"],
            checked_at=retrieved_at,
            lineage=root,
            branch_match="exact_address",
            authority=target.get("source_authority", "official"),
            source_revision=hashlib.sha256(html.encode()).hexdigest(),
            source_path=path + "/" + field,
            country=target.get("country", "US"),
        )
        for field, value in values.items()
    ]


def page_contact_assertions(links, target, retrieved_at):
    """Retain page-level contacts without assigning corporate/footer data to a branch."""
    rows = []
    root = "retailer:" + (urlsplit(target["url"]).hostname or "").removeprefix("www.")
    for index, link in enumerate(links):
        href = link.get("href") or ""
        field = (
            "phone" if href.startswith("tel:") else "email" if href.startswith("mailto:") else None
        )
        if field:
            value = href.split("?", 1)[0].removeprefix("mailto:")
            rows.append(
                assertion(
                    target["store_id"],
                    field,
                    value,
                    source_id="retailer_page",
                    record_id=target["url"],
                    source_url=target["url"],
                    checked_at=retrieved_at,
                    lineage=root,
                    branch_match="unresolved",
                    authority="official",
                    source_path=f"links/{index}",
                    scope="page_contact",
                )
            )
    return rows
