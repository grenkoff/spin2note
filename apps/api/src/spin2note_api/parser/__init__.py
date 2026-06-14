"""Hand-history parsing: Rust ``hh_parser`` wrapper + domain mapping."""

from .mapping import build_hand, build_hands, build_tournament, deterministic_hand_id
from .wrapper import ParserUnavailable, detect_format, parse, parse_summaries, parse_summary

__all__ = [
    "parse",
    "parse_summary",
    "parse_summaries",
    "detect_format",
    "ParserUnavailable",
    "build_hand",
    "build_hands",
    "build_tournament",
    "deterministic_hand_id",
]
