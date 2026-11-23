#!/usr/bin/env python3
"""진짜 DB 카탈로그와 스키마 모델을 맞춰 본다 (표준 라이브러리 sqlite3 만 사용).

PostgreSQL DDL 중 SQLite 도 받아들이는 부분집합(표·컬럼·타입 이름·NOT NULL·
PK·UNIQUE·인덱스)을 실제로 SQLite 에 넣고, PRAGMA 가 돌려주는 카탈로그와
migrate-guard 의 `parse_schema` 결과를 컬럼 단위로 비교한다.

    python3 tools/schema_probe.py

네트워크·PostgreSQL 서버 없이 돈다. 맞지 않으면 0 이 아닌 코드로 끝난다.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrate_guard.schema import parse_schema  # noqa: E402

DDL = """
CREATE TABLE users (
    id integer PRIMARY KEY,
    email varchar(255) NOT NULL,
    phone varchar(32),
    name varchar(80),
    created_at text NOT NULL DEFAULT '',
    flag boolean NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    id integer PRIMARY KEY,
    user_id bigint NOT NULL,
    total_cents integer NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'pending',
    note text
);

CREATE TABLE events (
    id integer PRIMARY KEY,
    user_id bigint,
    kind varchar(48) NOT NULL,
    payload text,
    created_at text
);

CREATE TABLE invoices (
    id integer PRIMARY KEY,
    order_id bigint NOT NULL,
    amount_cents integer NOT NULL,
    issued_at date NOT NULL
);

CREATE UNIQUE INDEX invoices_order_id_key ON invoices (order_id);
CREATE INDEX events_kind_idx ON events (kind);
"""


def sqlite_catalog(conn: sqlite3.Connection) -> dict[str, dict[str, dict]]:
    tables: dict[str, dict[str, dict]] = {}
    names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    for name in names:
        columns: dict[str, dict] = {}
        for cid, column, ctype, notnull, default, pk in conn.execute(f'PRAGMA table_info("{name}")'):
            columns[column.lower()] = {
                "type": (ctype or "").lower(),
                "nullable": not bool(notnull) and not bool(pk),
                "primary_key": bool(pk),
            }
        tables[name.lower()] = columns
    return tables


def main() -> int:
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    catalog = sqlite_catalog(conn)
    model = parse_schema(DDL)

    problems: list[str] = []
    compared = 0
    for table_name, columns in catalog.items():
        table = model.table(table_name)
        if table is None:
            problems.append(f"표를 읽지 못했습니다: {table_name}")
            continue
        for column_name, facts in columns.items():
            column = table.column(column_name)
            if column is None:
                problems.append(f"컬럼을 읽지 못했습니다: {table_name}.{column_name}")
                continue
            compared += 1
            if column.type.strip().lower() != facts["type"]:
                problems.append(f"타입 불일치 {table_name}.{column_name}: 모델 {column.type!r} · DB {facts['type']!r}")
            if column.nullable != facts["nullable"]:
                problems.append(
                    f"NULL 불일치 {table_name}.{column_name}: 모델 {column.nullable} · DB {facts['nullable']}"
                )
            if bool(column.primary_key) != facts["primary_key"]:
                problems.append(
                    f"PK 불일치 {table_name}.{column_name}: 모델 {column.primary_key} · DB {facts['primary_key']}"
                )

    sqlite_indexes = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    }
    model_indexes = set(model.indexes)
    if sqlite_indexes != model_indexes:
        problems.append(f"인덱스 불일치: DB {sorted(sqlite_indexes)} · 모델 {sorted(model_indexes)}")

    print(f"표 {len(catalog)}개 · 컬럼 {compared}개 · 인덱스 {len(sqlite_indexes)}개 비교")
    if problems:
        print(f"불일치 {len(problems)}건")
        for problem in problems:
            print(" -", problem)
        return 1
    print("불일치 0건 — 실제 DB 카탈로그와 모델이 같습니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
