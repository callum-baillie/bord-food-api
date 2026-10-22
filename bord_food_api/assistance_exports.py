"""Reviewed municipal ArcGIS/Socrata and authorized HSDS-export normalization.

Provider profiles supply exact field maps and rights, never inferred licenses.
No connector signs up for 211 or treats public search as a bulk entitlement.
"""

import re

from .assistance import (
    TYPES,
    annotate_fields,
    base_payload,
    coordinates,
    optional_contact,
    provenance,
    records_for_site,
    safe_text,
)


def validate_profile(profile):
    if (
        profile.get("reuse_reviewed") is not True
        or not profile.get("license")
        or profile["license"].lower() in {"unknown", "unconfirmed"}
        or not profile.get("attribution")
    ):
        raise ValueError("assistance_local_source_rights_review_required")
    if not re.fullmatch(r"[a-z0-9_-]{1,80}", str(profile.get("id", ""))):
        raise ValueError("assistance_safe_local_profile_id_required")
    if profile.get("service_type") not in TYPES:
        raise ValueError("assistance_explicit_service_type_required")
    if not profile.get("id") or not profile.get("state"):
        raise ValueError("assistance_local_profile_identity_required")


def parse_local_row(row, profile, *, point=None):
    validate_profile(profile)
    mapping = profile["fields"]

    def field(name):
        key = mapping.get(name)
        return row.get(key) if key else None

    key = field("id")
    if key is None or not field("name"):
        raise ValueError("assistance_local_record_identity_missing")
    if field("state") and field("state") != profile["state"]:
        raise ValueError("assistance_source_state_mismatch")
    key = profile["id"] + ":" + str(key)
    ref = provenance(
        "community_food_assistance",
        key,
        license=profile["license"],
        attribution=profile["attribution"],
        source_url=profile["url"],
        verified=field("verified_at"),
    )
    address = {
        "street": safe_text(field("street"), 500),
        "city": safe_text(field("city"), 200),
        "region": profile["state"],
        "postal_code": safe_text(field("postal_code"), 20),
        "country": "US",
    }
    site = base_payload(
        field("name"),
        address,
        point or coordinates(field("latitude"), field("longitude")),
        ref,
        schedule=field("facility_hours"),
        verified=field("verified_at"),
    )
    site.update(
        phone=optional_contact("phone", field("phone")),
        email=optional_contact("email", field("email")),
        website=optional_contact("website", field("website")),
        service_types=[profile["service_type"]],
        operator=safe_text(field("operator")),
        accessibility=safe_text(field("accessibility")),
    )
    if field("permanently_closed") is True:
        site.update(operating_status="permanently_closed", permanently_closed=True)
    service = {
        "type": profile["service_type"],
        "schedule": {
            **site["schedule"],
            "raw": safe_text(field("service_hours")),
            "scope": "service",
        },
        "eligibility": safe_text(field("eligibility")),
        "application_process": safe_text(field("application_process")),
        "documents_required": safe_text(field("documents_required")),
        "service_area": safe_text(field("service_area")),
        "languages": field("languages"),
        "appointment_required": field("appointment_required")
        if type(field("appointment_required")) is bool
        else None,
        "public_access": "unknown",
        "inventory_status": "unknown",
        "data_quality": "unverified",
    }
    events = []
    if field("event_id") is not None:
        events = [
            {
                "source_key": profile["id"] + ":event:" + str(field("event_id")),
                "service_key": key + ":service:0",
                "starts_at": field("starts_at"),
                "ends_at": field("ends_at"),
                "status": field("event_status") or "unknown",
                "timezone": field("timezone"),
            }
        ]
    annotate_fields(site, ref)
    annotate_fields(service, ref)
    yield from records_for_site("community_food_assistance", key, site, [service], events)


def parse_hsds_bundle(bundle, profile):
    """Join services through service_at_location, never a blind organization cross join.

    Input is an explicitly authorized, bounded export bundle of HSDS tables.
    Missing association links or location references quarantine the import.
    """
    validate_profile(profile)
    tables = {}
    for table in (
        "locations",
        "services",
        "service_at_location",
        "organizations",
        "addresses",
        "phones",
        "schedules",
    ):
        rows = bundle.get(table, [])
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError("assistance_hsds_export_budget")
        tables[table] = rows

    def indexed(table):
        rows = tables[table]
        result = {str(r["id"]): r for r in rows}
        if len(result) != len(rows):
            raise ValueError("assistance_hsds_duplicate_identity")
        return result

    locations, services = indexed("locations"), indexed("services")
    organizations = indexed("organizations")
    links = {}
    for link in tables["service_at_location"]:
        location, service = str(link["location_id"]), str(link["service_id"])
        if location not in locations or service not in services:
            raise ValueError("assistance_hsds_dangling_relation")
        links.setdefault(location, []).append(services[service])
    for key, location in locations.items():
        linked = links.get(key, [])
        selected = [
            s
            for s in linked
            if profile.get("service_types", {}).get(str(s["id"]), s.get("type")) in TYPES
        ]
        if not selected:
            continue
        addresses = [r for r in tables["addresses"] if str(r.get("location_id")) == key]
        if len(addresses) != 1:
            raise ValueError("assistance_hsds_address_ambiguous")
        address = addresses[0]
        if address.get("state_province") != profile["state"]:
            raise ValueError("assistance_source_state_mismatch")
        ref = provenance(
            "community_food_assistance",
            profile["id"] + ":" + key,
            license=profile["license"],
            attribution=profile["attribution"],
            source_url=profile["url"],
        )
        site = base_payload(
            location.get("name"),
            {
                "street": address.get("address_1"),
                "city": address.get("city"),
                "region": address.get("state_province"),
                "postal_code": address.get("postal_code"),
                "country": "US",
            },
            coordinates(location.get("latitude"), location.get("longitude")),
            ref,
        )
        site["service_types"] = sorted(
            {profile.get("service_types", {}).get(str(s["id"]), s.get("type")) for s in selected}
        )
        phones = [
            r
            for r in tables["phones"]
            if str(r.get("location_id")) == key and not r.get("service_id")
        ]
        site["phone"] = (
            optional_contact("phone", phones[0].get("number")) if len(phones) == 1 else None
        )
        site["website"] = optional_contact("website", location.get("url"))
        output = []
        for service in selected:
            org = organizations.get(str(service.get("organization_id")), {})
            schedules = [
                r
                for r in tables["schedules"]
                if str(r.get("service_id")) == str(service["id"])
                and (not r.get("location_id") or str(r["location_id"]) == key)
            ]
            output.append(
                {
                    "source_key": profile["id"] + ":" + key + ":service:" + str(service["id"]),
                    "type": profile.get("service_types", {}).get(
                        str(service["id"]), service.get("type")
                    ),
                    "organization": org.get("name"),
                    "description": safe_text(service.get("description")),
                    "eligibility": safe_text(service.get("eligibility")),
                    "application_process": safe_text(service.get("application_process")),
                    "documents_required": safe_text(service.get("required_documents")),
                    "fees": safe_text(service.get("fees")),
                    "service_area": safe_text(service.get("service_area")),
                    "schedule": {
                        "raw": safe_text(schedules),
                        "scope": "service",
                        "timezone": None,
                        "verified_at": None,
                        "status": "unverified",
                    },
                    "public_access": "unknown",
                    "inventory_status": "unknown",
                    "data_quality": "unverified",
                }
            )
        annotate_fields(site, ref)
        yield from records_for_site(
            "community_food_assistance", profile["id"] + ":" + key, site, output
        )
