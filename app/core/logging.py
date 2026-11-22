"""Application logging setup.

One place configures logging for the whole process, so every module can just
call ``get_logger(__name__)`` and inherit the same level, format and handlers.

**Request correlation.** A ``request_id`` is generated per request and stored
in a :class:`~contextvars.ContextVar`. Because a ContextVar is scoped to the
running task, every log line emitted while handling a request carries that id
automatically — the service and repository layers never have to accept or pass
a correlation id, which would pollute every signature in the codebase.

**Text or JSON.** `LOG_FORMAT=text` (default) is readable in a terminal;
`LOG_FORMAT=json` emits one object per line for a log aggregator.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

from app.core.config import settings

# Empty string rather than None so format strings never render "None".
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")

_HANDLER_NAME = "talentfinder"


class ContextFilter(logging.Filter):
    """Attach the current request id and tenant id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.tenant_id = tenant_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for ingestion by a log aggregator."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "tenant_id": getattr(record, "tenant_id", "-"),
        }
        # Anything passed via logger.info("...", extra={...}) that is not a
        # standard LogRecord attribute becomes a top-level field.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "request_id",
    "tenant_id",
    "message",
    "asctime",
    "taskName",
}

TEXT_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s t=%(tenant_id)s] %(name)s: %(message)s"


def configure_logging() -> None:
    """Configure root and uvicorn loggers. Safe to call more than once.

    This deliberately re-asserts the configuration on every call instead of
    short-circuiting after the first. Other code can and does reconfigure
    logging underneath us — Alembic's ``fileConfig`` resets the root level and
    can disable existing loggers — so a one-shot guard would leave the app
    silently mis-configured. Re-running is cheap, and the named-handler check
    below keeps it from stacking duplicate handlers.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(ContextFilter())
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT, datefmt="%H:%M:%S"))

    root = logging.getLogger()
    # Remove only handlers this function installed, never every handler.
    # Clearing the list wholesale would also tear out handlers the host
    # process owns - pytest's capture handler is the one that bit here, and
    # it silently broke every assertion about log output.
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # uvicorn installs its own handlers; clear them so output is not doubled
    # and so uvicorn's lines carry the request id too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True  # let our root handler format them

    # The request middleware already logs method, path, status and duration,
    # so uvicorn's own access log would be a duplicate of every line.
    logging.getLogger("uvicorn.access").disabled = True

    # SQLAlchemy echoes every statement at INFO; that is far too noisy for
    # normal operation. Raise it to WARNING unless explicitly asked for.
    logging.getLogger("sqlalchemy.engine").setLevel("INFO" if settings.log_sql else "WARNING")


def get_logger(name: str) -> logging.Logger:
    """Module-level logger. Use ``get_logger(__name__)``."""
    return logging.getLogger(name)
