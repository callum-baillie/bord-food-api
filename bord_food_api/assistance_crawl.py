"""Operator-page enrichment after grocery crawls, using the shared robots/frontier.

No products, stock, credentials or model decisions are inferred from page text.
Exact name and full premises are required; facility hours stay facility hours.
"""

import copy
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .assistance import optional_contact
from .crawl_history import CrawlHistory, exception_details, prior_holds
from .crawl_runtime import run_map_discovery
from .crawlers import parse_page
from .domain import content_hash
from .platform import atomic_json
from .runtime import Lease
from .store_enrichment import public_url
from .store_hours import structured_hours, valid_timezone


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def extract_operator_fields(html, site, *, now, domain_reviewed=False):
    candidates = []
    address = site.get("address") or {}
    for script in parse_page(html).scripts:
        try:
            value = json.loads(script)
        except ValueError:
            continue
        pending = value if isinstance(value, list) else [value]
        visited = 0
        while pending:
            node = pending.pop()
            visited += 1
            if visited > 5000:
                raise ValueError("assistance_page_complexity_limit")
            if not isinstance(node, dict):
                continue
            pending.extend(node.get("@graph", []))
            addr = node.get("address")
            if not isinstance(addr, dict) or _key(node.get("name")) != _key(site.get("name")):
                continue
            if not all(
                address.get(k) and _key(address[k]) == _key(addr.get(v))
                for k, v in [
                    ("street", "streetAddress"),
                    ("city", "addressLocality"),
                    ("region", "addressRegion"),
                ]
            ):
                continue
            values = {}
            for field, native in [("phone", "telephone"), ("email", "email"), ("website", "url")]:
                if normalized := optional_contact(field, node.get(native)):
                    values[field] = normalized
            if node.get("openingHoursSpecification"):
                try:
                    values["facility_hours"] = structured_hours(node["openingHoursSpecification"])
                except (ValueError, TypeError, KeyError):
                    pass
            if node.get("timezone") and valid_timezone(node["timezone"]):
                values["timezone"] = node["timezone"]
            for prop in node.get("additionalProperty", []):
                if (
                    isinstance(prop, dict)
                    and prop.get("name") == "operating_status"
                    and prop.get("value") in {"open", "temporarily_closed", "permanently_closed"}
                ):
                    values["operating_status"] = prop["value"]
            if values:
                candidates.append(values)
    if len(candidates) != 1:
        return {
            "status": "review_required",
            "reason": "ambiguous_or_missing_exact_premises",
            "fields": {},
        }
    return {
        "status": "accepted",
        "fields": candidates[0],
        "checked_at": now,
        "matched_exact_premises": True,
        "domain_reviewed": domain_reviewed,
        "html_sha256": content_hash(html),
        "schedule_scope": "facility",
    }


def apply_operator_evidence(platform, row, generation):
    result = copy.deepcopy(row)
    if row.get("kind") not in {"assistance_site", "osm_assistance_site"}:
        return result
    osm = row["kind"].startswith("osm_")
    source = "osm_assistance_operator" if osm else "assistance_operator"
    evidence = platform.get_by_source(
        "osm_assistance_evidence" if osm else "assistance_evidence",
        source,
        row["id"],
        generation=generation,
    )
    if not evidence or evidence.get("site_identity_hash") != content_hash(
        {"name": row.get("name"), "address": row.get("address"), "website": row.get("website")}
    ):
        return result
    if evidence.get("model_review"):
        result["model_review"] = evidence["model_review"]
    for field, assertion in evidence.get("assertions", {}).items():
        authoritative = assertion.get("domain_reviewed") is True
        if time.time() - assertion["checked_at"] > (7 if field == "facility_hours" else 30) * 86400:
            continue
        value = assertion["value"]
        old = result.get(field)
        if field == "facility_hours":
            old = result.get("schedule", {}).get("raw")
        if old and old != value:
            result.setdefault("field_conflicts", []).append(
                {
                    "field": field,
                    "source_value": old,
                    "operator_value": value,
                    "source_url": evidence["source_url"],
                    "resolution": "operator_preferred" if authoritative else "review_required",
                }
            )
        if (old and not authoritative) or field == "operating_status" and not authoritative:
            continue
        verified_at = (
            datetime.fromtimestamp(assertion["checked_at"], UTC).isoformat()
            if authoritative
            else None
        )
        if field == "facility_hours":
            result["schedule"] = {
                "raw": value,
                "scope": "facility",
                "timezone": result.get("timezone"),
                "verified_at": verified_at,
                "status": "verified" if authoritative else "unverified",
                "exceptions": [],
            }
        else:
            result[field] = value
        result.setdefault("field_provenance", {})[field] = {
            "status": "operator_verified" if authoritative else "source_reported",
            "verified_at": verified_at,
            "source_url": evidence["source_url"],
            "checked_at": assertion["checked_at"],
            "source_id": source,
            "license": None,
            "rights_basis": "public_factual_metadata_only",
            "upstream_pack_license": row.get("source_license"),
        }
        if authoritative:
            result["last_verified_at"] = max(result.get("last_verified_at") or "", verified_at)
            result["data_quality"] = "partially_verified"
        if field == "operating_status":
            result["permanently_closed"] = value == "permanently_closed"
    if result.get("schedule"):
        result["schedule"]["timezone"] = result.get("timezone")
    return result


def target_plan(platform, states, *, datasets=("directory", "osm")):
    targets, gaps = [], []
    seen_urls = {}
    for dataset in datasets:
        for site in platform.iter_records(
            "osm_assistance_site" if dataset == "osm" else "assistance_site"
        ):
            if site.get("address", {}).get("region") not in states:
                continue
            target = {
                "store_id": site["id"],
                "site_id": site["id"],
                "kind": site["kind"],
                "dataset": dataset,
                "name": site["name"],
                "expected_branch": site["name"],
                "source_address": site.get("address"),
                "url": site.get("website"),
            }
            address = site.get("address") or {}
            reason = "missing_site_name" if not site.get("name") else None
            if not all(address.get(k) for k in ("street", "city", "region")):
                reason = "missing_structured_premises"
            try:
                url = public_url(site.get("website"))
                if urlsplit(url).scheme != "https" or urlsplit(url).query:
                    raise ValueError()
                target["url"] = url
            except (ValueError, TypeError):
                reason = reason or "missing_or_unsafe_operator_url"
            if reason:
                gaps.append({**target, "reason": reason})
            else:
                seen_urls.setdefault(target["url"], []).append(target)
    for entries in seen_urls.values():
        if len(entries) > 1:
            gaps.extend({**t, "reason": "shared_operator_url_requires_review"} for t in entries)
        else:
            targets.extend(entries)
    return {"targets": targets, "gaps": gaps}


def crawl_target(
    platform,
    target,
    config,
    *,
    transport_factory=None,
    clock=time.time,
    sleep=time.sleep,
    random_uniform=None,
    external_check=lambda: None,
    review=None,
):
    now = clock()
    identifier = config["campaign_id"]
    run_directory = platform.root / "crawl-campaigns" / identifier
    run_directory.mkdir(parents=True, exist_ok=True)
    status = {
        "campaign_id": identifier,
        "state": "running",
        "targets": {target["site_id"]: {"state": "running"}},
        "started_at": now,
    }
    source = "osm_assistance_operator" if target["dataset"] == "osm" else "assistance_operator"
    history_config = {**config, "targets": [target], "state": target["source_address"]["region"]}
    history = CrawlHistory(platform.root)
    history.register(history_config)
    history.ingest(status, history_config)
    if prior_holds(platform.root, target):
        status["targets"][target["site_id"]] = {
            "state": "prior_history_hold",
            "reason": "prior_history_hold",
        }
        status["state"] = "finished_with_holds"
        history.ingest(status, history_config)
        atomic_json(run_directory / "status.json", status)
        return status
    job_id = platform.control.enqueue(
        source, identifier, operation="assistance_enrichment", version=str(now)
    )
    job = platform.control.claim("food-assistance", job_id=job_id)
    if not job:
        raise ValueError("assistance_crawl_claim_unavailable")
    try:
        with Lease(platform.control, job, 120, 20) as lease:
            lease.policy_check = external_check
            lease.check()
            original = platform.get(target["kind"], target["site_id"])
            if (
                not original
                or original.get("name") != target["name"]
                or original.get("address") != target["source_address"]
                or original.get("website") != target["url"]
            ):
                raise ValueError("assistance_target_snapshot_changed")
            collected = []

            def sink(html, _target):
                collected.append(
                    extract_operator_fields(
                        html,
                        original,
                        now=clock(),
                        domain_reviewed=urlsplit(target["url"]).hostname
                        in config.get("reviewed_operator_hosts", []),
                    )
                )

                if review is not None:
                    reviewed = review(html, target, collected[-1])
                    if reviewed:
                        collected[-1]["model_review"] = reviewed
                        identity = reviewed["identity"]
                        if identity["choice"] != "consistent" or identity["confidence"] < 0.9:
                            collected[-1]["status"] = "review_required"

            policy = {
                **config,
                "allowed_host": urlsplit(target["url"]).hostname,
                "scope_prefix": "/",
                "approved_targets": [target],
                "_check": lease.check,
                "_fields_only": True,
                "_evidence_sink": sink,
            }
            options = {"clock": clock, "sleep": sleep, "entity_kind": target["kind"]}
            if transport_factory is not None:
                options["transport_factory"] = transport_factory
            if random_uniform is not None:
                options["random_uniform"] = random_uniform
            run_map_discovery(platform, job, policy, **options)
            if not collected or collected[0]["status"] != "accepted":
                status["targets"][target["site_id"]] = {
                    "state": "review_required",
                    "reason": "page_review",
                }
            else:
                item = collected[0]
                evidence_kind = (
                    "osm_assistance_evidence"
                    if target["dataset"] == "osm"
                    else "assistance_evidence"
                )
                previous = platform.get_by_source(evidence_kind, source, target["site_id"]) or {}
                assertions = previous.get("assertions", {})
                for field, value in item["fields"].items():
                    assertions[field] = {
                        "value": value,
                        "checked_at": item["checked_at"],
                        "domain_reviewed": item["domain_reviewed"],
                    }
                payload = {
                    "target_site_id": target["site_id"],
                    "site_identity_hash": content_hash(
                        {
                            "name": original.get("name"),
                            "address": original.get("address"),
                            "website": original.get("website"),
                        }
                    ),
                    "source_url": target["url"],
                    "assertions": assertions,
                    "history": (previous.get("history", []) + [item])[-20:],
                    "model_review": item.get("model_review"),
                    "source_license": original.get("source_license"),
                    "source_refs": original.get("source_refs", []),
                }
                platform.sync(
                    source,
                    target["source_address"]["region"],
                    content_hash(payload),
                    [{"kind": evidence_kind, "source_key": target["site_id"], "payload": payload}],
                    complete=False,
                    parser_version="assistance-operator-v1",
                    fence=job,
                )
                status["targets"][target["site_id"]] = {
                    "state": "published",
                    "reason": "page_check_completed",
                    "fields": sorted(item["fields"]),
                }
            platform.control.finish(job)
        status["state"] = (
            "finished"
            if status["targets"][target["site_id"]]["state"] == "published"
            else "finished_with_holds"
        )
    except (OSError, ValueError, RuntimeError) as error:
        status["targets"][target["site_id"]] = {"state": "host_blocked", **exception_details(error)}
        status["state"] = "finished_with_holds"
        if str(error) == "assistance_operator_stopped":
            status["state"] = "stopped"
            status["targets"][target["site_id"]] = {
                "state": "interrupted_requires_review",
                "reason": "interrupted",
            }
        if str(error) == "decision_budget_exhausted":
            status["state"] = "paused_budget"
            status["targets"][target["site_id"]] = {
                "state": "deferred_budget",
                "reason": "budget_exhausted",
            }
        platform.control.finish(job, state="failed", reason="assistance_target_failed")
    status["completed_at"] = clock()
    history.ingest(status, history_config)
    atomic_json(run_directory / "status.json", status)
    return status
