"""Wrapper over the Rust ``hh_parser`` PyO3 extension.

The Rust crate (``crates/hh-parser``) does the CPU-bound text parsing of millions of hands.
This wrapper imports it lazily so the API and tests still run when the extension hasn't been
built yet (``maturin develop``), and normalises its raw dict output into domain models.
"""

from __future__ import annotations

from typing import Any


class ParserUnavailable(RuntimeError):
    """Raised when the compiled ``hh_parser`` extension is not importable."""


def _hh_parser() -> Any:
    try:
        import hh_parser
    except ImportError as exc:  # pragma: no cover - depends on build state
        raise ParserUnavailable(
            "hh_parser extension not built. Run `maturin develop` in crates/hh-parser."
        ) from exc
    return hh_parser


def detect_format(raw: str) -> str:
    """Return '3max' or '6max' for a raw hand-history blob."""
    return str(_hh_parser().detect_format(raw))


def parse(raw: str) -> list[dict[str, Any]]:
    """Parse a raw hand-history blob into a list of structured hand dicts."""
    return list(_hh_parser().parse(raw))
