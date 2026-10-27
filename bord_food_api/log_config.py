"""Structured logging shared by the API, the worker and the supervisor.

One JSON line per event: debug and info on stdout, warning and error on stderr, so
``docker logs`` and Dozzle read the same stream and can filter on ``level``.

    LOG_LEVEL   debug | info | warning | error | silent   (default info)
    LOG_FORMAT  json | text                               (default json)

Credentials never belong in a message; values under sensitive keys and ``key=value`` pairs
that look like credentials are redacted as a second line of defence.
"""

import json
import logging
import os
import re
import sys
import traceback
from datetime import UTC, datetime

SERVICE = "bord-food-api"
_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "silent": logging.CRITICAL + 10,
}
_SENSITIVE_KEY = re.compile(
    r"secret|token|password|authorization|cookie|api[_-]?key|credential", re.IGNORECASE
)
_SENSITIVE_PAIR = re.compile(
    r"((?:api[_-]?key|token|secret|password|authorization)\s*[=:]\s*)(?:bearer\s+)?[^\s&\"',;]+",
    re.IGNORECASE,
)
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}
_MAX_TEXT = 2000


def resolve_level(value: str | None) -> int:
    return _LEVELS.get((value or "").strip().lower(), logging.INFO)


def resolve_format(value: str | None) -> str:
    return "text" if (value or "").strip().lower() == "text" else "json"


def _redact_text(text: str) -> str:
    text = _SENSITIVE_PAIR.sub(r"\1[redacted]", text)
    return text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT] + "…"


def _safe(value, depth: int = 0):
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _SENSITIVE_KEY.search(str(key)) else _safe(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth + 1) for item in list(value)[:20]]
    return _redact_text(str(value))


class _Formatter(logging.Formatter):
    def __init__(self, fmt: str):
        super().__init__()
        self.fmt = fmt

    def format(self, record: logging.LogRecord) -> str:
        fields = {
            key: _safe({key: value})[key]
            for key, value in record.__dict__.items()
            if key not in _STANDARD and not key.startswith("_")
        }
        message = _redact_text(record.getMessage())
        if record.exc_info and record.exc_info[0] is not None:
            kind, error, trace = record.exc_info
            fields["error"] = {
                "type": kind.__name__,
                "message": _redact_text(str(error)),
                "stack": _redact_text("".join(traceback.format_tb(trace)[-6:]).strip()),
            }
        time = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        time = time.replace("+00:00", "Z")
        level = record.levelname.lower().replace("warning", "warn")
        if self.fmt == "json":
            return json.dumps(
                {
                    "time": time,
                    "level": level,
                    "service": SERVICE,
                    "component": record.name,
                    "msg": message,
                    **fields,
                },
                default=str,
            )
        detail = f" {json.dumps(fields, default=str)}" if fields else ""
        return f"{time} {level.upper():5} [{record.name}] {message}{detail}"


class _Below(logging.Filter):
    """stdout takes everything under warning; stderr takes the rest."""

    def __init__(self, upper: int | None, lower: int | None):
        super().__init__()
        self.upper, self.lower = upper, lower

    def filter(self, record: logging.LogRecord) -> bool:
        if self.upper is not None and record.levelno >= self.upper:
            return False
        return self.lower is None or record.levelno >= self.lower


class _AccessLevel(logging.Filter):
    """Judge uvicorn access records by outcome: refusals and failures are visible at the
    default level, everything else (including the health probe) only at debug."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            _client, method, target, _version, status = record.args  # type: ignore[misc]
        except (TypeError, ValueError):
            return True
        path = str(target).split("?", 1)[0]
        status = int(status)
        level = (
            logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.DEBUG
        )
        record.levelno, record.levelname = level, logging.getLevelName(level)
        record.msg, record.args = "request", ()
        record.__dict__.update(method=method, path=path, status=status)
        return True


_role: str | None = None
_factory_installed = False


def _install_role_factory() -> None:
    """Stamp the process role on every record; installed once however often we configure."""
    global _factory_installed
    if _factory_installed:
        return
    default_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = default_factory(*args, **kwargs)
        if _role:
            record.role = _role
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(role: str | None = None) -> None:
    """Install the handlers on the root logger and route uvicorn through them."""
    threshold = resolve_level(os.getenv("LOG_LEVEL"))
    formatter = _Formatter(resolve_format(os.getenv("LOG_FORMAT")))
    out = logging.StreamHandler(sys.stdout)
    out.addFilter(_Below(logging.WARNING, None))
    err = logging.StreamHandler(sys.stderr)
    err.addFilter(_Below(None, logging.WARNING))
    handlers = (out, err)
    for handler in handlers:
        handler.setLevel(threshold)
        handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(threshold)
    global _role
    _role = role
    _install_role_factory()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.setLevel(logging.DEBUG)
    access.filters[:] = [_AccessLevel()]
