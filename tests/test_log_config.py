import io
import json
import logging

import pytest

from bord_food_api import log_config


@pytest.fixture(autouse=True)
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:], _ = handlers, root.setLevel(level)
    log_config._role = None
    access = logging.getLogger("uvicorn.access")
    access.filters[:] = []
    access.setLevel(logging.NOTSET)


def capture(monkeypatch, level="info", fmt="json", role=None):
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(log_config.sys, "stdout", out)
    monkeypatch.setattr(log_config.sys, "stderr", err)
    monkeypatch.setenv("LOG_LEVEL", level)
    monkeypatch.setenv("LOG_FORMAT", fmt)
    log_config.configure_logging(role=role)
    return out, err


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_level_names_fall_back_to_info():
    assert log_config.resolve_level(None) == logging.INFO
    assert log_config.resolve_level("nonsense") == logging.INFO
    assert log_config.resolve_level(" WARNING ") == logging.WARNING
    assert log_config.resolve_format("TEXT") == "text"
    assert log_config.resolve_format(None) == "json"


def test_levels_filter_and_split_streams(monkeypatch):
    out, err = capture(monkeypatch, level="info", role="worker")
    log = logging.getLogger("bord_food_api.test")
    log.debug("hidden")
    log.info("shown")
    log.warning("careful")
    log.error("broken")
    assert [line["msg"] for line in lines(out)] == ["shown"]
    assert [line["level"] for line in lines(err)] == ["warn", "error"]
    first = lines(out)[0]
    assert first["service"] == "bord-food-api"
    assert first["component"] == "bord_food_api.test"
    assert first["role"] == "worker"


def test_debug_and_silent(monkeypatch):
    out, _ = capture(monkeypatch, level="debug")
    logging.getLogger("x").debug("visible")
    assert lines(out)[0]["level"] == "debug"
    out, err = capture(monkeypatch, level="silent")
    logging.getLogger("x").error("nothing")
    assert out.getvalue() == err.getvalue() == ""


def test_credentials_are_redacted(monkeypatch):
    out, err = capture(monkeypatch)
    logging.getLogger("x").info(
        "fetch https://h/x?api_key=abc123&q=1", extra={"api_key": "abc123", "ok": 1}
    )
    try:
        raise ValueError("bad token=zzz999")
    except ValueError:
        logging.getLogger("x").exception("failed")
    text = out.getvalue() + err.getvalue()
    assert "abc123" not in text and "zzz999" not in text
    first = lines(out)[0]
    assert first["api_key"] == "[redacted]" and first["ok"] == 1
    assert lines(err)[0]["error"]["type"] == "ValueError"


def test_access_records_are_judged_by_outcome(monkeypatch):
    out, err = capture(monkeypatch, level="info")
    access = logging.getLogger("uvicorn.access")
    fmt = '%s - "%s %s HTTP/%s" %d'
    access.info(fmt, "1.2.3.4:5", "GET", "/live", "1.1", 200)
    access.info(fmt, "1.2.3.4:5", "GET", "/fdc/v1/foods?api_key=s3cret", "1.1", 401)
    access.info(fmt, "1.2.3.4:5", "GET", "/boom", "1.1", 500)
    assert out.getvalue() == ""
    levels = [(line["level"], line["path"], line["status"]) for line in lines(err)]
    assert levels == [("warn", "/fdc/v1/foods", 401), ("error", "/boom", 500)]
    assert "s3cret" not in err.getvalue()
    out, _ = capture(monkeypatch, level="debug")
    logging.getLogger("uvicorn.access").info(fmt, "1.2.3.4:5", "GET", "/live", "1.1", 200)
    assert lines(out)[0]["level"] == "debug"


def test_text_format_is_one_line(monkeypatch):
    out, _ = capture(monkeypatch, fmt="text")
    logging.getLogger("x").info("hello", extra={"a": 1})
    assert out.getvalue().strip().endswith('INFO  [x] hello {"a": 1}')
