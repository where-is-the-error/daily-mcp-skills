"""SQLite 저장소 — 페이지 스냅샷 + 기억(그래프) 한 파일.

Memory MCP는 그래프를 JSONL 한 파일에 통째로 쓴다. 여기서는 두 종류의 기억
(페이지 스냅샷 · 엔티티/관찰/관계)을 같은 SQLite 파일에 넣어, 한 트랜잭션 안에서
"페이지를 읽고 그 사실을 기억에 남기는" 일이 원자적으로 끝나게 했다.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

__all__ = ["DEFAULT_DB_ENV", "default_db_path", "connect", "SCHEMA"]

DEFAULT_DB_ENV = "WEB_MEMO_DB"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pages (
    url         TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    checks      INTEGER NOT NULL DEFAULT 1,
    changes     INTEGER NOT NULL DEFAULT 0,
    last_hash   TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT NOT NULL REFERENCES pages(url) ON DELETE CASCADE,
    fetched_at   TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    chars        INTEGER NOT NULL,
    tokens       INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_url ON snapshots(url, id DESC);

CREATE TABLE IF NOT EXISTS entities (
    name    TEXT PRIMARY KEY,
    type    TEXT NOT NULL DEFAULT 'page',
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    entity  TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    source  TEXT,
    created TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_entity ON observations(entity, id);

CREATE TABLE IF NOT EXISTS relations (
    src     TEXT NOT NULL,
    dst     TEXT NOT NULL,
    kind    TEXT NOT NULL,
    created TEXT NOT NULL,
    PRIMARY KEY (src, dst, kind)
);
"""


def default_db_path() -> Path:
    """`$WEB_MEMO_DB` 또는 `~/.local/share/web-memo/memo.db`."""
    override = os.environ.get(DEFAULT_DB_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "web-memo" / "memo.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """스키마를 보장한 연결을 만든다. `:memory:`도 받는다."""
    raw = default_db_path() if path is None else path
    if str(raw) == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        target = Path(raw).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
