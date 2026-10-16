import io
from zipfile import ZipFile

import pytest

from bord_food_api import download


def test_latest_release_discovery_and_host_restriction():
    html = """
    <a href="/fdc-datasets/FoodData_Central_branded_food_json_2025-04-24.zip">old</a>
    <a href="/fdc-datasets/FoodData_Central_branded_food_json_2026-04-30.zip">new</a>
    <a href="https://evil.example/FoodData_Central_branded_food_json_2099-04-30.zip">ignore</a>
    <a href="/fdc-datasets/FoodData_Central_survey_food_json_2024-10-31.zip">survey</a>
    <a href="/fdc-datasets/FoodData_Central_foundation_food_csv_2026-04-30.zip">csv</a>
    """
    releases = download.discover(html)
    assert releases["branded"].endswith("2026-04-30.zip")
    assert "fndds" in releases
    assert "foundation" not in releases


def test_download_atomic_cache_checksum_and_incomplete_response(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("foods.json", '{"BrandedFoods": []}')
    archive_bytes = buffer.getvalue()
    calls = []
    bad_length = False

    def fake_open(url):
        calls.append(url)
        if url == download.PAGE:
            data = b'<a href="/fdc-datasets/FoodData_Central_branded_food_json_2026-04-30.zip">JSON</a>'
        else:
            data = archive_bytes
        response = io.BytesIO(data)
        response.headers = {"Content-Length": str(len(data) + int(bad_length))}
        return response

    monkeypatch.setattr(download, "open_url", fake_open)
    paths = download.download_datasets(("branded",), tmp_path)
    assert paths[0].read_bytes() == archive_bytes
    assert download.download_datasets(("branded",), tmp_path) == paths
    assert len(calls) == 3  # Page + ZIP, then page + verified local cache.
    paths[0].write_bytes(b"corrupt")
    download.download_datasets(("branded",), tmp_path)
    assert paths[0].read_bytes() == archive_bytes
    bad_length = True
    with pytest.raises(ValueError, match="Incomplete"):
        download.download_datasets(("branded",), tmp_path, force=True)
    assert paths[0].read_bytes() == archive_bytes
    assert not list(tmp_path.glob("*.part"))
