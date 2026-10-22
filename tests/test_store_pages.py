import json

from bord_food_api.crawl_evidence import collect_evidence
from bord_food_api.store_pages import weekly

TARGET = {
    "store_id": "sto_test",
    "name": "Imaginary Grocery",
    "url": "https://fixture.test/stores/one",
    "source_address": {
        "street": "10 Main St",
        "city": "Ames",
        "region": "IA",
        "postal_code": "50010",
    },
    "expected_branch": "Imaginary Grocery",
}


def test_visible_branch_contacts_hours_and_service_links_exclude_corporate_footer():
    html = """<nav><a href="/delivery">Delivery</a></nav><main><h1>Imaginary Grocery</h1><p>10 Main Street, Ames IA 50010</p><a href="tel:5155551234">Store phone</a><a href="mailto:branch@fixture.test">Email</a><p>Monday - Saturday 8:00 AM - 9:00 PM</p><p>Sunday Closed</p><a href="/stores/one/pickup">Curbside pickup</a></main><footer><a href="tel:8005559999">Corporate</a><a href="mailto:corp@fixture.test">Email</a></footer>"""
    result = collect_evidence(html, TARGET, retrieved_at=1792518000)
    assert result["branch_match"] == "exact_address"
    valid = {
        r["field"]: r["value"]
        for r in result["field_assertions"]
        if r["branch_match"] == "exact_address" and r["validation"] == "valid"
    }
    assert valid["phone"] == "+15155551234"
    assert valid["email"] == "branch@fixture.test"
    assert len(valid["opening_hours"]) == 7
    assert valid["pickup_links"] == ["https://fixture.test/stores/one/pickup"]
    assert "delivery_links" not in valid
    assert any(
        r["scope"] == "page_contact" and r["branch_match"] == "unresolved"
        for r in result["field_assertions"]
    )
    wrong = html.replace("10 Main Street", "20 Main Street")
    assert collect_evidence(wrong, TARGET, retrieved_at=0)["branch_match"] == "ambiguous_or_missing"


def test_json_hydration_is_bounded_and_does_not_evaluate_javascript_or_products():
    entity = {
        "name": "Imaginary Grocery",
        "address": {
            "line1": "10 Main Street",
            "city": "Ames",
            "region": "IA",
            "postalCode": "50010",
        },
        "mainPhone": "5155551234",
        "hours": {"monday": {"openIntervals": [{"start": "08:00", "end": "21:00"}]}},
    }
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"entity": entity}})
        + "</script>"
    )
    result = collect_evidence(html, TARGET, retrieved_at=0)
    assert result["branch_match"] == "exact_address"
    assert {r["field"] for r in result["field_assertions"]} >= {"phone", "opening_hours"}
    entity["productId"] = "inventory"
    html = '<script type="application/json">' + json.dumps(entity) + "</script>"
    assert collect_evidence(html, TARGET, retrieved_at=0)["branch_match"] == "ambiguous_or_missing"
    assert (
        collect_evidence(
            "<script>window.state = " + json.dumps(entity) + "</script>", TARGET, retrieved_at=0
        )["branch_match"]
        == "ambiguous_or_missing"
    )


def test_ambiguous_or_department_hours_remain_unparsed():
    assert weekly("Monday 8 AM - 9 PM Monday 9 AM - 8 PM") == []
    assert weekly("Monday 8 - 9") == []
    html = '<main>10 Main St Ames IA 50010 Pharmacy Monday 8 AM - 9 PM <a href="tel:5155551234">Phone</a><a href="tel:5155559876">Pharmacy</a></main>'
    result = collect_evidence(html, TARGET, retrieved_at=0)
    assert not any(
        r["field"] in {"phone", "opening_hours"} and r["branch_match"] == "exact_address"
        for r in result["field_assertions"]
    )


def test_yext_literal_preserves_store_hours_departments_and_dated_exceptions():
    entity = {
        "address": {
            "line1": "10 Main Street",
            "city": "Ames",
            "region": "IA",
            "postalCode": "50010",
        },
        "mainPhone": {"number": "+15155551234"},
        "c_pagesDepartments": ["Bakery", "Produce"],
        "hours": {
            "normalHours": [{"day": "MONDAY", "intervals": [{"start": 600, "end": 0}]}],
            "holidayHours": [
                {"date": "2026-12-25", "isClosed": True},
                {"date": "Christmas", "isClosed": True},
            ],
        },
        "appleActionLinks": [
            {"category": "Pickup (Retail)", "quickLinkUrl": "https://fixture.test/pickup?storeId=1"}
        ],
    }
    html = (
        "<script>window.Yext = (function(Yext){Yext.Profile = "
        + json.dumps(entity)
        + "; return Yext;})(window.Yext || {});</script>"
    )
    result = collect_evidence(html, TARGET, retrieved_at=1792518000)
    fields = {
        r["field"]: r["value"] for r in result["field_assertions"] if r["validation"] == "valid"
    }
    assert result["branch_match"] == "exact_address"
    assert fields["phone"] == "+15155551234"
    assert (
        fields["opening_hours"][0]["opens"] == "06:00"
        and fields["opening_hours"][0]["closes"] == "00:00"
    )
    assert fields["departments"] == [{"name": "Bakery"}, {"name": "Produce"}]
    assert len(fields["hours_exceptions"]) == 1
    assert fields["pickup_links"] == ["https://fixture.test/pickup?storeId=1"]


def test_encoded_telephone_and_visible_sibling_hours():
    html = '<article><div class="store-info">10 Main Street Ames IA 50010</div><div class="store-hours">Mon - Sat 8:57 am-8:36 pm Sun 8:57 am-7:36 pm</div><div class="store-phone"><a href="tel:%28515%29555-1234">Phone</a></div></article>'
    result = collect_evidence(html, TARGET, retrieved_at=1792518000)
    fields = {
        r["field"]: r["value"]
        for r in result["field_assertions"]
        if r["validation"] == "valid" and r["branch_match"] == "exact_address"
    }
    assert fields["phone"] == "+15155551234" and len(fields["opening_hours"]) == 7


def test_visible_address_without_explicit_state_or_zip_is_not_bound():
    html = '<main>10 Main St Ames Monday 8 AM - 9 PM <a href="tel:5155551234">Phone</a></main>'
    assert collect_evidence(html, TARGET, retrieved_at=0)["branch_match"] == "ambiguous_or_missing"
    html = (
        '<div class="contact-info">Open Daily 8am-8pm | 10 Main St, Ames, IA | 515-555-1234</div>'
    )
    result = collect_evidence(html, TARGET, retrieved_at=0)
    assert result["branch_match"] == "exact_address"
    assert any(
        r["field"] == "phone" and r["validation"] == "valid" for r in result["field_assertions"]
    )


def test_explicit_department_hours_table_does_not_change_grocery_hours_or_create_aisles():
    node = {
        "@type": "GroceryStore",
        "name": "Imaginary Grocery",
        "address": {"streetAddress": "10 Main Street", "postalCode": "50010"},
        "openingHours": "Mo-Su 08:00-22:00",
    }
    html = (
        '<h1>Imaginary Grocery Ames</h1><script type="application/ld+json">'
        + json.dumps(node)
        + "</script><table><thead><tr><td>Department Hours</td></tr></thead><tbody><tr><td>Pharmacy:</td><td>Monday-Friday 9 AM-6 PM</td></tr><tr><td>Online Groceries:</td><td>Pickup: 8 a.m. to 8 p.m.</td></tr></tbody></table>"
    )
    result = collect_evidence(html, TARGET, retrieved_at=0)
    fields = {
        r["field"]: r["value"]
        for r in result["field_assertions"]
        if r["validation"] == "valid" and r["branch_match"] == "exact_address"
    }
    assert fields["departments"][0]["name"] == "Pharmacy"
    assert fields["departments"][1]["hours_raw"] == "Pickup: 8 a.m. to 8 p.m."
    assert fields["opening_hours"][0]["closes"] == "22:00"
    assert "aisle_category_mappings" not in fields and "pickup_links" not in fields
    assert result["layout_evidence"][-1]["route_geometry_validated"] is False


def test_independent_contact_panel_is_bound_but_footer_panels_never_become_branch_fields():
    from bord_food_api.crawl_evidence import _branch_match
    from bord_food_api.store_pages import Page, branch_html

    target = {
        "name": "Fixture Grocery",
        "url": "https://fixture.test/",
        "single_store_site": True,
        "source_address": {
            "street": "123 Main St",
            "city": "Ames",
            "region": "IA",
            "postal_code": "50010",
        },
    }
    fragment = '<div class="contact-us">123 Main St, Ames IA 50010 <a href="tel:5155551234">Store phone</a> Monday-Sunday 8am-9pm</div>'
    p = Page()
    p.feed(fragment)
    node, _, _ = branch_html(p, target, _branch_match)
    assert node["telephone"] == "tel:5155551234" and node["openingHoursSpecification"]
    p = Page()
    p.feed("<footer>" + fragment + "</footer>")
    assert branch_html(p, target, _branch_match)[0] is None
