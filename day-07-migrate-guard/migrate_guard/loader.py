"""파일이든 SQL 문자열이든 받아서 Migration 으로 만든다 — CLI 와 MCP 가 같이 쓴다."""

from __future__ import annotations

import json
from pathlib import Path

from .operations import Migration, analyze
from .schema import Schema, parse_schema

__all__ = ["resolve_text", "resolve_optional", "parse_rows", "build"]


def _resolve(value: str, root: Path | None) -> str:
    text = value.strip()
    candidate = Path(text)
    if not candidate.is_absolute() and root is not None:
        candidate = root / text
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return value


def resolve_text(value: str, root: Path | None = None) -> str:
    """경로면 읽고, 아니면 문자열 그대로."""
    return _resolve(value, root)


def resolve_optional(value: str | None, root: Path | None = None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _resolve(str(value), root)


def parse_rows(value: str | None, root: Path | None = None) -> dict[str, int]:
    """`{"users": 1400000}` 또는 그 JSON 이 담긴 파일."""
    if not value or not str(value).strip():
        return {}
    raw = resolve_text(str(value), root)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"행 수 JSON 을 읽지 못했습니다: {exc}") from exc
    if isinstance(data, dict) and "tables" in data and isinstance(data["tables"], dict):
        data = data["tables"]
    if not isinstance(data, dict):
        raise ValueError("행 수는 {\"표이름\": 행수} 형태의 JSON 이어야 합니다.")
    out: dict[str, int] = {}
    for key, count in data.items():
        try:
            out[str(key).lower()] = int(count)
        except (TypeError, ValueError):
            continue
    return out


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    return "\n" not in text and text.lower().endswith((".sql", ".ddl"))


def build(
    source: str,
    *,
    baseline: str | None = None,
    rows: str | None = None,
    pg_version: int = 16,
    root: Path | None = None,
    label: str = "",
) -> Migration:
    if _looks_like_path(source):
        candidate = Path(source.strip())
        resolved = candidate if candidate.is_absolute() or root is None else root / candidate
        if not resolved.is_file():
            raise FileNotFoundError(f"파일을 찾지 못했습니다: {source}")
    text = resolve_text(source, root)
    baseline_text = resolve_optional(baseline, root)
    baseline_schema: Schema | None = parse_schema(baseline_text) if baseline_text else None
    stats = parse_rows(rows, root)
    name = label
    if not name:
        candidate = Path(source.strip())
        if candidate.is_file() or (root is not None and (root / candidate).is_file()):
            name = candidate.name
    return analyze(
        text,
        baseline=baseline_schema,
        rows=stats,
        pg_version=pg_version,
        label=name or "마이그레이션",
    )
