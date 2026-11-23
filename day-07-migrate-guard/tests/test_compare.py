"""두 마이그레이션 비교 — 좋아졌는지 숫자로."""

from __future__ import annotations

import pytest

from conftest import migration
from migrate_guard.compare import compare
from migrate_guard.dialect import Severity

SCHEMA = """
CREATE TABLE users (
    id bigint PRIMARY KEY,
    phone varchar(32)
);
"""
BIG = {"users": 1_000_000}


def pair(before_sql: str, after_sql: str):
    return compare(
        migration(before_sql, baseline=SCHEMA, rows_map=BIG),
        migration(after_sql, baseline=SCHEMA, rows_map=BIG),
    )


def test_improvement_lowers_critical() -> None:
    result = pair("DROP TABLE users;", "ALTER TABLE users ADD COLUMN a int;")
    assert result.before_counts[Severity.치명] == 1
    assert result.after_counts[Severity.치명] == 0


def test_improved_rules_listed() -> None:
    result = pair("CREATE INDEX idx ON users (phone);", "CREATE INDEX CONCURRENTLY idx ON users (phone);")
    assert "create-index-blocks-writes" in result.improved_rules()


def test_new_rules_listed() -> None:
    result = pair("SELECT 1;", "DROP TABLE users;")
    assert "drop-table" in result.new_rules()


def test_hold_seconds_shown() -> None:
    result = pair("CREATE INDEX idx ON users (phone);", "CREATE INDEX CONCURRENTLY idx ON users (phone);")
    text = result.render()
    assert "락 유지" in text


def test_transaction_note_when_split() -> None:
    result = pair(
        "BEGIN; ALTER TABLE users ADD COLUMN a int; ALTER TABLE users ADD COLUMN b int; COMMIT;",
        "ALTER TABLE users ADD COLUMN a int; ALTER TABLE users ADD COLUMN b int;",
    )
    assert "트랜잭션 묶음" in result.render()


def test_identical_files_report_same() -> None:
    result = pair("ALTER TABLE users ADD COLUMN a int;", "ALTER TABLE users ADD COLUMN a int;")
    assert result.improved_rules() == []
    assert result.new_rules() == []


def test_worst_lock_comparison() -> None:
    result = pair("CREATE INDEX idx ON users (phone);", "SELECT 1;")
    text = result.render()
    assert "이후: 읽기·쓰기를 막는 문장 없음" in text


def test_render_truncates_rules() -> None:
    result = pair("DROP TABLE users; CREATE INDEX i ON users (phone);", "SELECT 1;")
    assert result.render(max_items=1).count("- ") >= 1
