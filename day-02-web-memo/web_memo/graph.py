"""기억 그래프 — 엔티티 · 관찰 · 관계.

Memory MCP의 세 원자(entities / relations / observations)를 그대로 가져왔다.
바꾼 것:
- 엔티티 이름은 URL이거나 토픽 이름이고, **URL 엔티티에는 스냅샷이 자동으로 연결**된다
  (`pages.url` ↔ `entities.name`). 그래서 "이 페이지에 대해 내가 남긴 말"과
  "페이지 본문"이 같은 검색에서 만난다.
- `delete_*` 3종은 툴로 노출하지 않는다(읽기 위주의 서버 + 지우기는 `forget_page` 하나로).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = ["Observation", "annotate", "observations", "neighbors", "graph_stats",
           "entity_type", "ensure_entity"]


def _iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def entity_type(name: str) -> str:
    low = name.lower()
    if low.startswith(("http://", "https://")):
        return "page"
    if low.startswith("@"):
        return "person"
    if " " not in name and "/" in name:
        return "repo"
    return "topic"


def ensure_entity(conn: sqlite3.Connection, name: str, kind: str | None = None) -> bool:
    """엔티티를 만들고, 새로 만들었으면 True."""
    name = name.strip()
    if not name:
        raise ValueError("엔티티 이름이 비어 있습니다.")
    exists = conn.execute("SELECT 1 FROM entities WHERE name = ?", (name,)).fetchone()
    if exists:
        return False
    conn.execute(
        "INSERT INTO entities (name, type, created) VALUES (?, ?, ?)",
        (name, kind or entity_type(name), _iso()),
    )
    return True


@dataclass
class Observation:
    id: int
    entity: str
    text: str
    source: str | None
    created: str


@dataclass
class AnnotationResult:
    target: str
    created_entity: bool
    added_note: bool
    tags: list[str]
    notes: list[Observation]


def annotate(
    conn: sqlite3.Connection,
    target: str,
    note: str = "",
    *,
    tags: tuple[str, ...] | list[str] = (),
    source: str | None = None,
) -> AnnotationResult:
    """대상에 메모와 태그를 단다.

    - `note`는 observation으로 쌓인다 (같은 문장은 두 번 쌓지 않는다).
    - `tags`는 각각 `topic` 엔티티가 되고 `tagged` 관계로 이어진다.
    """
    target = target.strip()
    note = (note or "").strip()
    clean_tags = [t.strip().lstrip("#") for t in tags if t and t.strip()]
    stamp = _iso()

    with conn:
        created = ensure_entity(conn, target)
        for tag in clean_tags:
            ensure_entity(conn, tag, "topic")
            conn.execute(
                "INSERT OR IGNORE INTO relations (src, dst, kind, created) VALUES (?, ?, 'tagged', ?)",
                (target, tag, stamp),
            )
            conn.execute(
                "INSERT OR IGNORE INTO relations (src, dst, kind, created) VALUES (?, ?, 'tagged_by', ?)",
                (tag, target, stamp),
            )
        added = False
        if note:
            dup = conn.execute(
                "SELECT 1 FROM observations WHERE entity = ? AND text = ?", (target, note)
            ).fetchone()
            if not dup:
                conn.execute(
                    "INSERT INTO observations (entity, text, source, created) VALUES (?, ?, ?, ?)",
                    (target, note, source, stamp),
                )
                added = True
        if source and source != target:
            ensure_entity(conn, source)
            conn.execute(
                "INSERT OR IGNORE INTO relations (src, dst, kind, created) VALUES (?, ?, 'about', ?)",
                (source, target, stamp),
            )

    return AnnotationResult(
        target=target,
        created_entity=created,
        added_note=added,
        tags=clean_tags,
        notes=observations(conn, target),
    )


def observations(conn: sqlite3.Connection, entity: str, limit: int = 20) -> list[Observation]:
    rows = conn.execute(
        "SELECT id, entity, text, source, created FROM observations "
        "WHERE entity = ? ORDER BY id DESC LIMIT ?",
        (entity, max(1, limit)),
    ).fetchall()
    return [
        Observation(
            id=row["id"],
            entity=row["entity"],
            text=row["text"],
            source=row["source"],
            created=row["created"],
        )
        for row in rows
    ]


def neighbors(conn: sqlite3.Connection, entity: str, limit: int = 20) -> list[tuple[str, str, str]]:
    """(관계, 상대, 방향) 목록."""
    out: list[tuple[str, str, str]] = []
    for row in conn.execute(
        "SELECT dst, kind FROM relations WHERE src = ? ORDER BY kind, dst LIMIT ?", (entity, limit)
    ):
        out.append((row["kind"], row["dst"], "→"))
    for row in conn.execute(
        "SELECT src, kind FROM relations WHERE dst = ? ORDER BY kind, src LIMIT ?", (entity, limit)
    ):
        out.append((row["kind"], row["src"], "←"))
    return out


def graph_stats(conn: sqlite3.Connection) -> dict[str, int]:
    def one(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0] or 0)

    return {
        "entities": one("SELECT COUNT(*) FROM entities"),
        "observations": one("SELECT COUNT(*) FROM observations"),
        "relations": one("SELECT COUNT(*) FROM relations"),
    }
