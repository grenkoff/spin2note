"""SQL statement splitting for the ClickHouse migration runner.

Regression for the bug where a ';' inside a `--` comment split a statement and comment-only
chunks were sent to ClickHouse as empty queries.
"""

from __future__ import annotations

from spin2note_api.clickhouse.migrate import _statements


def test_splits_plain_statements() -> None:
    assert _statements("CREATE TABLE a (x Int8); CREATE TABLE b (y Int8)") == [
        "CREATE TABLE a (x Int8)",
        "CREATE TABLE b (y Int8)",
    ]


def test_strips_line_comments_and_ignores_semicolons_inside_them() -> None:
    sql = """
    -- statements are separated by ';' (this ; must NOT split anything)
    CREATE TABLE a (x Int8);
    -- a standalone comment line
    CREATE TABLE b (y Int8);
    """
    assert _statements(sql) == ["CREATE TABLE a (x Int8)", "CREATE TABLE b (y Int8)"]


def test_comment_only_input_yields_no_statements() -> None:
    assert _statements("-- just a comment\n-- another;one\n") == []


def test_trailing_semicolon_and_blank_lines_are_dropped() -> None:
    assert _statements("TRUNCATE TABLE t;\n\n   \n") == ["TRUNCATE TABLE t"]
