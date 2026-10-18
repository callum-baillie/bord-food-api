#!/usr/bin/env python3
"""Offline planning-package validator; never downloads, crawls or runs the API.
Requires a locally installed jsonschema package. Does not install dependencies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in pairs:
        if k in result:
            raise ValueError(f"Duplicate JSON key: {k}")
        result[k] = v
    return result


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    results = []

    def passed(name: str, detail: Any) -> None:
        results.append({"check": name, "status": "passed", "detail": detail})

    docs = {str(p.relative_to(root)): load(p) for p in root.rglob("*.json")}
    passed("json_parse_and_unique_keys", len(docs))
    validators = {}
    for p in (root / "schemas").glob("*.schema.json"):
        s = load(p)
        Draft202012Validator.check_schema(s)
        validators[p.name] = Draft202012Validator(s, format_checker=FormatChecker())
    passed("json_schema_validity", len(validators))
    for p in (root / "examples").rglob("*.response.json"):
        d = load(p)
        validators["envelope.schema.json"].validate(d)
        if p.parent.name == "real":
            schema = (
                "chain.schema.json"
                if d["data"]["entity_type"] == "store_chain"
                else "store.schema.json"
            )
            validators[schema].validate(d["data"])
            require(d["meta"]["catalog_generation"] is None, "Example became published data")
    for p in (root / "examples/synthetic").glob("*.json"):
        d = load(p)
        schema = (
            "synthetic-fixture.schema.json"
            if "fixture_kind" in d
            else "price-observation.schema.json"
            if p.name == "price-observation.json"
            else "change-event.schema.json"
            if p.name == "change-event.json"
            else None
        )
        if schema:
            validators[schema].validate(d)
    passed(
        "example_schema_validation", "Native, real, synthetic, price and change examples validate"
    )
    chain = docs["examples/real/walmart-chain.response.json"]["data"]
    store = docs["examples/real/walmart-coralville-2827.response.json"]["data"]
    require(chain["chain_id"] == store["chain_id"], "Chain/store link mismatch")
    require(store["external_ids"]["walmart_us_store_number"] == "2827", "Wrong store ID")
    require(
        store["coordinates"]["latitude"] is None and store["coordinates"]["longitude"] is None,
        "Invented coordinates",
    )
    count = chain["footprint"]["reported_store_count"]
    require(sum(count["format_counts"].values()) == count["value"], "Count breakdown mismatch")
    for base in ["walmart-chain", "walmart-coralville-2827"]:
        orig = load(root / "examples/reference-v0.1" / (base + ".example.json"))
        orig.pop("schema_version")
        require(
            orig == load(root / "examples/real" / (base + ".response.json"))["data"],
            "Real facts altered",
        )
    passed(
        "real_fact_preservation",
        "Original facts retained; links and count arithmetic valid; missing coordinates remain null",
    )
    for file in [
        "production.example.json",
        "development-offline.example.json",
        "nationwide-discovery.example.json",
    ]:
        d = load(root / "configs" / file)
        validators["policy.schema.json"].validate(d)
        require(
            not d["crawler"]["enabled"] and not d["network"]["crawl_enabled"], "Crawler enabled"
        )
        require(
            not d["network"]["allow_paid_sources"] and not d["media"]["download_map_assets"],
            "Paid/media activation",
        )
        require(
            d["scheduler"]["heartbeat_seconds"] < d["scheduler"]["lease_seconds"],
            "Heartbeat/lease invalid",
        )
        if file.startswith("development"):
            require(
                d["network"]["mode"] == "offline" and not d["scheduler"]["enabled"],
                "Development acquisition enabled",
            )
            require(all(not s["enabled"] for s in d["sources"].values()), "Offline source enabled")
        else:
            require(
                d["network"]["mode"] == "bulk_only" and d["bootstrap"]["mode"] == "automatic",
                "Runtime default mismatch",
            )
    passed(
        "activation_policy",
        "No seeds; offline implementation; automatic bulk-only runtime; crawling/paid sources off",
    )
    registry = load(root / "configs/source-registry.example.json")
    validators["source-registry.schema.json"].validate(registry)
    ids = [s["source_id"] for s in registry["sources"]]
    require(len(ids) == len(set(ids)), "Duplicate source IDs")
    ledger = load(root / "reference/source-ledger.json")["sources"]
    ledger_ids = {s["source_id"] for s in ledger}
    require(len(ledger_ids) == len(ledger), "Duplicate evidence IDs")
    for s in registry["sources"]:
        require(set(s["source_refs"]) <= ledger_ids, "Unresolved source evidence")
    for a, b in [
        ("source-registry.example.json", "sources.manifest.example.json"),
        ("refresh-policy.example.json", "field-refresh-policy.json"),
    ]:
        require(load(root / "configs" / a) == load(root / "configs" / b), "Config aliases diverge")
    passed("source_registry", {"descriptors": len(ids), "evidence_entries": len(ledger)})
    research = load(root / "reference/chain-research/us_supermarket_registry.json")
    require(
        len(research["ranked_chains"]) == 120 and len(research["unranked_candidates"]) == 180,
        "Research count mismatch",
    )
    with (root / "reference/chain-research/ranked_chains.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        require(len(list(csv.DictReader(f))) == 120, "CSV count mismatch")
    require(research["status"] == "working_seed_not_exhaustive_census", "Research caveat removed")
    for item in load(root / "reference/input-artifacts.json")["inputs"]:
        if item["included_path"]:
            require(
                digest(root / item["included_path"]) == item["sha256"],
                "Source copy changed: " + item["input_id"],
            )
    passed(
        "reference_integrity",
        "120 ranked + 180 candidates; retained files match original checksums",
    )
    tasks = load(root / "progress/tasks.json")["tasks"]
    graph = {t["id"]: t for t in tasks}
    require(len(graph) == len(tasks), "Duplicate tasks")
    done, visiting = set(), set()

    def visit(k: str) -> None:
        require(k in graph, "Unknown dependency " + k)
        require(k not in visiting, "Task cycle " + k)
        if k in done:
            return
        visiting.add(k)
        for dep in graph[k]["depends_on"]:
            visit(dep)
        visiting.remove(k)
        done.add(k)

    tests_text = (root / "docs/13-TESTS.md").read_text()
    for t in tasks:
        visit(t["id"])
        require(t["live_verification"] == "not_performed", "Unexpected live activation claim")
        require(
            t["status"] in {"not_started", "in_progress", "completed_offline", "handoff_complete"},
            "Unknown task status",
        )
        if t["status"] in {"completed_offline", "handoff_complete"}:
            require(
                bool(t["implementation_evidence"]), "Completed task lacks implementation evidence"
            )
        for test in t["acceptance_tests"]:
            require(f"| {test} |" in tests_text, "Missing test " + test)
    passed(
        "task_dag",
        {"total_tasks": len(tasks), "v1_tasks": sum(t["in_main_v1_scope"] for t in tasks)},
    )
    scene = load(root / "examples/synthetic/snapshot-diff-case.json")["scenario"]
    before = {r["source_key"]: r for r in scene["prior"]}
    after = {r["source_key"]: r for r in scene["incoming"]}
    expected = scene["expected"]
    require(
        sorted(after.keys() - before.keys()) == expected["new_store_keys"],
        "New-store fixture mismatch",
    )
    require(
        sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
        == expected["changed_store_keys"],
        "Changed fixture mismatch",
    )
    require(
        sorted(k for k in before.keys() & after.keys() if before[k] == after[k])
        == expected["unchanged_store_keys"],
        "Unchanged fixture mismatch",
    )
    for row in load(root / "examples/synthetic/gtin-cases.json")["scenario"]["cases"]:
        value = row["input"]
        valid = value.isascii() and value.isdigit() and len(value) in [8, 12, 13, 14]
        if valid:
            total = sum(
                int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(value[:-1]))
            )
            valid = (10 - total % 10) % 10 == int(value[-1])
        require(valid == row["valid"], "GTIN expected validity mismatch")
        if valid:
            require(value.zfill(14) == row["canonical"], "GTIN expected canonical mismatch")
    passed(
        "synthetic_expectations",
        "Roster comparisons and identifier arithmetic checked; not app tests",
    )
    sql_checks = {}
    for p in (root / "contracts").glob("*.sql"):
        sql = p.read_text()
        require(
            not re.search(r"\b(?:INSERT\s+INTO|REPLACE\s+INTO)\b", sql, re.IGNORECASE),
            "Seed rows in DDL",
        )
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(sql)
            require(
                db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "DDL integrity failure"
            )
            require(
                not db.execute("PRAGMA foreign_key_check").fetchall(), "DDL foreign-key failure"
            )
            sql_checks[p.name] = "empty schema executes and integrity checks pass"
        finally:
            db.close()
    passed("illustrative_sql_in_memory", sql_checks)
    spec = load(root / "contracts/openapi.blueprint.json")
    require(spec["openapi"] == "3.1.0", "Unexpected spec version")

    def refs(obj: Any) -> None:
        if isinstance(obj, dict):
            if "$ref" in obj:
                r = obj["$ref"]
                require(r.startswith("#/"), "Nonlocal OpenAPI ref")
                value = spec
                for part in r[2:].split("/"):
                    value = value[part.replace("~1", "/").replace("~0", "~")]
            for v in obj.values():
                refs(v)
        elif isinstance(obj, list):
            for v in obj:
                refs(v)

    refs(spec)
    operations = []
    for route, methods in spec["paths"].items():
        required = set(re.findall(r"\{([^}]+)\}", route))
        for op in methods.values():
            operations.append(op["operationId"])
            actual = {p["name"] for p in op["parameters"] if p["in"] == "path" and p["required"]}
            require(required == actual, "Path parameter mismatch " + route)
            require(
                "200" in op["responses"] and "503" in op["responses"], "Missing response " + route
            )
    require(len(operations) == len(set(operations)), "Duplicate operations")
    for schema in spec["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)
    passed(
        "openapi_structural_checks",
        {
            "paths": len(spec["paths"]),
            "operations": len(operations),
            "full_openapi_semantic_validation": "not_run",
        },
    )
    for p in root.rglob("*.md"):
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^\s)]+)\)", p.read_text()):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            require(
                (p.parent / target.split("#")[0]).exists(),
                "Broken relative link " + str(p) + " -> " + target,
            )
    passed("markdown_relative_links", "All destinations exist")
    manifest = root / "MANIFEST.sha256"
    if manifest.exists():
        count = 0
        for line in manifest.read_text().splitlines():
            sha, rel = line.split("  ", 1)
            p = (root / rel).resolve()
            require(p.is_relative_to(root) and p.is_file(), "Unsafe/missing manifest path " + rel)
            require(digest(p) == sha, "Checksum mismatch " + rel)
            count += 1
        passed("sha256_manifest", count)
    else:
        results.append(
            {
                "check": "sha256_manifest",
                "status": "created_and_checked_after_report",
                "detail": "Final read-only pass verifies the manifest after this report is written.",
            }
        )
    report = {
        "artifact": "Bord-Food-API-Codex-Implementation-Plan",
        "prepared_on": "2026-10-17",
        "status": "passed",
        "scope": "planning_package_only",
        "checks": results,
        "not_performed": [
            "Application implementation or tests",
            "TypeScript example compilation",
            "Full OpenAPI semantic validation",
            "Source crawlers",
            "Live bulk data acquisition/import",
            "Authenticated retailer API requests",
            "Docker/Unraid deployment",
        ],
    }
    if args.report:
        output = args.report if args.report.is_absolute() else root / args.report
        output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
