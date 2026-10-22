"""Read-only, generation-bound assistance search with separate ODbL selection."""

import time
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import Query

from .assistance import freshness


def register_assistance_routes(
    router, *, platform, page, response, find, require, generation, fail, envelope, errors
):
    def kind(entity, dataset):
        return ("osm_assistance_" if dataset == "osm" else "assistance_") + {
            "sites": "site",
            "services": "service",
            "events": "event",
        }[entity]

    def view(row, gen):
        from .assistance_crawl import apply_operator_evidence

        return freshness(apply_operator_evidence(platform, row, gen), now=time.time())

    @router.get(
        "/v1/food-assistance/{entity}",
        response_model=envelope[list[dict[str, Any]]],
        responses=errors,
    )
    def assistance_list(
        entity: Literal["sites", "services", "events"],
        dataset: Literal["directory", "osm"] = "directory",
        query: Annotated[str | None, Query(max_length=200)] = None,
        state: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
        postal_code: Annotated[str | None, Query(pattern=r"^\d{5}(?:-\d{4})?$")] = None,
        service_type: Literal[
            "pantry",
            "food_bank",
            "meal",
            "community_fridge",
            "mobile_pantry",
            "food_assistance_unspecified",
        ]
        | None = None,
        site_id: Annotated[str | None, Query(max_length=160)] = None,
        lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
        lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
        radius_km: Annotated[float, Query(ge=0.1, le=100)] = 10,
        include_closed: bool = False,
        include_past_events: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ):
        from .native_api import distance_km

        if (lat is None) != (lon is None):
            fail(422, "INVALID_INPUT", "Latitude and longitude must be supplied together.")
        now = time.time()

        def matches(row, gen):
            address = row.get("address") or {}
            if state and address.get("region") != state:
                return False
            if postal_code and address.get("postal_code") != postal_code:
                return False
            if service_type and service_type not in row.get("service_types", [row.get("type")]):
                return False
            if site_id and row.get("site_id", row.get("id")) != site_id:
                return False
            display = view(row, gen)
            if not include_closed and display.get("operating_status") == "permanently_closed":
                return False
            if (
                entity == "events"
                and not include_past_events
                and (
                    row.get("status") == "cancelled"
                    or row.get("ends_at")
                    and datetime.fromisoformat(row["ends_at"]).timestamp() < now
                )
            ):
                return False
            if lat is not None:
                point = row.get("coordinates") or {}
                if (
                    not point
                    or distance_km(lat, lon, point["latitude"], point["longitude"]) > radius_km
                ):
                    return False
            return True

        filters = {
            "query": query,
            "dataset": dataset,
            "state": state,
            "postal_code": postal_code,
            "service_type": service_type,
            "site_id": site_id,
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "include_closed": include_closed,
            "include_past_events": include_past_events,
        }
        return page(
            kind(entity, dataset),
            "assistance_osm" if dataset == "osm" else "assistance",
            filters,
            limit,
            cursor,
            matches,
            transform=view,
        )

    @router.get(
        "/v1/food-assistance/{entity}/{identifier}",
        response_model=envelope[dict[str, Any]],
        responses=errors,
    )
    def assistance_detail(
        entity: Literal["sites", "services", "events"],
        identifier: str,
        dataset: Literal["directory", "osm"] = "directory",
    ):
        require("assistance_osm" if dataset == "osm" else "assistance")
        gen = generation()
        return response(
            view(find(kind(entity, dataset), identifier, gen), gen),
            gen,
            warnings=[
                {
                    "code": "CONFIRM_SERVICE_DETAILS",
                    "message": "Confirm distribution times and eligibility with the operator; office hours do not establish food distribution or inventory.",
                }
            ],
        )
