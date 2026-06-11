"""Thin Python wrapper around the Rust ``hh_parser`` extension."""

from .wrapper import ParserUnavailable, detect_format, parse

__all__ = ["parse", "detect_format", "ParserUnavailable"]
