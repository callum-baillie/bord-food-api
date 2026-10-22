"""Small bounded Schema.org microdata reader; no product/inventory extraction."""

from html.parser import HTMLParser

TYPES = {
    "Store",
    "GroceryStore",
    "Supermarket",
    "LocalBusiness",
    "PostalAddress",
    "OpeningHoursSpecification",
    "PropertyValue",
    "LocationFeatureSpecification",
    "GeoCoordinates",
}
PROPS = {
    "name",
    "branchCode",
    "address",
    "streetAddress",
    "addressLocality",
    "addressRegion",
    "postalCode",
    "addressCountry",
    "telephone",
    "email",
    "url",
    "openingHours",
    "openingHoursSpecification",
    "specialOpeningHoursSpecification",
    "opens",
    "closes",
    "dayOfWeek",
    "validFrom",
    "validThrough",
    "department",
    "additionalProperty",
    "amenityFeature",
    "value",
    "propertyID",
    "geo",
    "latitude",
    "longitude",
    "businessStatus",
    "timeZone",
    "timezone",
    "hasEntrance",
}
VOID = {
    "meta",
    "link",
    "input",
    "br",
    "img",
    "hr",
    "source",
    "wbr",
    "area",
    "base",
    "embed",
    "param",
    "track",
    "col",
}


def append(node, key, value):
    if not node or key not in PROPS or value in (None, ""):
        return
    if key not in node:
        node[key] = value
    elif node[key] != value:
        previous = node[key]
        if isinstance(previous, list):
            previous.append(value)
        else:
            node[key] = [previous, value]


class Microdata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.stores = []
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 100000 or len(self.stack) > 128:
            raise ValueError("microdata_limit")
        attrs = dict(attrs)
        scope = self.stack[-1]["scope"] if self.stack else None
        props = [v for v in (attrs.get("itemprop") or "").split() if v in PROPS]
        types = {v.rsplit("/", 1)[-1] for v in (attrs.get("itemtype") or "").split()}
        frame = {
            "tag": tag,
            "scope": scope,
            "props": props,
            "parent": scope,
            "text": [],
            "capture": False,
        }
        if "itemscope" in attrs:
            node = {"@type": sorted(types)} if types & TYPES else None
            if node:
                for prop in props:
                    append(scope, prop, node)
                if types & {"Store", "GroceryStore", "Supermarket", "LocalBusiness"}:
                    self.stores.append(
                        (
                            f"microdata/{len(self.stores)}"
                            + ("/department" if "department" in props else ""),
                            node,
                        )
                    )
            frame["scope"] = node
        elif scope and props:
            value = next(
                (attrs[k] for k in ("content", "datetime", "href") if attrs.get(k) is not None),
                None,
            )
            if value is not None:
                for prop in props:
                    append(scope, prop, value)
            else:
                frame["capture"] = True
        if tag not in VOID:
            self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        for frame in self.stack:
            if frame["capture"]:
                frame["text"].append(data)

    def handle_endtag(self, tag):
        index = next(
            (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None
        )
        if index is None:
            return
        for frame in self.stack[index:]:
            if frame["capture"]:
                value = " ".join("".join(frame["text"]).split())
                for prop in frame["props"]:
                    append(frame["parent"], prop, value)
        del self.stack[index:]


def stores(html):
    parser = Microdata()
    parser.feed(html)
    parser.close()
    return parser.stores
