"""SQLite 저장소 — SQLite MCP 에서 가져온 '한 파일 + 스키마 + 읽기/쓰기 분리' 사상.

원본 SQLite MCP 는 `read_query`/`write_query` 로 임의 SQL 을 받는다. 여기서는 그 대신
**정해진 세 테이블**(deadlines · events)만 두고, 쓰기는 함수 하나씩으로 좁혔다.
에이전트가 `DELETE FROM deadlines` 를 칠 수 있는 서버는 마감 도구로 쓰기 어렵기 때문이다.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .zones import UTC

__all__ = [
    "DEFAULT_DB_ENV",
    "SCHEMA",
    "Deadline",
    "AddResult",
    "default_db_path",
    "connect",
    "new_id",
    "add",
    "get",
    "find",
    "list_rows",
    "set_done",
    "stats",
    "events",
    "delete",
]

DEFAULT_DB_ENV = "DEADLINE_CLOCK_DB"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS deadlines (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    title_key   TEXT NOT NULL,
    due_utc     TEXT NOT NULL,
    zone        TEXT NOT NULL,
    wall        TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL DEFAULT '',
    assumed     TEXT NOT NULL DEFAULT '',
    created_utc TEXT NOT NULL,
    done_utc    TEXT
);

CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(due_utc);
CREATE INDEX IF NOT EXISTS idx_deadlines_key ON deadlines(title_key);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deadline_id TEXT NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
    at_utc      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_deadline ON events(deadline_id, id);
"""


def default_db_path() -> Path:
    override = os.environ.get(DEFAULT_DB_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "deadline-clock" / "deadlines.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
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


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def new_id(existing: Iterable[str] = ()) -> str:
    taken = set(existing)
    for _ in range(50):
        candidate = "dl_" + secrets.token_hex(3)
        if candidate not in taken:
            return candidate
    raise RuntimeError("마감 id 를 만들지 못했습니다.")


@dataclass(frozen=True)
class Deadline:
    id: str
    title: str
    due_utc: str
    zone: str
    wall: str
    tags: str
    note: str
    source_text: str
    assumed: str
    created_utc: str
    done_utc: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict) -> "Deadline":
        data = dict(row)
        return cls(
            id=data["id"],
            title=data["title"],
            due_utc=data["due_utc"],
            zone=data["zone"],
            wall=data["wall"],
            tags=data.get("tags") or "",
            note=data.get("note") or "",
            source_text=data.get("source_text") or "",
            assumed=data.get("assumed") or "",
            created_utc=data["created_utc"],
            done_utc=data.get("done_utc"),
        )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "due_utc": self.due_utc,
            "zone": self.zone,
            "wall": self.wall,
            "tags": self.tags,
            "note": self.note,
            "source_text": self.source_text,
            "assumed": self.assumed,
            "created_utc": self.created_utc,
            "done_utc": self.done_utc,
        }

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]


@dataclass(frozen=True)
class AddResult:
    status: str  # "created" | "duplicate" | "revived"
    deadline: Deadline


def _event(conn: sqlite3.Connection, deadline_id: str, at: datetime, kind: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO events (deadline_id, at_utc, kind, detail) VALUES (?, ?, ?, ?)",
        (deadline_id, _iso(at), kind, detail),
    )


def add(
    conn: sqlite3.Connection,
    *,
    title: str,
    due_utc: datetime,
    zone: str,
    wall: datetime,
    tags: str = "",
    note: str = "",
    source_text: str = "",
    assumed: str = "",
    now: datetime | None = None,
) -> AddResult:
    name = re.sub(r"\s+", " ", (title or "").strip())
    if not name:
        raise ValueError("마감 제목이 비어 있습니다.")
    if len(name) > 120:
        raise ValueError(f"제목이 너무 깁니다({len(name)}자). 120자 이내로 적어 주세요.")
    stamp = now or datetime.now(UTC)
    key = _title_key(name)
    due_text = _iso(due_utc)

    existing = conn.execute(
        "SELECT * FROM deadlines WHERE title_key = ? AND due_utc = ? ORDER BY created_utc LIMIT 1",
        (key, due_text),
    ).fetchone()
    if existing is not None:
        row = Deadline.from_row(existing)
        if row.done_utc:
            conn.execute(
                "UPDATE deadlines SET done_utc = NULL, tags = ?, note = ? WHERE id = ?",
                (tags or row.tags, note or row.note, row.id),
            )
            _event(conn, row.id, stamp, "reopened", "같은 마감을 다시 추가")
            conn.commit()
            return AddResult("revived", get(conn, row.id))
        if tags and tags != row.tags:
            conn.execute("UPDATE deadlines SET tags = ? WHERE id = ?", (tags, row.id))
            conn.commit()
        return AddResult("duplicate", get(conn, row.id))

    rows = conn.execute("SELECT id FROM deadlines").fetchall()
    deadline_id = new_id(row["id"] for row in rows)
    conn.execute(
        """
        INSERT INTO deadlines
            (id, title, title_key, due_utc, zone, wall, tags, note, source_text, assumed, created_utc, done_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            deadline_id,
            name,
            key,
            due_text,
            zone,
            wall.strftime("%Y-%m-%dT%H:%M:%S"),
            tags or "",
            note or "",
            source_text or "",
            assumed or "",
            _iso(stamp),
        ),
    )
    _event(conn, deadline_id, stamp, "created", source_text or "")
    conn.commit()
    return AddResult("created", get(conn, deadline_id))


def get(conn: sqlite3.Connection, deadline_id: str) -> Deadline | None:
    row = conn.execute("SELECT * FROM deadlines WHERE id = ?", (deadline_id,)).fetchone()
    return Deadline.from_row(row) if row else None


def find(conn: sqlite3.Connection, ref: str, limit: int = 10) -> list[Deadline]:
    """id · id 앞부분 · 제목(부분 일치)로 찾는다. 최근 것부터."""
    needle = (ref or "").strip()
    if not needle:
        return []
    rows = conn.execute(
        "SELECT * FROM deadlines WHERE id = ? OR id LIKE ? ORDER BY due_utc",
        (needle, needle + "%"),
    ).fetchall()
    if rows:
        return [Deadline.from_row(r) for r in rows][:limit]
    key = _title_key(needle)
    rows = conn.execute(
        "SELECT * FROM deadlines WHERE title_key LIKE ? ORDER BY done_utc IS NOT NULL, due_utc LIMIT ?",
        (f"%{key}%", limit),
    ).fetchall()
    return [Deadline.from_row(r) for r in rows]


def list_rows(
    conn: sqlite3.Connection,
    *,
    window_seconds: int | None = None,
    tag: str | None = None,
    include_done: bool = False,
    now: datetime,
    limit: int = 50,
) -> list[Deadline]:
    """마감 가까운 순. window_seconds 를 주면 그 안(지난 것 포함)만."""
    clauses: list[str] = []
    params: list[object] = []
    if not include_done:
        clauses.append("done_utc IS NULL")
    if tag and tag.strip():
        clauses.append("(',' || tags || ',') LIKE ?")
        params.append(f"%,{tag.strip()},%")
    sql = "SELECT * FROM deadlines"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY due_utc"
    rows = [Deadline.from_row(r) for r in conn.execute(sql, params).fetchall()]
    if window_seconds is not None:
        from .clock import remaining_seconds  # 순환 import 를 피하려고 지역 import

        rows = [r for r in rows if remaining_seconds(_parse(r.due_utc), now) <= window_seconds]
    return rows[:limit]


def _parse(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def set_done(
    conn: sqlite3.Connection, deadline_id: str, done: bool, now: datetime
) -> tuple[str, Deadline] | None:
    """완료/되돌리기. 이미 그 상태면 'already'."""
    row = get(conn, deadline_id)
    if row is None:
        return None
    if done and row.done_utc:
        return "already", row
    if not done and not row.done_utc:
        return "already", row
    if done:
        conn.execute("UPDATE deadlines SET done_utc = ? WHERE id = ?", (_iso(now), row.id))
        _event(conn, row.id, now, "done")
        status = "done"
    else:
        conn.execute("UPDATE deadlines SET done_utc = NULL WHERE id = ?", (row.id,))
        _event(conn, row.id, now, "reopened")
        status = "reopened"
    conn.commit()
    return status, get(conn, row.id)


def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) AS n FROM deadlines").fetchone()["n"]
    closed = conn.execute("SELECT COUNT(*) AS n FROM deadlines WHERE done_utc IS NOT NULL").fetchone()["n"]
    events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    return {"total": total, "open": total - closed, "done": closed, "events": events}


def events(conn: sqlite3.Connection, deadline_id: str, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT at_utc, kind, detail FROM events WHERE deadline_id = ? ORDER BY id DESC LIMIT ?",
        (deadline_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def delete(conn: sqlite3.Connection, deadline_id: str) -> bool:
    cur = conn.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
    conn.commit()
    return cur.rowcount > 0
