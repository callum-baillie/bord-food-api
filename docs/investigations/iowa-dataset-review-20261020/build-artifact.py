"""Build the canonical, aggregate-only report input from the reviewed profile."""

import json
from pathlib import Path

folder = Path(__file__).resolve().parent
p = json.loads((folder / "profile.json").read_text())
stamp = p["captured_at"]
source = {
    "id": "profile",
    "label": "Iowa directory and crawler quality audit",
    "path": "profile.json",
    "query": {
        "engine": "python",
        "language": "python",
        "sql": 'from analyze import analyze\nprofile = analyze(readonly_unraid_snapshot)\nprofile["source_reconciliation"], profile["crawl"], profile["published_directory_fields"]',
        "description": "Analyze read-only immutable catalog entities, saved campaign status/evidence and exact native-ID crosswalks. All measures are Iowa snapshots; source counts are assertions and overlap.",
        "tables_used": [
            "stores pack: entities",
            "maps pack: entities",
            "iowa-statewide-20261019/status.json",
            "iowa-statewide-20261019/evidence/*.json",
            "iowa-chains-20261019/status.json",
            "iowa discovery: candidates.jsonl",
            "iowa discovery: crosswalk.jsonl",
            "iowa discovery: reviews.jsonl",
            "iowa discovery: excluded.jsonl",
        ],
        "filters": [
            "Iowa store records at the captured serving generation",
            "No live source downloads or crawl execution",
            "Single structured branch match only for crawler field counts",
            "Published field presence is not current accuracy",
        ],
        "executed_at": stamp,
    },
}
ledger = {
    "id": "ledger",
    "label": "Jev post-fetch review counts",
    "path": "jev-stage-counts.json",
    "query": {
        "engine": "sqlite",
        "language": "sql",
        "sql": "SELECT campaign,stage,state,count(*) FROM decisions GROUP BY campaign,stage,state",
        "tables_used": ["jev-crawl-budget.sqlite: decisions"],
        "filters": ["Iowa campaign rows for page-review interpretation"],
        "executed_at": stamp,
    },
}
blocks = []


def md(id, body, sourceid="profile"):
    b = {"id": id, "type": "markdown", "body": body}
    if sourceid:
        b["sourceId"] = sourceid
    blocks.append(b)


def tableblock(id):
    blocks.append({"id": id + "-block", "type": "table", "tableId": id})


def chartblock(id):
    blocks.append({"id": id + "-block", "type": "chart", "chartId": id})


md("title", "# Iowa store data review", None)
md(
    "summary",
    """## Executive Summary

- **Discovery is ahead of crawl enrichment.** The directory has 735 Iowa records. Across the Iowa pilot and statewide run, 96 unique stores completed retailer-page checks; the statewide run retained 95 rich evidence files.
- **SNAP and OSM substantially broaden the reference base.** The downloaded Iowa subsets contain 2,882 SNAP retailer assertions and 666 OSM place candidates. Their categories differ and their records overlap.
- **The crawler has not yet produced accepted aisle or map data.** Only 41 saved pages have one structured branch match. All saved evidence remains pending acceptance, and no interior map or item-to-aisle placement was found.
- **Use existing evidence before increasing crawl volume.** Linked downloads contain candidates for missing coordinates, phones, hours and websites. Address normalization and selection of the primary grocery business are immediate verification gaps.""",
)
md(
    "definitions",
    """## Separate discovery, page checks and usable facts

A source assertion is one provider record. A published directory record is a canonical API record, not a certified count of distinct operating stores. A completed page check can publish a “not found” map result. A retained evidence file contains source excerpts and structured candidates; it does not imply that its fields have been accepted into the API.

The comparison is an October 20, 2026 snapshot. Completeness percentages use the 735 published Iowa directory records, not all groceries actually operating in Iowa. The original statewide campaign covered 362 directory records and 319 URLs, before the subsequent directory expansion.""",
)
md(
    "source-comparison",
    """## The reference sources are much larger than the completed crawl

**SNAP lists many retailers outside our grocery scope.** Its broad Grocery Store, Supermarket and Super Store categories contain 705 rows before pharmacy and other format checks. Some grocers also occur in Other, so 705 is not an exact grocery census. OSM has 508 supermarket-tagged records and five grocery-tagged records, plus 153 candidates in department-store, wholesale and general-shop categories.

The exact counts below are different populations, not parts of one total. SNAP and OSM native assertions have been linked conservatively to 621 and 276 published directory records; 211 records have links to both sources. Among the 96 completed Iowa page checks, 69 have a confirmed SNAP link and 46 have a confirmed OSM link. An unresolved link does not prove the store is absent from the provider.""",
)
tableblock("counts")
md(
    "queue",
    """## Most current directory records have no saved crawler evidence

**The statewide run saved evidence for 95 stores, or 12.9% of the current directory.** An earlier pilot contributes one additional completed store check, making 96 unique completed checks overall, or 13.1% of the directory.

The chart splits the 319 statewide targets into mutually exclusive outcomes. Host holds include inherited blocks and failed requests; they do not mean all 133 stores were individually fetched. The 43 original records without usable URLs were outside that target list. The 373 subsequently added directory records were also outside this campaign.""",
)
chartblock("outcomes")
md(
    "review-stage",
    """**There were 97 statewide post-fetch Jev reviews:** the 95 saved page checks and two pages held after review. The earlier pilot had nine post-fetch reviews; most repeated stores from the statewide run. Across both Iowa runs, the records identify 98 unique stores reaching page review. Those two held pages did not produce retained rich evidence files. Earlier request-attempt flags are incomplete, so they cannot establish a precise historical HTTP request total.""",
    None,
)
md(
    "captured",
    """## The crawler saved useful candidates, with limited app-ready enrichment

**Every saved statewide page has a source URL, retrieval time, content hash and visible-text excerpt.** Of 95 files, 41 have exactly one matching structured branch, ten have two matching business candidates, and 44 have no matching structured candidate. The ten ambiguous Walmart pages all contain Grocery and Photo Center descriptions. Selection of the grocery business needs to use business type and page hierarchy as well as address.

The table counts fields on the 41 singly matched pages. All remain review-required. The nine department records describe services or departments; they are not aisle numbers or an interior route graph. No interior map links, geographic map links or item-placement candidates were retained by this campaign.""",
)
tableblock("crawler-fields")
md(
    "acceptance",
    """**No saved evidence bundle has been promoted to accepted enrichment.** All 96 Iowa map-pack records are “not found” results, not 96 maps. Separately, earlier Woodman’s work outside Iowa retained map-link candidates; it does not establish Iowa map coverage.

Text excerpts are bounded: 21 of the 95 reach the 4,500-character limit. The retained evidence is not a complete archive of the page. Address-matching failures and unsupported page structures can therefore look like missing fields even when a human can see them on the website.""",
)
md(
    "directory-fields",
    """## Basic location coverage is strong; contact and opening details are uneven

**Every published record has a name and usable postal address.** Only 610 have separate street/city fields and coordinates: 125 existing Hy-Vee records retain full postal-address strings without structured coordinates.

The chart measures populated API fields across all 735 records. A populated value may come from bulk data and is not necessarily recently verified. All 357 populated hours fields and all 287 populated phone fields come from the older ATP-backed records; none of the 373 newly added records has those normalized fields yet. Opening status and timezone remain unknown throughout this snapshot.""",
)
chartblock("fields")
md(
    "quick-wins",
    """## Linked source data can fill some gaps without new retailer requests

**There are concrete enrichment leads in already downloaded, identity-linked assertions.** Counts below are distinct directory records per missing field; a store may appear in several rows, so do not add them. These are candidates for field review, not pre-approved replacements. Preserve conflicting values and source freshness rather than silently choosing one.

The wider OSM download contains 349 phone tags, 275 hours tags, 245 website tags and 16 wheelchair tags. Many are already-known values, unresolved identities or candidates outside the final grocery scope; those raw tag counts are not counts of additional verified app fields.""",
)
tableblock("opportunities")
md(
    "next",
    """## Prioritize verification and promotion before another broad crawl

1. **Join reference evidence into each crawler target.** Supply canonical IDs, source-native IDs, structured addresses, coordinates, matching websites and conflicts to deterministic checks and Jev. Review the 501 unresolved discovery assertions without treating them as 501 distinct missing shops.
2. **Improve branch extraction.** Normalize address abbreviations and full postal strings, retain JSON-LD business types and parent/department context, and distinguish the main grocer from co-located Photo Center or pharmacy entries. Support bounded visible-HTML evidence when JSON-LD is absent.
3. **Review the existing missing-field candidates.** Promote corroborated coordinates, contact details and hours into immutable directory updates, with field-level source and verification dates. Preserve all canonical IDs and household overrides.
4. **Make opening-hours data usable.** Store an explicit timezone, holiday exceptions and freshness before the app presents an “open now” claim. Unknown must remain distinct from closed.
5. **Collect the shopping details Bòrd needs.** Prioritize branch-specific pickup/delivery links, department names, entrance/directions and accessibility evidence. For navigation, retain reviewed category-to-aisle mappings, map version, branch association and display rights.
6. **Keep product inventory outside this crawl.** Prices, availability and full assortment are intentionally absent. If later required, use appropriate product/price providers and Bòrd’s private purchase history, with date and branch identity; preserve the current no-inventory crawl scope.""",
)
md(
    "questions",
    """## Further questions that determine the next validation pass

- Can a complete current Iowa grocery-license roster be reconciled with SNAP, OSM and the directory? Without that denominator, 100% statewide coverage remains unverified.
- Which unresolved assertions describe existing stores, stale businesses or out-of-scope formats?
- Which saved page descriptions can be safely promoted after improved extraction, without fetching again?
- Which branches matter most for household shopping, so limited requests and paid review can focus on missing useful fields?""",
)
md(
    "caveats",
    """## Caveats and assumptions

Source counts refer to downloaded Iowa subsets, not national exports. Source record presence, SNAP enrollment, OSM tagging, a recent snapshot clock and current store operation are distinct facts. The SNAP reference’s data clock is October 7, 2026; the statewide page evidence was retrieved October 18–19, Central time. OSM snapshot time does not establish when every individual field was checked.

Some identity matching is intentionally conservative. Published canonical IDs and native crosswalks are unique, but physical-location completeness and all stale/duplicate business assertions have not been independently certified. Field presence is not a freshness or accuracy score. This review performed no new crawler requests, paid calls, serving data changes or companion app changes.""",
)
sources = [source, ledger]
counts = [
    {"population": "SNAP retailers", "records": 2882, "meaning": "All Iowa retailer types"},
    {
        "population": "SNAP broad grocery types",
        "records": 705,
        "meaning": "Before format exclusions",
    },
    {"population": "OSM places", "records": 666, "meaning": "Five queried shop categories"},
    {"population": "OSM grocery tags", "records": 513, "meaning": "Supermarket or grocery tags"},
    {
        "population": "Published directory",
        "records": 735,
        "meaning": "Combined source-backed records",
    },
    {
        "population": "Completed Iowa page checks",
        "records": 96,
        "meaning": "Unique stores across two runs",
    },
    {
        "population": "Saved statewide page evidence",
        "records": 95,
        "meaning": "Retained rich evidence files",
    },
]
fields = [
    {
        "field": r["field"]
        .replace("Known opening or closure status", "Open/closed")
        .replace("Usable postal address", "Address")
        .replace("Structured street and city", "Street/city"),
        "records": r["present"],
        "share": r["present"] / 735,
        "denominator": 735,
    }
    for r in p["published_directory_fields"]
    if r["field"] not in ["Name", "Structured street and city"]
]
outcomes = [
    {"outcome": name, "records": count, "share": count / 319, "denominator": 319}
    for name, count in [
        ("Saved", 95),
        ("Post-fetch hold", 2),
        ("Pre-fetch hold", 89),
        ("Host hold", 133),
    ]
]
charts = []
for id, title, dataset, x, denominator in [
    ("outcomes", "Statewide target outcomes", "outcomes", "outcome", 319),
    ("fields", "Published field availability", "fields", "field", 735),
]:
    charts.append(
        {
            "id": id,
            "title": title,
            "subtitle": f"{denominator} records in this comparison",
            "type": "bar",
            "dataset": dataset,
            "sourceId": "profile",
            "valueFormat": "number",
            "encodings": {
                "x": {
                    "field": x,
                    "type": "nominal",
                    "label": "Outcome" if id == "outcomes" else "Field",
                },
                "y": {"field": "records", "type": "quantitative", "label": "Records"},
                "tooltip": [
                    {
                        "field": "share",
                        "type": "quantitative",
                        "format": "percent",
                        "label": "Share of denominator",
                    }
                ],
            },
        }
    )


def table(id, title, dataset, columns, sort):
    return {
        "id": id,
        "title": title,
        "dataset": dataset,
        "sourceId": "profile",
        "defaultSort": {"field": sort, "direction": "desc"},
        "columns": columns,
    }


text = lambda key, label: {"field": key, "label": label, "type": "text"}
number = lambda key, label: {"field": key, "label": label, "format": "number"}
tables = [
    table(
        "counts",
        "Source and crawl counts",
        "counts",
        [text("population", "Population"), number("records", "Records"), text("meaning", "Scope")],
        "records",
    ),
    table(
        "crawler-fields",
        "Structured crawler fields",
        "crawler-fields",
        [text("field", "Field"), number("pages", "Pages"), number("saved_pages", "Saved pages")],
        "pages",
    ),
    table(
        "opportunities",
        "Missing-field candidates",
        "opportunities",
        [text("field", "Field"), number("records", "Records")],
        "records",
    ),
]
artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": "Iowa store data review",
        "description": "Discovery, crawler yield and useful enrichment gaps.",
        "generatedAt": stamp,
        "filters": [],
        "cards": [],
        "charts": charts,
        "tables": tables,
        "sources": sources,
        "blocks": blocks,
    },
    "snapshot": {
        "version": 1,
        "generatedAt": stamp,
        "status": "ready",
        "datasets": {
            "counts": counts,
            "outcomes": outcomes,
            "fields": fields,
            "crawler-fields": p["crawler_fields_single_branch"],
            "opportunities": [
                {
                    "field": label.replace("Missing ", "")
                    .replace(" with linked SNAP coordinates", " (SNAP)")
                    .replace(" with linked OSM phone", " (OSM)")
                    .replace(" with linked OSM hours", " (OSM)")
                    .replace(" with linked OSM website", " (OSM)"),
                    "records": n,
                }
                for label, n in p["enrichment_opportunities"].items()
            ],
        },
        "access_issues": [],
    },
    "sources": sources,
}
import runpy

runpy.run_path(str(folder / "report-sources.py"))["bind_sources"](artifact, p)
for t in artifact["manifest"]["tables"]:
    for c in t["columns"]:
        c["sizing"] = "content"
(folder / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")
notes = {
    "audience": "product stakeholders",
    "delivery_mode": "html",
    "runtime_reason": "Unclassified runtime; portable HTML selected by report skill. No hosted publication.",
    "required_structure": {
        "Title": "title",
        "Executive Summary": "summary",
        "Key findings with visual evidence": [
            "definitions",
            "source-comparison",
            "queue",
            "captured",
            "directory-fields",
            "quick-wins",
        ],
        "Recommended next steps": "next",
        "Further questions": "questions",
        "Caveats and assumptions": "caveats",
    },
    "chart_map": [
        {
            "id": "outcomes",
            "question": "Where did the statewide target queue stop?",
            "family": "comparison bar",
            "grain": "319 target records, mutually exclusive outcomes",
            "palette": "shared default categorical/neutral",
            "qa": "packaged portable verifier",
        },
        {
            "id": "fields",
            "question": "Which published fields are populated?",
            "family": "comparison bar",
            "grain": "735 directory records for every field",
            "palette": "shared default",
            "qa": "packaged portable verifier",
        },
    ],
    "table_rationale": "Source populations have incomparable scopes, so exact lookup is clearer than one misleading coverage bar. Structured crawler fields and enrichment candidates need exact count lookup.",
    "omitted_trend": "Only one serving snapshot; no current-accuracy or temporal trend is supported.",
    "scope": "Read-only live snapshot plus offline analysis; no source/paid requests or serving changes.",
    "notebook": "analysis.ipynb is an inspectable replay; analysis itself was executed via analyze.py.",
}
(folder / "report-notes.json").write_text(json.dumps(notes, indent=2) + "\n")
print("Built canonical aggregate report with", len(blocks), "blocks")
