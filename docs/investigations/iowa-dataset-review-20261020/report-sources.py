"""Execute the exact SQLite JSON queries exposed by report source controls."""

import json
import sqlite3


def bind_sources(artifact, profile):
    queries = {
        "outcomes": """WITH p AS (SELECT json(:profile) j), counts AS (
 SELECT 'Saved' outcome, json_extract(j,'$.crawl.saved_evidence_pages') records, json_extract(j,'$.crawl.target_count') denominator FROM p
 UNION ALL SELECT 'Post-fetch hold',json_extract(j,'$.crawl.review_reasons.page_review'),json_extract(j,'$.crawl.target_count') FROM p
 UNION ALL SELECT 'Pre-fetch hold',json_extract(j,'$.crawl.review_reasons.pre_fetch_confidence'),json_extract(j,'$.crawl.target_count') FROM p
 UNION ALL SELECT 'Host hold',json_extract(j,'$.crawl.target_outcomes.host_blocked'),json_extract(j,'$.crawl.target_count') FROM p
) SELECT *,1.0*records/denominator share FROM counts""",
        "fields": """SELECT CASE json_extract(value,'$.field') WHEN 'Usable postal address' THEN 'Address' WHEN 'Known opening or closure status' THEN 'Open/closed' ELSE json_extract(value,'$.field') END field,
 json_extract(value,'$.present') records, json_extract(value,'$.total') denominator,
 1.0*json_extract(value,'$.present')/json_extract(value,'$.total') share
FROM json_each(:profile,'$.published_directory_fields')
WHERE json_extract(value,'$.field') NOT IN ('Name','Structured street and city')""",
        "crawler-fields": """SELECT json_extract(value,'$.field') field,json_extract(value,'$.pages') pages,
 json_extract(value,'$.saved_pages') saved_pages FROM json_each(:profile,'$.crawler_fields_single_branch')""",
        "opportunities": """SELECT CASE key WHEN 'Missing coordinates with linked SNAP coordinates' THEN 'Coordinates (SNAP)'
 WHEN 'Missing phone with linked OSM phone' THEN 'Phone (OSM)' WHEN 'Missing hours with linked OSM hours' THEN 'Hours (OSM)'
 WHEN 'Missing website with linked OSM website' THEN 'Website (OSM)' END field,value records
FROM json_each(:profile,'$.enrichment_opportunities')""",
        "counts": """WITH p AS (SELECT json(:profile) j)
 SELECT 'SNAP retailers' population,json_extract(j,'$.raw_source_counts.snap') records,'All Iowa retailer types' meaning FROM p
 UNION ALL SELECT 'SNAP broad grocery types',json_extract(j,'$.snap_broad_grocery_types_before_exclusions'),'Before format exclusions' FROM p
 UNION ALL SELECT 'OSM places',json_extract(j,'$.raw_source_counts.osm'),'Five queried shop categories' FROM p
 UNION ALL SELECT 'OSM grocery tags',json_extract(j,'$.osm_shop_types.supermarket')+json_extract(j,'$.osm_shop_types.grocery'),'Supermarket or grocery tags' FROM p
 UNION ALL SELECT 'Published directory',json_extract(j,'$.directory_records'),'Combined source-backed records' FROM p
 UNION ALL SELECT 'Completed Iowa page checks',json_extract(j,'$.crawl.completed_iowa_stores_all_campaigns'),'Unique stores across two runs' FROM p
 UNION ALL SELECT 'Saved statewide page evidence',json_extract(j,'$.crawl.saved_evidence_pages'),'Retained rich evidence files' FROM p""",
    }
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    artifact["manifest"]["sources"][0].pop("query", None)
    artifact["sources"][0].pop("query", None)
    for name, sql in queries.items():
        dataset = [dict(r) for r in db.execute(sql, {"profile": json.dumps(profile)})]
        artifact["snapshot"]["datasets"][name] = dataset
        source = {
            "id": "data-" + name,
            "label": "Iowa audit: " + name.replace("-", " "),
            "path": "profile.json",
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": sql,
                "description": "Execute this query with :profile bound to the saved profile.json. The underlying profile was computed by analyze.py from a read-only Unraid snapshot.",
                "tables_used": ["profile.json"],
                "filters": ["Iowa only; source/crawl denominators as labeled"],
                "executed_at": profile["captured_at"],
            },
        }
        artifact["manifest"]["sources"].append(source)
        # artifact.sources and manifest.sources share the same list in this builder.
        for widget in artifact["manifest"]["charts"] + artifact["manifest"]["tables"]:
            if widget.get("dataset") == name:
                widget["sourceId"] = source["id"]
    db.close()
