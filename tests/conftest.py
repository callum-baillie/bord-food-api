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


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    """All routine tests deny real provider DNS and sockets, independent of HTTP library."""
    import ipaddress
    import socket

    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def allowed(host):
        if host in ("localhost", b"localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def resolve(host, *args, **kwargs):
        if not allowed(host):
            raise AssertionError("External DNS disabled in routine tests")
        return original_resolve(host, *args, **kwargs)

    def connect(sock, address):
        if isinstance(address, tuple) and not allowed(address[0]):
            raise AssertionError("External network disabled in routine tests")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if isinstance(address, tuple) and not allowed(address[0]):
            raise AssertionError("External network disabled in routine tests")
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
