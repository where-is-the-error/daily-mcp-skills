"""페이지 스냅샷 — "이 URL을 마지막으로 봤을 때와 지금이 같은가".

Fetch MCP는 매번 페이지를 새로 읽는다. 여기에 스냅샷을 붙여서
- 같은 내용이면 저장하지 않고(`unchanged`)
- 달라졌으면 이전 스냅샷과의 차이를 돌려준다(`changed`)
- 처음이면 전체를 저장한다(`new`)

content hash는 정규화된 본문 텍스트 기준이라, 광고·타임스탬프만 바뀐 페이지는
다시 저장하지 않는다.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import diff as diffmod
from .tokens import estimate

__all__ = ["Snapshot", "RememberResult", "remember", "latest", "previous", "history",
           "list_pages", "forget", "stats", "hash_text"]

MAX_SNAPSHOTS = 30


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Snapshot:
    id: int
    url: str
    fetched_at: str
    content_hash: str
    title: str
    text: str
    chars: int
    tokens: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Snapshot":
        return cls(
            id=row["id"],
            url=row["url"],
            fetched_at=row["fetched_at"],
            content_hash=row["content_hash"],
            title=row["title"],
            text=row["text"],
            chars=row["chars"],
            tokens=row["tokens"],
        )


@dataclass
class RememberResult:
    status: str            # new | unchanged | changed
    url: str
    title: str
    snapshot: Snapshot | None
    previous: Snapshot | None = None
    diff: diffmod.DiffResult | None = None
    tokens_saved: int = 0

    @property
    def changed(self) -> bool:
        return self.status == "changed"


def _row_to_snapshot(row: sqlite3.Row | None) -> Snapshot | None:
    return Snapshot.from_row(row) if row is not None else None


def latest(conn: sqlite3.Connection, url: str) -> Snapshot | None:
    row = conn.execute(
        "SELECT * FROM snapshots WHERE url = ? ORDER BY id DESC LIMIT 1", (url,)
    ).fetchone()
    return _row_to_snapshot(row)


def previous(conn: sqlite3.Connection, url: str) -> Snapshot | None:
    row = conn.execute(
        "SELECT * FROM snapshots WHERE url = ? ORDER BY id DESC LIMIT 1 OFFSET 1", (url,)
    ).fetchone()
    return _row_to_snapshot(row)


def history(conn: sqlite3.Connection, url: str, limit: int = 10) -> list[Snapshot]:
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE url = ? ORDER BY id DESC LIMIT ?", (url, max(1, limit))
    ).fetchall()
    return [Snapshot.from_row(row) for row in rows]


def remember(
    conn: sqlite3.Connection,
    url: str,
    title: str,
    text: str,
    *,
    fetched_at: datetime | None = None,
    keep: int = MAX_SNAPSHOTS,
) -> RememberResult:
    """페이지 본문을 기억한다. 같은 내용이면 스냅샷을 늘리지 않는다."""
    stamp = _iso(fetched_at or datetime.now(timezone.utc))
    digest = hash_text(text)
    before = latest(conn, url)

    with conn:
        conn.execute(
            """
            INSERT INTO pages (url, title, first_seen, last_seen, checks, changes, last_hash)
            VALUES (?, ?, ?, ?, 1, 0, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                last_seen = excluded.last_seen,
                checks = pages.checks + 1
            """,
            (url, title, stamp, stamp, digest),
        )

        if before is not None and before.content_hash == digest:
            return RememberResult(
                status="unchanged",
                url=url,
                title=title or before.title,
                snapshot=before,
                tokens_saved=before.tokens,
            )

        cursor = conn.execute(
            """
            INSERT INTO snapshots (url, fetched_at, content_hash, title, text, chars, tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url, stamp, digest, title, text, len(text), estimate(text)),
        )
        snapshot = Snapshot(
            id=int(cursor.lastrowid),
            url=url,
            fetched_at=stamp,
            content_hash=digest,
            title=title,
            text=text,
            chars=len(text),
            tokens=estimate(text),
        )
        conn.execute("UPDATE pages SET last_hash = ? WHERE url = ?", (digest, url))

        if before is None:
            return RememberResult(status="new", url=url, title=title, snapshot=snapshot)

        delta = diffmod.diff_lines(before.text, text)
        conn.execute("UPDATE pages SET changes = changes + 1 WHERE url = ?", (url,))
        conn.execute(
            """
            DELETE FROM snapshots
            WHERE url = ? AND id NOT IN (
                SELECT id FROM snapshots WHERE url = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (url, url, max(2, keep)),
        )
        return RememberResult(
            status="changed",
            url=url,
            title=title,
            snapshot=snapshot,
            previous=before,
            diff=delta,
            tokens_saved=max(0, snapshot.tokens - estimate(delta.render())),
        )


@dataclass
class PageRow:
    url: str
    title: str
    checks: int
    changes: int
    last_seen: str
    tags: str
    snapshots: int
    tokens: int


def list_pages(
    conn: sqlite3.Connection,
    *,
    stale_days: int | None = None,
    limit: int = 50,
    tag: str | None = None,
    now: datetime | None = None,
) -> list[PageRow]:
    sql = """
        SELECT p.url, p.title, p.checks, p.changes, p.last_seen, p.tags,
               (SELECT COUNT(*) FROM snapshots s WHERE s.url = p.url) AS snapshots,
               (SELECT tokens FROM snapshots s WHERE s.url = p.url ORDER BY id DESC LIMIT 1) AS tokens
        FROM pages p
    """
    rows = conn.execute(sql + " ORDER BY p.last_seen DESC").fetchall()
    out: list[PageRow] = []
    cutoff = None
    if stale_days is not None:
        base = now or datetime.now(timezone.utc)
        cutoff = (base - timedelta(days=stale_days)).isoformat(timespec="seconds")
    for row in rows:
        if tag and tag.lower() not in (row["tags"] or "").lower():
            continue
        if cutoff is not None:
            last = row["last_seen"] or ""
            if last > cutoff:  # 최근에 봤으면 stale 아님
                continue
        out.append(
            PageRow(
                url=row["url"],
                title=row["title"] or "",
                checks=row["checks"],
                changes=row["changes"],
                last_seen=row["last_seen"],
                tags=row["tags"] or "",
                snapshots=row["snapshots"] or 0,
                tokens=row["tokens"] or 0,
            )
        )
        if len(out) >= max(1, limit):
            break
    return out


def forget(conn: sqlite3.Connection, url: str) -> int:
    """페이지와 스냅샷을 지운다. 남은 스냅샷 수를 돌려준다."""
    with conn:
        count = conn.execute("SELECT COUNT(*) FROM snapshots WHERE url = ?", (url,)).fetchone()[0]
        conn.execute("DELETE FROM snapshots WHERE url = ?", (url,))
        conn.execute("DELETE FROM pages WHERE url = ?", (url,))
    return int(count)


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    def one(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0] or 0)

    return {
        "pages": one("SELECT COUNT(*) FROM pages"),
        "snapshots": one("SELECT COUNT(*) FROM snapshots"),
        "changed_pages": one("SELECT COUNT(*) FROM pages WHERE changes > 0"),
        "tokens": one("SELECT COALESCE(SUM(tokens),0) FROM snapshots"),
    }
