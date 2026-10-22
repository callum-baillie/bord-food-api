"""Bounded public food-assistance acquisition through an injected source transport.

An incomplete page chain, duplicate native key, Overpass error, unknown rights,
or scope drift aborts the candidate before publication. Feeds remain additive:
absence is not closure. Checkpoint hashes make repeat full snapshots incremental.
"""

import hashlib
import json
import time
from urllib.parse import urlencode

from .assistance import (
    FEED_TYPES,
    iso_time,
    parse_feed_resource,
    parse_osm_element,
    validate_states,
)
from .domain import content_hash


def overpass_url(state):
    validate_states([state])
    query = (
        '[out:json][timeout:90];area["ISO3166-2"="US-' + state + '"]["admin_level"="4"]->.s;'
        '(nwr["social_facility"~"^(food_bank|soup_kitchen)$"](area.s);nwr["amenity"="food_sharing"](area.s););out meta center tags;'
    )
    return "https://overpass-api.de/api/interpreter?" + urlencode({"data": query})


def acquire_assistance(source, policy, directory, fetch, *, check=lambda: None, cursor=None):
    from .sources import Artifact

    states = validate_states(policy.get("states", ["IA"]))
    last_request = [None]

    def pace():
        delay = policy.get("request_delay_seconds", 10 if source == "osm_food_assistance" else 1)
        if type(delay) not in (int, float) or not 0 <= delay <= 300:
            raise ValueError("assistance_source_request_delay_invalid")
        if last_request[0] is not None:
            check()
            policy.get("_sleep", time.sleep)(delay)
        last_request[0] = time.time()

    maximum_pages = policy.get("max_pages", 100)
    page_size = policy.get("page_size", 1000)
    if (
        type(maximum_pages) is not int
        or not 1 <= maximum_pages <= 200
        or type(page_size) is not int
        or not 1 <= page_size <= 1000
    ):
        raise ValueError("assistance_pagination_budget_invalid")
    max_rows = policy.get("max_records", 100000)
    if type(max_rows) is not int or not 1 <= max_rows <= 200000:
        raise ValueError("assistance_record_budget_invalid")
    if source == "feed_america" and (
        policy.get("rights_reviewed") is not True or not policy.get("approved_upstream_sources")
    ):
        raise ValueError("assistance_feed_rights_review_required")
    for state in states:
        check()
        destination = directory / (state + "-candidate.jsonl")
        artifacts, seen = [], set()
        count = 0
        source_time = None

        def read(url, state=state, artifacts=artifacts):
            check()
            pace()
            path, metadata = fetch(Artifact(state, url, "current"))
            if path.stat().st_size > min(
                policy.get("max_artifact_bytes", 16 * 1024**2), 16 * 1024**2
            ):
                raise ValueError("assistance_page_byte_limit")
            value = json.loads(path.read_text())
            artifacts.append(
                {
                    "url": url,
                    "sha256": metadata["sha256"],
                    "bytes": metadata.get("bytes"),
                    "etag": metadata.get("etag"),
                }
            )
            return value

        with destination.open("w") as handle:

            def write(records, seen=seen):
                nonlocal count
                for record in records:
                    check()
                    key = (record["kind"], record["source_key"])
                    if key in seen:
                        raise ValueError("assistance_duplicate_native_identity")
                    seen.add(key)
                    count += 1
                    if count > max_rows:
                        raise ValueError("assistance_record_budget_exceeded")
                    handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")

            if source == "osm_food_assistance":
                value = read(overpass_url(state))
                if value.get("remark") or not isinstance(value.get("elements"), list):
                    raise ValueError("assistance_osm_partial_or_error")
                source_time = (value.get("osm3s") or {}).get("timestamp_osm_base")
                if not iso_time(source_time):
                    raise ValueError("assistance_osm_source_clock_missing")
                previous = (cursor or {}).get("partitions", {}).get(state, cursor or {})
                if (
                    previous.get("source_observed_at")
                    and source_time < previous["source_observed_at"]
                ):
                    raise ValueError("assistance_osm_clock_regression")
                for row in value["elements"]:
                    write(parse_osm_element(row, state=state))
            elif source == "feed_america":
                for resource_type in FEED_TYPES:
                    for page in range(1, maximum_pages + 1):
                        url = "https://feedam.org/api/resources/bulk?" + urlencode(
                            {
                                "state": state,
                                "type": resource_type,
                                "limit": page_size,
                                "page": page,
                            }
                        )
                        value = read(url)
                        rows = value.get("resources")
                        if (
                            value.get("success") is not True
                            or not isinstance(rows, list)
                            or value.get("page") != page
                            or len(rows) > page_size
                            or value.get("count") != len(rows)
                        ):
                            raise ValueError("assistance_feed_page_invalid")
                        if any(row.get("resource_type") != resource_type for row in rows):
                            raise ValueError("assistance_feed_filter_ignored")
                        for row in rows:
                            write(
                                parse_feed_resource(
                                    row,
                                    state=state,
                                    approved_sources=policy["approved_upstream_sources"],
                                )
                            )
                        if len(rows) < page_size:
                            break
                    else:
                        raise ValueError("assistance_feed_page_budget_incomplete")
            else:
                raise ValueError("assistance_source_unsupported")
        with destination.open("rb") as candidate:
            digest = hashlib.file_digest(candidate, "sha256").hexdigest()

        def records(path=destination):
            with path.open() as handle:
                for line in handle:
                    yield json.loads(line)

        yield {
            "partition": state,
            "release": digest,
            "records": records(),
            "complete": False,
            "cursor": {
                "state": state,
                "source_observed_at": source_time,
                "snapshot_hash": digest,
                "complete": False,
                "record_count": count,
            },
            "metadata": {
                "artifacts": artifacts,
                "source_observed_at": source_time,
                "license_separated": True,
                "checked_at": time.time(),
                "manifest_hash": content_hash(artifacts),
            },
        }


def acquire_reviewed_exports(policy, directory, fetch, *, check=lambda: None):
    from .assistance import coordinates
    from .assistance_exports import parse_hsds_bundle, parse_local_row, validate_profile
    from .sources import Artifact

    profiles = policy.get("profiles", [])
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 50:
        raise ValueError("assistance_explicit_local_profiles_required")
    for profile in profiles:
        validate_profile(profile)
        state = validate_states([profile["state"]])[0]
        if profile["format"] not in {"arcgis", "socrata", "hsds_bundle"}:
            raise ValueError("assistance_local_format_unsupported")
        artifacts = []
        seen = set()
        count = 0
        output = directory / (profile["id"] + "-candidate.jsonl")
        size, max_pages = 1000, min(policy.get("max_pages", 100), 200)
        with output.open("w") as handle:
            for page in range(max_pages):
                check()
                base = profile["url"]
                field = profile.get("fields", {}).get("id", "")
                if profile["format"] == "arcgis":
                    url = (
                        base.rstrip("/")
                        + "/query?"
                        + urlencode(
                            {
                                "where": "1=1",
                                "outFields": "*",
                                "outSR": 4326,
                                "f": "json",
                                "orderByFields": field,
                                "resultOffset": page * size,
                                "resultRecordCount": size,
                            }
                        )
                    )
                elif profile["format"] == "socrata":
                    url = (
                        base
                        + "?"
                        + urlencode({"$limit": size, "$offset": page * size, "$order": field})
                    )
                else:
                    url = base
                path, metadata = fetch(Artifact(profile["id"], url, "current"))
                if path.stat().st_size > 16 * 1024**2:
                    raise ValueError("assistance_page_byte_limit")
                value = json.loads(path.read_text())
                artifacts.append({"url": url, "sha256": metadata["sha256"]})
                if profile["format"] == "hsds_bundle":
                    chunks = [parse_hsds_bundle(value, profile)]
                    done = True
                elif profile["format"] == "arcgis":
                    features = value.get("features")
                    if value.get("error") or not isinstance(features, list):
                        raise ValueError("assistance_arcgis_error")
                    chunks = []
                    for feature in features:
                        geometry = feature.get("geometry")
                        if geometry and value.get("spatialReference", {}).get("wkid") != 4326:
                            raise ValueError("assistance_arcgis_coordinates_not_wgs84")
                        chunks.append(
                            parse_local_row(
                                feature["attributes"],
                                profile,
                                point=coordinates(geometry.get("y"), geometry.get("x"))
                                if geometry
                                else None,
                            )
                        )
                    done = len(features) < size and value.get("exceededTransferLimit") is not True
                    if not features and not done:
                        raise ValueError("assistance_arcgis_incomplete_page")
                else:
                    if not isinstance(value, list):
                        raise ValueError("assistance_socrata_error")
                    chunks = [parse_local_row(row, profile) for row in value]
                    done = len(value) < size
                for chunk in chunks:
                    for record in chunk:
                        key = (record["kind"], record["source_key"])
                        if key in seen:
                            raise ValueError("assistance_duplicate_native_identity")
                        seen.add(key)
                        count += 1
                        if count > min(policy.get("max_records", 100000), 200000):
                            raise ValueError("assistance_record_budget_exceeded")
                        handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
                if done:
                    break
            else:
                raise ValueError("assistance_local_page_budget_incomplete")
        with output.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()

        def records(path=output):
            with path.open() as handle:
                for line in handle:
                    yield json.loads(line)

        yield {
            "partition": profile["id"],
            "release": digest,
            "records": records(),
            "complete": False,
            "cursor": {
                "state": state,
                "complete": False,
                "record_count": count,
                "profile_hash": content_hash(profile),
            },
            "metadata": {
                "artifacts": artifacts,
                "license": profile["license"],
                "attribution": profile["attribution"],
            },
        }
