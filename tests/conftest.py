import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.importer import build_catalog
from bord_food_api.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "foods.json"


@pytest.fixture
def foods():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def settings(tmp_path):
    result = Settings(data_dir=tmp_path, api_key="")
    build_catalog([FIXTURE], result.database)
    return result


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as result:
        yield result
