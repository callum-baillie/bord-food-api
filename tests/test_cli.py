import json
import sys

from bord_food_api.__main__ import main


def invoke(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["bord_food_api", *arguments])
    main()


def test_serve_starts_empty_without_importing_or_network(tmp_path, foods, monkeypatch):
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / "foods.json").write_text(json.dumps(foods))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPORT_DIR", str(imports))
    monkeypatch.setenv("AUTO_DOWNLOAD", "false")
    served = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: served.append(True))
    invoke(monkeypatch, "serve")
    invoke(monkeypatch, "serve")
    assert len(served) == 2
    assert not (tmp_path / "data" / "foods.sqlite").exists()
    assert not (tmp_path / "data" / "current.json").exists()


def test_download_disabled_empty_server_is_live(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPORT_DIR", str(tmp_path / "imports"))
    monkeypatch.setenv("AUTO_DOWNLOAD", "false")
    served = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: served.append(True))
    invoke(monkeypatch, "serve")
    assert served == [True]
    assert not (tmp_path / "data" / "foods.sqlite").exists()


def test_plan_and_status_are_network_free(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "bord_food_api.transport.Transport.get",
        lambda *_: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    invoke(monkeypatch, "sync", "--plan", "--source", "all_the_places")
    result = json.loads(capsys.readouterr().out)
    assert result[0]["would_discover"] is True
    assert result[0]["would_crawl"] is False
    invoke(monkeypatch, "status", "--json")
    assert json.loads(capsys.readouterr().out)


def test_explicit_local_import_preserves_legacy_payload(tmp_path, foods, monkeypatch, capsys):
    from bord_food_api.platform import Platform

    source = tmp_path / "foods.json"
    source.write_text(json.dumps(foods))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    invoke(monkeypatch, "import", str(source))
    assert Platform(tmp_path / "data").legacy_path().exists()
    invoke(monkeypatch, "status")
    outputs = capsys.readouterr().out
    assert "totalFoods" in outputs


def test_rights_cli_restriction_and_config_revocation(tmp_path, monkeypatch, capsys):
    import pytest

    from bord_food_api.control import Control
    from bord_food_api.platform import Platform

    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    platform = Platform(data)
    platform.sync(
        "all_the_places",
        "fixture",
        "r1",
        [{"kind": "store", "source_key": "001", "payload": {"name": "Fixture store"}}],
    )
    assert len(platform.records("store")) == 1
    invoke(monkeypatch, "rights", "restrict", "all_the_places", "--reason", "reviewed removal")
    assert "all_the_places" in Control(data).denied_sources()
    assert platform.records("store") == []
    invoke(monkeypatch, "rights", "allow", "all_the_places", "--reason", "reviewed restoration")
    assert "all_the_places" not in Control(data).denied_sources()
    assert len(platform.records("store")) == 1
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"sources": {"all_the_places": {"can_retain": False}}}))
    monkeypatch.setenv("BORD_FOOD_CONFIG", str(config))
    invoke(monkeypatch, "status", "--json")
    assert "all_the_places" in Control(data).denied_sources()
    assert platform.records("store") == []
    with pytest.raises(ValueError, match="Configuration still denies"):
        invoke(monkeypatch, "rights", "allow", "all_the_places", "--reason", "must fix config")
    invoke(monkeypatch, "rights", "purge", "--quiesced")
    assert platform.records("store") == []
    assert capsys.readouterr().out


def test_crawl_plan_and_disabled_once_never_create_job(tmp_path, monkeypatch, capsys):
    import pytest

    from bord_food_api.control import Control

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    invoke(monkeypatch, "crawl", "--plan", "--adapter", "woodmans_maps")
    result = json.loads(capsys.readouterr().out)
    assert not result["allowed"]
    assert not result["would_crawl"]
    with pytest.raises(ValueError, match="activation gates"):
        invoke(monkeypatch, "crawl", "--once", "--adapter", "woodmans_maps")
    with Control(tmp_path / "data").connect() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
