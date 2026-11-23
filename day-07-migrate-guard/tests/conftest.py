"""테스트 도우미 — 예제 파일 경로와 마이그레이션 빌더."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrate_guard.operations import Migration, analyze

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
SCHEMA = EXAMPLES / "schema.sql"
RISKY = EXAMPLES / "0012_add_email_verified.up.sql"
FIXED = EXAMPLES / "0012_add_email_verified.fixed.up.sql"
STATS = EXAMPLES / "stats.json"


def rows() -> dict[str, int]:
    return json.loads(STATS.read_text(encoding="utf-8"))["tables"]


def baseline_sql() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def migration(sql: str, *, baseline: str | None = None, rows_map: dict[str, int] | None = None,
              pg_version: int = 16, label: str = "") -> Migration:
    from migrate_guard.schema import parse_schema

    return analyze(
        sql,
        baseline=parse_schema(baseline if baseline is not None else baseline_sql()),
        rows=rows_map if rows_map is not None else {},
        pg_version=pg_version,
        label=label,
    )


@pytest.fixture()
def baseline() -> str:
    return baseline_sql()


@pytest.fixture()
def risky() -> Migration:
    from migrate_guard.loader import build

    return build(str(RISKY), baseline=str(SCHEMA), rows=str(STATS))


@pytest.fixture()
def fixed() -> Migration:
    from migrate_guard.loader import build

    return build(str(FIXED), baseline=str(SCHEMA), rows=str(STATS))
