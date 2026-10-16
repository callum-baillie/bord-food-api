from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.settings import Settings


def test_search_filter_pagination_and_detail_contract(client):
    first = client.post("/fdc/v1/foods/search", json={"query": "oats", "pageSize": 2}).json()
    second = client.get(
        "/fdc/v1/foods/search", params={"query": "oats", "pageSize": 2, "pageNumber": 2}
    ).json()
    assert first["totalHits"] == 5
    assert first["totalPages"] == 3
    assert {x["fdcId"] for x in first["foods"]}.isdisjoint(x["fdcId"] for x in second["foods"])
    generic = client.post(
        "/fdc/v1/foods/search", json={"query": "oats", "dataType": ["Foundation", "Survey (FNDDS)"]}
    ).json()
    assert {x["fdcId"] for x in generic["foods"]} == {201, 301}
    branded = client.post(
        "/fdc/v1/foods/search", json={"query": "rolled oats", "dataType": ["Branded"]}
    ).json()
    item = next(x for x in branded["foods"] if x["fdcId"] == 101)
    assert item["foodNutrients"][0] == {
        "nutrientId": 1003,
        "nutrientName": "Protein",
        "unitName": "g",
        "value": 12.5,
    }
    assert item["foodNutrients"][1]["value"] == 0
    assert item["foodNutrients"][2]["value"] is None
    assert "value" not in item["foodNutrients"][3]
    detail = client.get("/fdc/v1/food/101").json()
    assert detail["foodCategory"] == "Cereals"
    assert detail["foodNutrients"][0]["amount"] == 12.5
    assert detail["foodNutrients"][0]["nutrient"]["id"] == 1003
    assert client.get("/fdc/v1/food/999").status_code == 404


@pytest.mark.parametrize("gtin", ["012345678905", "0012345678905", "00012345678905", "12345678905"])
def test_barcode_exact_match_leading_zeroes_and_newest_first(client, gtin):
    result = client.post(
        "/fdc/v1/foods/search", json={"query": gtin, "dataType": ["Branded"]}
    ).json()
    assert [item["fdcId"] for item in result["foods"]] == [102, 101]
    assert "brandOwner" not in result["foods"][0]
    assert "servingSize" not in result["foods"][0]


def test_prefix_brand_punctuation_and_no_match(client):
    assert (
        client.get("/fdc/v1/foods/search", params={"query": "exam roll"}).json()["totalHits"] == 1
    )
    for query in ['" OR *', "---", "zqxnofood"]:
        result = client.post("/fdc/v1/foods/search", json={"query": query})
        assert result.status_code == 200
        assert result.json()["totalHits"] == 0
    assert (
        client.post("/fdc/v1/foods/search", json={"query": "012345678906"}).json()["totalHits"] == 0
    )


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 201},
        {"query": "a " * 21},
        {"query": "oats", "pageSize": 0},
        {"query": "oats", "pageSize": 201},
        {"query": "oats", "pageNumber": -1},
        {"query": "oats", "pageNumber": True},
        {"query": "oats", "dataType": ["bad"]},
        {"query": "oats", "unexpected": True},
    ],
)
def test_invalid_http_input(client, body):
    assert client.post("/fdc/v1/foods/search", json=body).status_code == 422


def test_invalid_ids_large_body_and_empty_catalog(client, tmp_path):
    for value in ["0", "-1", "abc", str(2**64)]:
        assert client.get("/fdc/v1/food/" + value).status_code == 422
    assert client.post("/fdc/v1/foods/search", content="x" * 20000).status_code == 413
    assert client.get("/fdc/v1/foods/search", params={"query": "   "}).status_code == 422
    with TestClient(create_app(Settings(data_dir=tmp_path / "empty", api_key=""))) as empty:
        assert empty.get("/health").status_code == 503


def test_optional_key_protects_foods_and_status(settings):
    with TestClient(create_app(replace(settings, api_key="local-test-key"))) as client:
        assert client.get("/health").status_code == 200
        for headers in ({}, {"X-Api-Key": "wrong"}):
            assert client.get("/fdc/v1/food/101", headers=headers).status_code == 401
            assert client.get("/status", headers=headers).status_code == 401
        assert (
            client.get("/fdc/v1/food/101", headers={"X-Api-Key": "local-test-key"}).status_code
            == 200
        )
        status = client.get("/status", headers={"X-Api-Key": "local-test-key"}).json()
        assert "local-test-key" not in str(status)
        assert status["totalFoods"] == 6
        assert status["sources"][0]["sha256"]


def test_health_and_openapi(client):
    assert client.get("/health").json() == {"status": "ok", "totalFoods": 6}
    assert "/fdc/v1/foods/search" in client.get("/openapi.json").json()["paths"]


def test_concurrent_requests_have_independent_database_connections(client):
    def lookup(_):
        response = client.post("/fdc/v1/foods/search", json={"query": "oats"})
        return response.status_code, response.json().get("totalHits")

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(lookup, range(24))) == [(200, 5)] * 24
