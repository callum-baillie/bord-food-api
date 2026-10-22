"""Rebuild AI-assisted planning estimates from retained public aggregates, offline.

No network, paid model calls, catalog writes, or changes to crawl activation.
The assistant selected the transparent heuristic; numbers are not a model survey.
"""

import csv
import datetime
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIPS_CODES = "01 AL,02 AK,04 AZ,05 AR,06 CA,08 CO,09 CT,10 DE,12 FL,13 GA,15 HI,16 ID,17 IL,18 IN,19 IA,20 KS,21 KY,22 LA,23 ME,24 MD,25 MA,26 MI,27 MN,28 MS,29 MO,30 MT,31 NE,32 NV,33 NH,34 NJ,35 NM,36 NY,37 NC,38 ND,39 OH,40 OK,41 OR,42 PA,44 RI,45 SC,46 SD,47 TN,48 TX,49 UT,50 VT,51 VA,53 WA,54 WV,55 WI,56 WY"
FIPS = dict(item.split() for item in FIPS_CODES.split(","))
METHOD = {
    "version": "ai-assisted-public-anchors-v1",
    "authorship": "Codex selected assumptions and interpreted results; no separate paid AI requests",
    "scope": "Physical supermarkets and general-line independent groceries, plus grocery supercenters and warehouse clubs; exclude convenience, dollar stores, standalone pharmacies and specialist food shops",
    "point": "Round (2 * Census 2023 grocery-plus-club establishments + SNAP grocery-format records) / 3 to nearest 10, halves up",
    "low": "Floor 0.85 * min(Census anchor, SNAP anchor) to multiple of 10",
    "high": "Ceil 1.20 * max(Census anchor, SNAP anchor) to multiple of 10",
    "rationale": "Census has a closer industry definition independent of crawler discovery; SNAP supplies a newer participating-retailer cross-check. Weighting and buffers are uncalibrated planning judgments, not empirical probabilities.",
    "confidence": "low; ranges are scenario envelopes, not statistical confidence intervals",
    "catalog_independence": "Catalog counts never enter point estimates or ranges",
    "use": "Soft coverage investigation targets only; never stop discovery, relax evidence gates, infer closure or certify completeness from counts",
}


def load(name):
    return json.loads((ROOT / name).read_text())


def main():
    census = load("census-state-counts.json")
    ranking = json.loads((ROOT.parent / "small-states-20261020/ranking.json").read_text())
    catalog = load("catalog-snapshot.json")
    counts = {}
    for row in census["rows"]:
        assert row["lfo"] == "-", "Avoid double-counting legal-form subtotals"
        key = (row["fipstate"], row["naics"])
        assert key not in counts
        counts[key] = int(row["est"])
    # Published national figures include DC; the requested output has only 50 states.
    assert sum(v for (f, n), v in counts.items() if n == "445110") == 62947
    assert sum(v for (f, n), v in counts.items() if n == "452311") == 7961
    assert len(counts) == 102
    refs = {r["state"]: r for r in ranking["states"]}
    assert len(refs) == 50 and set(refs) == set(FIPS.values())
    rows = []
    for fips, state in FIPS.items():
        grocery = counts[(fips, "445110")]
        club = counts[(fips, "452311")]
        cbp = grocery + club
        snap = refs[state]["snap_grocery_format_records"]
        point = int(math.floor(((2 * cbp + snap) / 3) / 10 + 0.5) * 10)
        low = int(math.floor(0.85 * min(cbp, snap) / 10) * 10)
        high = int(math.ceil(1.20 * max(cbp, snap) / 10) * 10)
        actual = catalog["canonical_state_counts"][state]
        assert 0 < low <= point <= high
        rows.append(
            {
                "state": state,
                "name": refs[state]["name"],
                "rough_target": point,
                "planning_low": low,
                "planning_high": high,
                "census_2023_groceries": grocery,
                "census_2023_clubs_supercenters": club,
                "census_2023_combined": cbp,
                "snap_grocery_format_records": snap,
                "catalog_records": actual,
                "catalog_to_target_ratio": round(actual / point, 4),
                "count_signal": "below_planning_range"
                if actual < low
                else "above_planning_range"
                if actual > high
                else "within_planning_range_review_still_required",
                "source_disagreement": "material"
                if max(cbp, snap) / min(cbp, snap) >= 1.4
                else "moderate_or_small",
                "confidence": "low",
                "census_complete": False,
            }
        )
    rows.sort(key=lambda r: r["name"])
    summary = {
        k: sum(r[k] for r in rows)
        for k in [
            "rough_target",
            "planning_low",
            "planning_high",
            "catalog_records",
            "census_2023_combined",
            "snap_grocery_format_records",
        ]
    }
    output = {
        "generated_at": "2026-10-21",
        "method": METHOD,
        "catalog_snapshot": catalog,
        "census_source": {k: v for k, v in census.items() if k != "rows"},
        "snap_source": {k: ranking[k] for k in ["source_url", "source_clock", "acquired_at"]},
        "summary": summary,
        "states": rows,
    }
    (ROOT / "estimates.json").write_text(json.dumps(output, indent=2) + "\n")
    with (ROOT / "estimates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    build_report(output)
    print(
        json.dumps(
            {
                "checks": "50 unique states; 102 unique Census totals; national source sums; ordered ranges; no catalog-derived estimates",
                "summary": summary,
                "iowa": next(r for r in rows if r["state"] == "IA"),
            }
        )
    )


def build_report(output):
    rows = output["states"]
    summary = output["summary"]
    below = sum(r["count_signal"] == "below_planning_range" for r in rows)
    stamp = datetime.datetime.fromtimestamp(
        output["catalog_snapshot"]["captured_at"], datetime.UTC
    ).isoformat()
    sources = [
        {
            "id": "estimates",
            "label": "AI-assisted state planning estimates",
            "path": "estimates.json",
            "query": {
                "language": "python",
                "engine": "offline-python",
                "description": "Weighted independent public counts; current canonical records joined only for comparison",
                "sql": "import math\npoint = math.floor(((2 * census + snap) / 3) / 10 + 0.5) * 10\nlow = math.floor(0.85 * min(census, snap) / 10) * 10\nhigh = math.ceil(1.20 * max(census, snap) / 10) * 10",
                "tables_used": [
                    "census-state-counts.json",
                    "small-states-20261020/ranking.json",
                    "catalog-snapshot.json",
                ],
                "filters": [
                    "50 states only; DC and territories excluded",
                    "Census NAICS 445110 and 452311; all legal forms only",
                ],
                "executed_at": stamp,
            },
        },
        {
            "id": "census",
            "label": "Census 2023 State Business Patterns",
            "url": output["census_source"]["source_url"],
        },
        {
            "id": "snap",
            "label": "USDA FNS SNAP public retailer aggregates",
            "url": output["snap_source"]["source_url"],
        },
    ]
    blocks = [
        {"id": "title", "type": "markdown", "body": "# Grocery store coverage targets"},
        {
            "id": "summary",
            "type": "markdown",
            "sourceId": "estimates",
            "body": f"## Executive Summary\n\n**Use approximately {summary['rough_target']:,} stores nationally as a rough planning target.** The summed state scenarios span {summary['planning_low']:,}–{summary['planning_high']:,}; this is not a statistical interval.\n\n**Discovery remains partial.** {below} states have catalog record counts below even their lower planning scenarios.\n\n**Counts cannot certify accuracy.** AI selected a transparent estimation method using Census and SNAP aggregates. No extra paid model requests were made; store identity, open status and field accuracy still require evidence.",
        },
        {
            "id": "scope",
            "type": "markdown",
            "body": "## Count physical groceries across chains and independents\n\nInclude general-line groceries, supermarkets, grocery supercenters and warehouse clubs. Exclude convenience stores, dollar stores, standalone pharmacies and specialist meat or produce shops. General merchandise stores with limited groceries and employer-free businesses are imperfectly covered by the anchors. Each row compares published canonical records with an estimate of physical stores; published records have not all been crawled or independently verified.",
        },
        {
            "id": "findings",
            "type": "markdown",
            "sourceId": "estimates",
            "body": "## The active smaller-state cohort still needs broader discovery\n\nThe downloadable data retains both public-source counts; the table compares planning ranges and catalog counts. Ratios are record-count comparisons, not verified coverage. Low counts can indicate missing source discovery; high counts can indicate wider scope, duplication or undercounting in the public anchors. Review all three possibilities.",
        },
        {"id": "table", "type": "table", "tableId": "states", "layout": "full"},
        {
            "id": "iowa",
            "type": "markdown",
            "sourceId": "estimates",
            "body": "## Iowa is near the count target, with identity work still needed\n\nIowa has 735 catalog records against a rough target of 710 (590–860 planning range). The underlying anchors are 709 Census establishments and 705 grocery-format SNAP records. Agreement at aggregate level is encouraging, but missing independent stores may be offset by duplicates, permanently closed stores or scope differences. Compare matched addresses and operating status before describing statewide coverage.",
        },
        {
            "id": "next",
            "type": "markdown",
            "body": "## Use the targets to direct verification\n\n1. Prioritize states below the lower planning range for SNAP, OpenStreetMap, state inspection or licensing data and chain locator discovery.\n2. Report distinct in-scope operating stores, reviewed closures, unresolved identities and excluded formats separately.\n3. Check source overlap by address and coordinates, plus county and chain gaps; do not just compare totals.\n4. Continue phone, hours, timezone and provenance checks even when a count is near target. Targets do not change crawl limits, budgets, activation or acceptance gates.",
        },
        {
            "id": "questions",
            "type": "markdown",
            "body": "## What could change the estimates?\n\nWhich current SNAP records are outside our scope? How many independent groceries do not accept SNAP or have employees? Which counties and chains have poor discovery? State licensing and inspection lists can help answer these questions, but some include restaurants or convenience stores and need filtering.",
        },
        {
            "id": "caveats",
            "type": "markdown",
            "body": f"## Caveats and assumptions\n\nCensus is a 2023 employer-establishment count downloaded October 21, 2026; SNAP aggregates were acquired October 20, 2026. Catalog counts are a fixed snapshot at {stamp}, while the crawl continues. Census and SNAP have different definitions and overlap; they are not additive. The 2:1 weighting and 15%/20% buffers are AI-selected judgments, not validated growth rates or confidence bounds. All estimates have low confidence. The 50-state total excludes DC and territories. Never delete records, infer closure, claim exact missing-store counts or stop crawling solely because of these estimates.",
        },
    ]
    fields = [
        ("name", "State", "text"),
        ("planning_target", "Target (range)", "text"),
        ("catalog_records", "Records", "number"),
    ]
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Grocery store coverage targets",
            "generatedAt": stamp,
            "sources": sources,
            "blocks": blocks,
            "tables": [
                {
                    "id": "states",
                    "title": "50-state grocery planning targets",
                    "subtitle": "Physical-store estimates versus published record counts; October 21, 2026 snapshot",
                    "dataset": "states",
                    "sourceId": "estimates",
                    "defaultSort": {"field": "name", "direction": "asc"},
                    "columns": [
                        {"field": k, "label": label, "type": kind} for k, label, kind in fields
                    ],
                }
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": stamp,
            "status": "ready",
            "datasets": {"states": rows},
        },
    }
    cohort = {"WY", "AK", "VT", "ND", "DE", "SD", "MT", "RI", "NH", "HI", "ID", "WV"}
    query = """SELECT state, 'Published records' AS series, catalog_records AS count
FROM state_estimates WHERE in_cohort = 1
UNION ALL
SELECT state, 'Rough planning target' AS series, rough_target AS count
FROM state_estimates WHERE in_cohort = 1
ORDER BY state, series"""
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        names = list(rows[0])
        connection.execute(
            "CREATE TABLE state_estimates (" + ", ".join(names) + ", in_cohort INTEGER)"
        )
        connection.executemany(
            "INSERT INTO state_estimates VALUES ("
            + ",".join("?" for _ in range(len(names) + 1))
            + ")",
            [tuple(r[k] for k in names) + (int(r["state"] in cohort),) for r in rows],
        )
        table_query = "SELECT *, CAST(rough_target AS TEXT) || ' (' || planning_low || '–' || planning_high || ')' AS planning_target FROM state_estimates ORDER BY rough_target, state"
        table_rows = [dict(r) for r in connection.execute(table_query)]
        chart_rows = [dict(r) for r in connection.execute(query)]
    chart_source = {
        "id": "cohort_sql",
        "label": "Smaller-state count comparison",
        "path": "estimates.json",
        "query": {
            "sql": query,
            "engine": "sqlite",
            "language": "sql",
            "tables_used": ["state_estimates"],
            "description": "Load state estimates into an in-memory table, select the 12 active campaign states and compare published record counts with planning targets",
            "executed_at": stamp,
        },
    }
    table_source = {
        **chart_source,
        "id": "states_sql",
        "label": "50-state estimate comparison",
        "query": {
            **chart_source["query"],
            "sql": table_query,
            "description": "Read all 50 retained state estimates and catalog counts, ordered by rough planning target",
        },
    }
    artifact["manifest"]["sources"].append(table_source)
    artifact["manifest"]["tables"][0]["source"] = table_source
    artifact["manifest"]["tables"][0].pop("sourceId", None)
    artifact["snapshot"]["datasets"]["states"] = table_rows
    artifact["manifest"]["sources"].append(chart_source)
    artifact["snapshot"]["datasets"]["cohort"] = chart_rows
    artifact["manifest"]["charts"] = [
        {
            "id": "cohort",
            "title": "Smaller-state records and planning targets",
            "subtitle": "12 active campaign states; record counts are not verified coverage",
            "type": "bar",
            "dataset": "cohort",
            "source": chart_source,
            "layout": "full",
            "encodings": {
                "x": {"field": "state", "type": "ordinal", "label": "State"},
                "y": {"field": "count", "type": "quantitative", "label": "Stores or records"},
                "color": {"field": "series", "type": "nominal", "label": "Count basis"},
            },
        }
    ]
    artifact["manifest"]["charts"][0]["source"] = chart_source
    artifact["manifest"]["charts"][0].pop("sourceId", None)
    artifact["manifest"]["blocks"].insert(
        4, {"id": "cohort-chart", "type": "chart", "chartId": "cohort", "layout": "full"}
    )
    (ROOT / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")


if __name__ == "__main__":
    main()
