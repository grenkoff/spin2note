"""Central logging: context binding + JSON/text formatting + configuration."""

from __future__ import annotations

import json
import logging

from spin2note_api.config import Settings
from spin2note_api.logging_config import (
    _JsonFormatter,
    _TextFormatter,
    bind_log_context,
    configure_logging,
    reset_log_context,
)


def _record(msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("spin2note.test", logging.INFO, __file__, 1, msg, None, None)


def test_json_formatter_includes_bound_context() -> None:
    reset_log_context()
    bind_log_context(request_id="r1", user_id="u1")
    rec = _record("ingested")

    # The context filter normally sets these; emulate it for the record.
    from spin2note_api.logging_config import _ContextFilter

    _ContextFilter().filter(rec)
    out = json.loads(_JsonFormatter().format(rec))
    assert out["msg"] == "ingested"
    assert out["level"] == "INFO"
    assert out["request_id"] == "r1"
    assert out["user_id"] == "u1"
    assert "session_id" not in out  # unset keys are omitted
    reset_log_context()


def test_text_formatter_appends_present_context() -> None:
    reset_log_context()
    bind_log_context(object_key="2026/x.txt")
    rec = _record("parsed")
    from spin2note_api.logging_config import _ContextFilter

    _ContextFilter().filter(rec)
    line = _TextFormatter().format(rec)
    assert "parsed" in line
    assert "object_key=2026/x.txt" in line
    reset_log_context()


def test_configure_logging_sets_level_and_json_outside_dev() -> None:
    configure_logging(Settings(environment="production", log_level="WARNING"))
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert isinstance(root.handlers[0].formatter, _JsonFormatter)
    # restore a sane dev config for the rest of the suite
    configure_logging(Settings(environment="development", log_level="INFO"))
    assert isinstance(logging.getLogger().handlers[0].formatter, _TextFormatter)
