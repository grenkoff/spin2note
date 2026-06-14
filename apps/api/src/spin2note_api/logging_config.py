"""Central logging setup shared by the API and the worker.

- One `configure_logging()` entrypoint (stdlib only — no extra deps).
- Text format in development, **JSON in any other environment** (Railway/prod aggregation).
- Level from `LOG_LEVEL` (settings).
- A contextvar-backed filter injects correlation fields (request_id, user_id, import_id, …) into
  every record, so a request or import can be traced across the API and the worker.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from .config import Settings

# Correlation fields surfaced in every log line when set on the current task's context.
CONTEXT_KEYS = ("request_id", "user_id", "import_id", "session_id", "object_key")

_log_context: ContextVar[dict[str, Any]] = ContextVar("_log_context", default={})  # noqa: B039

_NOISY_LOGGERS = (
    "clickhouse_connect", "asynch", "urllib3", "minio", "httpcore", "httpx", "aiohttp",
)


def bind_log_context(**fields: Any) -> None:
    """Merge correlation fields into the current context (e.g. per request / per job)."""
    _log_context.set({**_log_context.get(), **fields})


def reset_log_context() -> None:
    _log_context.set({})


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _log_context.get()
        for key in CONTEXT_KEYS:
            setattr(record, key, ctx.get(key))
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = (
            f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} "
            f"{record.name} {record.getMessage()}"
        )
        ctx = " ".join(
            f"{k}={getattr(record, k)}"
            for k in CONTEXT_KEYS
            if getattr(record, k, None) is not None
        )
        if ctx:
            line += f"  [{ctx}]"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(settings: Settings) -> None:
    """Idempotently configure root logging for the current process."""
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        _TextFormatter() if settings.environment == "development" else _JsonFormatter()
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
