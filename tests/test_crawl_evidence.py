import json

from bord_food_api.crawl_evidence import collect_evidence


def page(*nodes):
    return (
        '<h1>Imaginary North</h1><script type="application/ld+json">'
        + json.dumps(list(nodes))
        + '</script><a href="/north.pdf">Store Map</a>'
    )


def target():
    return {
        "store_id": "store-fixture",
        "url": "https://retailer.test/stores/north",
        "expected_branch": "Imaginary North",
        "source_address": {
            "street": "10 Imaginary St",
            "city": "Synthetic",
            "region": "IA",
            "postal_code": "50000",
        },
    }


def store():
    return {
        "@type": "GroceryStore",
        "@id": "#north",
        "name": "Imaginary North",
        "address": {"streetAddress": "10 Imaginary St", "postalCode": "50000"},
        "telephone": "synthetic",
        "openingHoursSpecification": [{"dayOfWeek": "Monday", "opens": "08:00", "closes": "22:00"}],
        "specialOpeningHoursSpecification": [
            {"validFrom": "2026-12-25", "opens": "00:00", "closes": "00:00"}
        ],
        "amenityFeature": {"name": "pickup", "value": True},
        "additionalProperty": {"name": "Aisle 7", "value": "Baking"},
        "hasMap": "https://maps.test/geographic",
    }


def test_store_and_aisle_evidence_omit_catalog_prices_and_inventory():
    product = {
        "@type": "Product",
        "name": "Synthetic Pack",
        "gtin12": "036000291452",
        "sku": "item1",
        "additionalProperty": {"name": "aisle", "value": "7"},
        "image": "https://retailer.test/image.jpg",
        "offers": {
            "@type": "Offer",
            "price": "3.4900",
            "priceCurrency": "USD",
            "priceValidUntil": "2026-10-19",
            "availableAtOrFrom": {"@id": "#north"},
            "availability": "https://schema.org/InStock",
        },
    }
    evidence = collect_evidence(page(store(), product), target(), retrieved_at=123)
    assert evidence["branch_match"] == "exact_address"
    assert evidence["store_candidates"][0]["fields"]["specialOpeningHoursSpecification"]
    placement = evidence["item_placement_candidates"][0]
    assert placement["gtin"] == "00036000291452" and placement["sku"] == "item1"
    assert placement["placement_properties"] == [{"name": "aisle", "value": "7"}]
    assert placement["status"] == "unverified"
    assert evidence["capture_policy"]["product_inventory"] is False
    assert evidence["capture_policy"]["product_catalog"] is False
    encoded = json.dumps(evidence)
    assert '"offers"' not in encoded and "3.4900" not in encoded and "InStock" not in encoded
    assert evidence["acceptance_status"] == "review_required" and evidence["timezone"] is None
    assert evidence["interior_map_candidates"][0]["source_url"].endswith("north.pdf")
    assert evidence["geographic_map_links"] == ["https://maps.test/geographic"]
    assert not evidence["rights"]["media_storage_permitted"]
    assert evidence["html_sha256"] and evidence["retrieved_at"] == 123
    assert evidence["layout_evidence"][0]["value"]["name"] == "Aisle 7"
    assert evidence["layout_evidence"][0]["route_geometry_validated"] is False


def test_name_only_branch_and_nonplacement_products_are_not_captured():
    branch = store()
    branch["address"]["streetAddress"] = "20 Different Street"
    product = {
        "@type": "Product",
        "gtin": "invalid",
        "offers": [
            {"price": "0", "priceCurrency": "USD"},
            {"price": "NaN", "priceCurrency": "USD"},
        ],
    }
    evidence = collect_evidence(page(branch, product), target(), retrieved_at=0)
    assert evidence["branch_match"] == "ambiguous_or_missing" and evidence["store_candidates"] == []
    assert evidence["item_placement_candidates"] == []
    assert evidence["inventory_status"] == "unknown"
    assert "products" not in evidence


def test_duplicate_store_nodes_collapse_but_conflicting_nodes_are_held():
    assert (
        collect_evidence(page(store(), store()), target(), retrieved_at=0)["branch_match"]
        == "exact_address"
    )
    assert (
        collect_evidence(
            '<script type="application/ld+json">invalid</script>', target(), retrieved_at=0
        )["item_placement_candidates"]
        == []
    )


def test_full_source_address_matches_without_fuzzy_name_or_geocoding():
    t = target()
    t["source_address"] = {"full": "10 Imaginary St, Synthetic, IA 50000", "region": "IA"}
    assert collect_evidence(page(store()), t, retrieved_at=0)["branch_match"] == "exact_address"
    conflicting = {**store(), "telephone": "different"}
    assert (
        collect_evidence(page(store(), conflicting), t, retrieved_at=0)["branch_match"]
        == "ambiguous_or_missing"
    )
