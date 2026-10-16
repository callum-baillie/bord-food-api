import json
import sys

import pytest

from bord_food_api.__main__ import main


def test_first_start_local_files_and_restart_without_sources(tmp_path, foods, monkeypatch):
    imports = tmp_path / "imports"
    imports.mkdir()
    fixture = imports / "foods.json"
    fixture.write_text(json.dumps(foods))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPORT_DIR", str(imports))
    monkeypatch.setenv("AUTO_DOWNLOAD", "false")
    monkeypatch.setattr(sys, "argv", ["bord_food_api", "serve"])
    served = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: served.append(True))
    main()
    fixture.unlink()
    main()
    assert len(served) == 2


def test_download_disabled_fails_without_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPORT_DIR", str(tmp_path / "imports"))
    monkeypatch.setenv("AUTO_DOWNLOAD", "false")
    monkeypatch.setattr(sys, "argv", ["bord_food_api", "serve"])
    with pytest.raises(ValueError, match="No source files"):
        main()
    assert not (tmp_path / "data" / "foods.sqlite").exists()
