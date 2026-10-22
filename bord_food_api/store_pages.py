"""Bounded branch HTML/hydration extraction; no browser, links followed or guessed facts."""

import json
import re
from html.parser import HTMLParser

from .store_microdata import VOID

BLOCKS = {"div", "p", "li", "tr", "td", "h1", "h2", "h3", "h4", "section", "article", "main", "br"}
SKIP = {"script", "style", "nav", "footer", "noscript", "template", "select"}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY = r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
TIME = r"\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?"


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "document", "attrs": {}, "children": [], "path": "html"}
        self.stack = [self.root]
        self.nodes = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or "" for key, value in attrs}
        if len(self.nodes) >= 50000 or len(self.stack) > 128:
            raise ValueError("branch_html_complexity_limit")
        parent = self.stack[-1]
        n = {
            "tag": tag,
            "attrs": attrs,
            "children": [],
            "path": parent["path"] + "/" + tag + f"/{len(parent['children'])}",
        }
        parent["children"].append(n)
        self.nodes.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        i = next(
            (i for i in range(len(self.stack) - 1, 0, -1) if self.stack[i]["tag"] == tag), None
        )
        if i is not None:
            del self.stack[i:]

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


def visible(n):
    if isinstance(n, str):
        return n
    a = n["attrs"]
    style = re.sub(r"\s+", "", a.get("style", "")).lower()
    if (
        n["tag"] in SKIP
        or "hidden" in a
        or a.get("aria-hidden") == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    ):
        return ""
    separator = "\n" if n["tag"] in BLOCKS else " "
    return separator + separator.join(visible(c) for c in n["children"]) + separator


def contact_region(n):
    """Render a specifically selected contact footer without exposing hidden content."""
    if n["tag"] == "footer":
        return {
            **n,
            "tag": "section",
            "attrs": {k: v for k, v in n["attrs"].items() if k != "class"},
        }
    return n


def branch_review_text(page, branch_path):
    """Raw title and selected branch panel, including an explicitly selected footer.

    No target-derived identity is inserted as if it appeared in the page. Hidden
    content, navigation and other branch panels remain excluded.
    """
    branch = next((n for n in page.nodes if n["path"] == branch_path), None)
    if not branch:
        return ""
    title = " ".join(visible(n) for n in page.nodes if n["tag"] == "title")
    panel = " ".join(visible(contact_region(branch)).split())
    return (" ".join(title.split())[:300] + "\n" + panel[:5700]).strip()


def links(n):
    result = []
    if not isinstance(n, dict) or n["tag"] in SKIP:
        return result
    if re.search(
        r"(?:^|[\s_-])(?:header|footer|navbar|teaser|nearby|breadcrumb)(?:[\s_-]|$)",
        n["attrs"].get("class", ""),
        re.IGNORECASE,
    ):
        return result
    if n["tag"] == "a" and n["attrs"].get("href"):
        result.append(
            {"href": n["attrs"]["href"], "text": " ".join(visible(n).split()), "path": n["path"]}
        )
    for c in n["children"]:
        if isinstance(c, dict):
            result.extend(links(c))
    return result


def _clock(s):
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", s.strip(), re.IGNORECASE)
    if not m or not 1 <= int(m[1]) <= 12 or int(m[2] or 0) > 59:
        raise ValueError("unsupported_visible_hours")
    return f"{int(m[1]) % 12 + (12 if m[3].lower() == 'p' else 0):02d}:{int(m[2] or 0):02d}"


def weekly(text):
    """Only explicit weekday spans with AM/PM on both endpoints, or closed."""
    rows = []
    text = re.sub(
        rf"\b(?:open\s+)?({TIME}\s*(?:-|–|—|to)\s*{TIME})\s+(?:daily|every\s+day)\b",
        r"Monday-Sunday \1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:open\s+)?(?:daily|every\s+day)\s*:?(?=\s*\d)",
        "Monday-Sunday ",
        text,
        flags=re.IGNORECASE,
    )
    pattern = rf"\b({DAY})(?:\s*(?:-|–|—|to|through)\s*({DAY}))?\s*:?\s*({TIME}\s*(?:-|–|—|to)\s*{TIME}|closed)\b"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        start = next(i for i, d in enumerate(DAYS) if d[:3].lower() == m[1][:3].lower())
        end = next(i for i, d in enumerate(DAYS) if d[:3].lower() == (m[2] or m[1])[:3].lower())
        span = (
            list(range(start, end + 1))
            if end >= start
            else list(range(start, 7)) + list(range(end + 1))
        )
        if m[3].lower() == "closed":
            opening = closing = "00:00"
        else:
            times = re.findall(TIME, m[3], re.IGNORECASE)
            opening, closing = (_clock(v) for v in times)
        rows.extend({"dayOfWeek": DAYS[i], "opens": opening, "closes": closing} for i in span)
    # Duplicate/different schedules from pharmacy/service sections are ambiguous.
    unique = {json.dumps(r, sort_keys=True): r for r in rows}
    result = list(unique.values())
    if len({r["dayOfWeek"] for r in result}) != len(result):
        return []
    return result


def structured_nodes(html):
    """Read pure JSON hydration only. Never evaluate JS or walk product objects."""
    page = Page()
    page.feed(html)
    page.close()
    result = []
    for node in page.nodes:
        attrs = node["attrs"]
        if node["tag"] != "script":
            continue
        raw = "".join(c for c in node["children"] if isinstance(c, str))
        try:
            if attrs.get("type") == "application/json" or attrs.get("id") == "__NEXT_DATA__":
                root = json.loads(raw)
            elif assignment := re.search(r"\bYext\.Profile\s*=\s*", raw):
                # Decode one JSON literal from this known template. Surrounding
                # JavaScript is never interpreted, evaluated or executed.
                root, _end = json.JSONDecoder().raw_decode(raw[assignment.end() :])
            else:
                continue
        except (TypeError, ValueError):
            continue
        pending = [(root, node["path"], 0)]
        count = 0
        while pending:
            row, path, depth = pending.pop()
            count += 1
            if count > 5000 or depth > 30:
                raise ValueError("hydration_complexity_limit")
            if isinstance(row, dict):
                if row.get("@type") == "Product" or any(
                    k in row for k in ("sku", "gtin", "gtin13", "productId")
                ):
                    continue
                address = row.get("address")
                if isinstance(address, dict) and (
                    address.get("line1") or address.get("streetAddress")
                ):
                    store = {
                        "@type": "GroceryStore",
                        "name": row.get("name"),
                        "address": {
                            "streetAddress": address.get("streetAddress") or address.get("line1"),
                            "addressLocality": address.get("addressLocality")
                            or address.get("city"),
                            "addressRegion": address.get("addressRegion") or address.get("region"),
                            "postalCode": address.get("postalCode"),
                        },
                    }
                    for key, source in [
                        ("telephone", "mainPhone"),
                        ("email", "email"),
                        ("url", "websiteUrl"),
                        ("openingHours", "openingHours"),
                    ]:
                        if row.get(source):
                            store[key] = row[source]
                    if isinstance(store.get("telephone"), dict):
                        store["telephone"] = store["telephone"].get("number")
                    if row.get("c_pagesDepartments"):
                        store["department"] = [
                            {"name": v} for v in row["c_pagesDepartments"] if isinstance(v, str)
                        ]
                    for field, keys in {
                        "pickupLinks": ("c_pickupLink", "c_driveUpAndGoURL"),
                        "deliveryLinks": ("c_groceryDeliveryLink", "c_deliveryURL"),
                    }.items():
                        values = [
                            row[k]
                            for k in keys
                            if isinstance(row.get(k), str) and row[k].startswith("https://")
                        ]
                        if values:
                            store[field] = values
                    for action in row.get("appleActionLinks", []):
                        if not isinstance(action, dict):
                            continue
                        category = str(action.get("category", ""))
                        url = action.get("quickLinkUrl")
                        if isinstance(url, str) and url.startswith("https://"):
                            if "pickup" in category.lower():
                                store.setdefault("pickupLinks", []).append(url)
                            if "delivery" in category.lower():
                                store.setdefault("deliveryLinks", []).append(url)
                    hours = row.get("hours")
                    if isinstance(hours, dict):
                        weekly_rows = []
                        for day in DAYS:
                            value = hours.get(day.lower())
                            if not isinstance(value, dict):
                                continue
                            if value.get("isClosed") is True:
                                weekly_rows.append(
                                    {"dayOfWeek": day, "opens": "00:00", "closes": "00:00"}
                                )
                            for interval in value.get("openIntervals", []):
                                weekly_rows.append(
                                    {
                                        "dayOfWeek": day,
                                        "opens": interval.get("start"),
                                        "closes": interval.get("end"),
                                    }
                                )
                        if weekly_rows:
                            store["openingHoursSpecification"] = weekly_rows
                        if isinstance(hours.get("normalHours"), list):
                            weekly_rows = []

                            def clock(value):
                                if (
                                    type(value) is not int
                                    or not 0 <= value <= 2400
                                    or value % 100 > 59
                                ):
                                    return None
                                return f"{value // 100:02d}:{value % 100:02d}"

                            for day in hours["normalHours"]:
                                name = str(day.get("day", "")).title()
                                if name not in DAYS:
                                    continue
                                if day.get("isClosed") is True:
                                    weekly_rows.append(
                                        {"dayOfWeek": name, "opens": "00:00", "closes": "00:00"}
                                    )
                                for interval in day.get("intervals", []):
                                    weekly_rows.append(
                                        {
                                            "dayOfWeek": name,
                                            "opens": clock(interval.get("start")),
                                            "closes": clock(interval.get("end")),
                                        }
                                    )
                            if weekly_rows:
                                store["openingHoursSpecification"] = weekly_rows
                        if isinstance(hours.get("holidayHours"), list):
                            holidays = []
                            for day in hours["holidayHours"]:
                                stamp = day.get("date")
                                if not isinstance(stamp, str) or not re.fullmatch(
                                    r"\d{4}-\d{2}-\d{2}", stamp
                                ):
                                    continue
                                if day.get("isClosed") is True:
                                    holidays.append(
                                        {
                                            "validFrom": stamp,
                                            "validThrough": stamp,
                                            "opens": "00:00",
                                            "closes": "00:00",
                                        }
                                    )
                            if holidays:
                                store["specialOpeningHoursSpecification"] = holidays
                    if any(
                        k in store
                        for k in ("telephone", "openingHours", "openingHoursSpecification")
                    ):
                        result.append((path, store))
                pending.extend(
                    (v, path + "/" + str(k), depth + 1)
                    for k, v in row.items()
                    if isinstance(v, (dict, list))
                )
            elif isinstance(row, list):
                pending.extend(
                    (v, path + "/" + str(i), depth + 1)
                    for i, v in enumerate(row)
                    if isinstance(v, (dict, list))
                )
    return page, result


def branch_html(page, target, match):
    """Select the smallest explicit branch region carrying its exact address.

    No document-wide footer contacts. Multiple phones remain unresolved unless a
    uniquely labelled store phone exists. Departments are not general store hours.
    """
    address = target.get("source_address") or {}
    full = address.get("full") or ""
    m = re.fullmatch(r"\s*(.+),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*", full)
    if m:
        address = {
            **address,
            **dict(zip(("street", "city", "region", "postal_code"), m.groups(), strict=True)),
        }
    street = address.get("street") or address.get("street_address")
    if not street:
        return None, [], None
    from .store_discovery import STREET_WORDS

    def normalized(text):
        return " ".join(STREET_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", text.casefold()))

    wanted = normalized(street)
    candidates = []
    review = target.get("site_identity_review") or {}
    reviewed_identity = (
        review.get("store_id") == target.get("store_id")
        and review.get("source_address") == target.get("source_address")
        and re.fullmatch(r"[a-f0-9]{64}", str(review.get("evidence_sha256") or ""))
    )
    reviewed_single = reviewed_identity and target.get("single_store_site") is True
    excluded_paths = [
        n["path"]
        for n in page.nodes
        if n["tag"] in {"nav", "footer", "header"}
        or re.search(
            r"(?:^|[ _-])(?:footer|navbar|breadcrumb|nearby)(?:[ _-]|$)",
            n["attrs"].get("class", ""),
            re.IGNORECASE,
        )
    ]
    for n in page.nodes:
        # Only an individually reviewed single-premise site may use its own
        # address-bound contact footer. Corporate/nearby footers remain excluded.
        contact_footer = reviewed_single and n["tag"] == "footer"
        reviewed_panel = (
            reviewed_identity
            and review.get("scope") == "multi_branch_contact_panel"
            and "/footer/" in n["path"]
            and n["tag"] in {"div", "li", "address"}
        )
        if (
            not contact_footer
            and not reviewed_panel
            and any(
                n["path"].startswith(path + "/") or n["path"] == path for path in excluded_paths
            )
        ):
            continue
        if contact_footer:
            n = contact_region(n)
        a = n["attrs"]
        label = (a.get("class", "") + " " + a.get("id", "")).lower()
        independent_contact = (
            target.get("single_store_site") is True
            and n["tag"] in {"div", "address"}
            and re.search(r"(?:contact|opening[-_ ]?hours|business[-_ ]info)", label)
        )
        independent_contact = independent_contact or reviewed_panel
        if (
            not independent_contact
            and n["tag"] not in {"main", "section", "article"}
            and not re.search(
                r"(?:store|location)[-_ ](?:detail|info|card|page)|contact[-_ ]info", label
            )
        ):
            continue
        text = visible(n)
        plain = normalized(text)
        if len(text) > 100000 or f" {wanted} " not in f" {plain} ":
            continue
        postal = str(address.get("postal_code") or "").split("-")[0]
        city = address.get("city") or address.get("locality")
        has_postal = bool(postal and re.search(r"\b" + re.escape(postal) + r"\b", text))
        has_city = bool(city and f" {normalized(city)} " in f" {plain} ")
        region = address.get("region")
        has_region = bool(
            region and re.search(r"\b" + re.escape(region) + r"\b", text, re.IGNORECASE)
        )
        if region and not has_region:
            from .nationwide import JURISDICTIONS

            state_name = JURISDICTIONS.get(region)
            has_region = bool(
                state_name and re.search(r"\b" + re.escape(state_name) + r"\b", text, re.IGNORECASE)
            )
        if not (has_postal or has_city and has_region):
            continue
        phones = {a["href"] for a in links(n) if a["href"].startswith("tel:")}
        if reviewed_identity and not phones:
            phones = set(re.findall(r"\(?[2-9]\d{2}\)?[ .-]*[2-9]\d{2}[ .-]*\d{4}", text))
        score = (8 if weekly(text) else 0) + (3 if len(phones) == 1 else 0)
        score += (
            2 if re.search(r"\b(?:store|grocery)\s+(?:phone|hours)\b", text, re.IGNORECASE) else 0
        )
        candidates.append((-score, len(text), n, text, has_postal, has_city, has_region))
    if not candidates:
        return None, [], None
    _, _, n, text, has_postal, has_city, has_region = min(candidates, key=lambda r: r[:2])
    node = {
        "@type": "GroceryStore",
        "name": target.get("name"),
        "address": {
            "streetAddress": street,
            "addressLocality": (address.get("city") or address.get("locality"))
            if has_city
            else None,
            "addressRegion": address.get("region") if has_region else None,
            "postalCode": address.get("postal_code") if has_postal else None,
        },
        "url": target["url"],
    }
    if not match(node, target):
        return None, [], None
    from .chain_profiles import main_phone, profile_for, store_hours_text

    profile = profile_for(target)
    anchors = links(n)
    phones = {a["href"].split("?", 1)[0] for a in anchors if a["href"].startswith("tel:")}
    labelled = {
        a["href"].split("?", 1)[0]
        for a in anchors
        if a["href"].startswith("tel:")
        and re.search(r"\b(?:store|grocery)\b", a["text"], re.IGNORECASE)
    }
    selected = labelled if len(labelled) == 1 else phones
    explicit_phone = main_phone(text, profile)
    if explicit_phone:
        selected = {explicit_phone}
    if len(selected) == 1:
        node["telephone"] = next(iter(selected))
    if not phones:
        labelled_numbers = set(
            re.findall(
                r"\b(?:Store\s+|Grocery\s+|Main\s+)?Phone(?:\s+Number)?\s*:?\s*(\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4})\b",
                text,
                re.IGNORECASE,
            )
        )
        if len(labelled_numbers) == 1:
            node["telephone"] = next(iter(labelled_numbers))
        elif reviewed_identity or "contact" in str(n["attrs"].get("class") or "").lower():
            numbers = set(re.findall(r"\(?[2-9]\d{2}\)?[ .-]*[2-9]\d{2}[ .-]*\d{4}", text))
            if len(numbers) == 1:
                node["telephone"] = next(iter(numbers))
    emails = {a["href"][7:].split("?", 1)[0] for a in anchors if a["href"].startswith("mailto:")}
    if len(emails) == 1:
        node["email"] = next(iter(emails))
    # Only a dedicated store-hours region, or a branch with no competing departments.
    hours = (
        weekly(text)
        if not re.search(r"pharmacy|fuel hours|deli hours", text, re.IGNORECASE)
        else []
    )
    hours_text = store_hours_text(text, profile)
    if not hours:
        hours = weekly(hours_text)
    if (
        hours
        and re.search(r"closed\s+Sundays?", hours_text, re.IGNORECASE)
        and not any(r["dayOfWeek"] == "Sunday" for r in hours)
    ):
        hours.append({"dayOfWeek": "Sunday", "opens": "00:00", "closes": "00:00"})
    if hours:
        node["openingHoursSpecification"] = hours
    if re.search(r"\bwheelchair accessible\b", text, re.IGNORECASE):
        node["amenityFeature"] = {
            "wheelchair": "no"
            if re.search(r"not wheelchair accessible", text, re.IGNORECASE)
            else "yes"
        }
    if re.search(r"\bpermanently closed\b", text, re.IGNORECASE):
        node["businessStatus"] = "permanently_closed"
    return node, anchors, n["path"]


def department_tables(page, store, target):
    """Explicit branch-page Department Hours tables, never product category menus."""
    from .store_discovery import name_key

    headings = {
        name_key(" ".join(visible(n).split()))
        for n in page.nodes
        if n["tag"] == "h1" and visible(n).strip()
    }
    names = [name_key(v) for v in (store.get("name"), target.get("name")) if v]
    if not any(len(name) >= 5 and name in heading for name in names for heading in headings):
        return []
    result = []
    for table in page.nodes:
        if table["tag"] != "table" or "/footer/" in table["path"] or "/nav/" in table["path"]:
            continue
        descendants = [n for n in page.nodes if n["path"].startswith(table["path"] + "/")]
        headers = [n for n in descendants if n["tag"] == "thead"]
        if not any(
            " ".join(visible(h).split()).rstrip(":").lower()
            in {"department hours", "store departments"}
            for h in headers
        ):
            continue
        departments = []
        for row in descendants:
            if row["tag"] != "tr" or "/thead/" in row["path"]:
                continue
            cells = [n for n in row["children"] if isinstance(n, dict) and n["tag"] == "td"]
            if not cells:
                continue
            name = " ".join(visible(cells[0]).split()).strip(" :")
            if not name or len(name) > 160:
                continue
            department = {"name": name}
            if len(cells) > 1:
                hours = " ".join(visible(cells[1]).split())
                if hours and len(hours) <= 1024:
                    department["hours_raw"] = hours
            departments.append(department)
        if 0 < len(departments) <= 64:
            result.append((table["path"], departments))
    return result
