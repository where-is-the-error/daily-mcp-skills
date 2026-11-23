"""MCP 배선 — 아홉 툴.

    MIGRATE_GUARD_ROOT=/path/to/db python -m migrate_guard.server

MCP 클라이언트 설정:

    {"mcpServers": {"migrate-guard": {
      "command": "python", "args": ["-m", "migrate_guard.server"],
      "env": {"MIGRATE_GUARD_ROOT": "/Users/me/app/db"}}}}
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import report
from .compare import compare
from .loader import build
from .schema import diff_schema, parse_schema, schema_after

DEFAULT_TOKENS = 1500
CHARS_PER_TOKEN = 4

mcp = MCPServer(
    name="migrate-guard",
    title="migrate-guard",
    version="0.1.0",
    instructions=(
        "PostgreSQL 마이그레이션 파일을 실행 전에 읽는 서버입니다. "
        "read_migration 으로 무엇이 바뀌는지 보고, lock_report 로 어떤 락이 얼마나 유지되는지, "
        "risk_report 로 되돌릴 수 없는 변경과 재작성을 확인하세요. "
        "rollout_plan 은 위험한 문장을 확장·백필·전환 단계로 다시 씁니다. "
        "판정하지 않는 것: 실행 시간의 실측, 지금 잡혀 있는 락, 복제 지연, 데이터 값의 분포. "
        "예상 시간은 행/초 가정으로 계산한 모델이며 결과에도 그렇게 적습니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("MIGRATE_GUARD_ROOT")
    return Path(root) if root else None


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _finish(text: str, max_tokens: int | None) -> str:
    budget = DEFAULT_TOKENS if not max_tokens else max(1, int(max_tokens))
    limit = budget * CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n\n… ({budget} 토큰에서 잘랐습니다. max_tokens 를 늘리세요)"


def _migration(source, baseline, rows, pg_version):
    return build(source, baseline=baseline, rows=rows, pg_version=pg_version, root=_root())


@mcp.tool()
def read_migration(source: str, baseline: str = "", rows: str = "", pg_version: int = 16,
                   max_tokens: int = DEFAULT_TOKENS) -> str:
    """마이그레이션을 한 화면으로 요약한다 — 판정, 최대 잠금, 먼저 볼 문장.

    source: SQL 파일 경로(MIGRATE_GUARD_ROOT 기준) 또는 SQL 문자열.
    baseline: 기준 스키마 파일(있으면 타입 변경을 정확히 판정).
    rows: {"users": 1400000} 형태의 행 수 JSON(파일 경로 또는 문자열).
    """
    try:
        migration = _migration(source, baseline, rows, pg_version)
        return _finish(report.summary(migration), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def list_statements(source: str, baseline: str = "", pg_version: int = 16, max_items: int = 40,
                    max_tokens: int = DEFAULT_TOKENS) -> str:
    """문장 목록 — ref(s1…), 줄 번호, 종류, 락 모드. 뒤에서 ref 로 지목할 수 있다."""
    try:
        migration = _migration(source, baseline, "", pg_version)
        return _finish(report.statements(migration, max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def lock_report(source: str, baseline: str = "", rows: str = "", pg_version: int = 16,
                max_tokens: int = DEFAULT_TOKENS) -> str:
    """잠금 — 문장별 락 모드, 무엇이 막히는지, 예상 유지 시간(모델)."""
    try:
        migration = _migration(source, baseline, rows, pg_version)
        return _finish(report.locks(migration), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def risk_report(source: str, baseline: str = "", rows: str = "", pg_version: int = 16,
                severity: str = "", max_items: int = 14, max_tokens: int = DEFAULT_TOKENS) -> str:
    """위험 판정 — 등급·근거 값·고치는 문장.

    severity: 치명 | 심각 | 보통 | 참고 — 그 등급 이상만 보여 준다.
    """
    try:
        migration = _migration(source, baseline, rows, pg_version)
        return _finish(report.risk(migration, severity=severity, max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rollout_plan(source: str, baseline: str = "", rows: str = "", pg_version: int = 16,
                 max_tokens: int = DEFAULT_TOKENS) -> str:
    """위험한 마이그레이션을 확장 → 백필 → 전환 단계로 다시 쓴 SQL."""
    try:
        migration = _migration(source, baseline, rows, pg_version)
        return _finish(report.rollout(migration), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rollback_plan(source: str, baseline: str = "", pg_version: int = 16,
                  max_tokens: int = DEFAULT_TOKENS) -> str:
    """되돌리기 SQL(역순) — 값이 사라진 단계는 그렇다고 표시한다."""
    try:
        migration = _migration(source, baseline, "", pg_version)
        return _finish(report.rollback(migration), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def schema_change(source: str, baseline: str, pg_version: int = 16,
                  max_tokens: int = DEFAULT_TOKENS) -> str:
    """기준 스키마에 이 마이그레이션을 적용한 뒤의 변화 — 새 표·사라지는 컬럼·바뀌는 타입."""
    try:
        from .loader import resolve_optional

        migration = _migration(source, baseline, "", pg_version)
        text = resolve_optional(baseline, _root()) or baseline
        before = parse_schema(text)
        after = schema_after(before, migration.statements)
        return _finish(report.schema_diff(diff_schema(before, after), label=migration.label), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_migrations(before: str, after: str, baseline: str = "", rows: str = "", pg_version: int = 16,
                       max_items: int = 10, max_tokens: int = DEFAULT_TOKENS) -> str:
    """마이그레이션 두 개 비교 — 등급 변화, 사라진 규칙, 가장 긴 잠금."""
    try:
        a = _migration(before, baseline, rows, pg_version)
        b = _migration(after, baseline, rows, pg_version)
        return _finish(compare(a, b).render(max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog() -> str:
    """규칙 목록과 이 도구가 판정하지 않는 것 — 결과를 해석하기 전에 읽으세요."""
    return report.rules()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="migrate-guard MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="마이그레이션 파일 기준 디렉터리 (MIGRATE_GUARD_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["MIGRATE_GUARD_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
