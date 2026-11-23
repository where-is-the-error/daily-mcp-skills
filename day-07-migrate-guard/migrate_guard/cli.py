"""CLI — 마이그레이션 파일 하나를 여러 각도로 본다.

    migrate-guard summary  0012_add_email.up.sql --baseline schema.sql --rows stats.json
    migrate-guard locks   0012_add_email.up.sql --rows stats.json
    migrate-guard risk    0012_add_email.up.sql --fail-on 치명
    migrate-guard rollout 0012_add_email.up.sql --out 0012.fixed.sql
    migrate-guard rollback 0012_add_email.up.sql
    migrate-guard schema  0012_add_email.up.sql --baseline schema.sql
    migrate-guard compare 0012_add_email.up.sql 0012_add_email.fixed.sql
    migrate-guard rules

종료 코드: 0 정상, 1 입력 오류, 2 `--fail-on` 기준에 걸림(CI 게이트).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from . import risks
from .compare import compare
from .loader import build
from .schema import diff_schema, parse_schema, schema_after

PG_DEFAULT = 16


def _build(args) -> "object":
    return build(
        args.migration,
        baseline=getattr(args, "baseline", None),
        rows=getattr(args, "rows", None),
        pg_version=args.pg_version,
    )


def cmd_summary(args) -> int:
    print(report.summary(_build(args)), end="")
    return 0


def cmd_statements(args) -> int:
    print(report.statements(_build(args), max_items=args.max_items), end="")
    return 0


def cmd_locks(args) -> int:
    print(report.locks(_build(args), max_items=args.max_items), end="")
    return 0


def cmd_risk(args) -> int:
    migration = _build(args)
    print(report.risk(migration, severity=args.severity, max_items=args.max_items), end="")
    if args.fail_on:
        threshold = args.fail_on.strip()
        if threshold not in risks.SEVERITY_ORDER:
            print("--fail-on 은 치명 · 심각 · 보통 · 참고 중 하나입니다.", file=sys.stderr)
            return 1
        limit = risks.SEVERITY_ORDER[threshold]
        if any(risks.SEVERITY_ORDER[f.severity.name] <= limit for f in risks.findings(migration)):
            print(f"\n게이트: {threshold} 이상이 있어 종료 코드 2 로 끝냅니다.", file=sys.stderr)
            return 2
    return 0


def cmd_rollout(args) -> int:
    text = _rollout_text(_build(args))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
        return 0
    print(text, end="")
    return 0


def _rollout_text(migration) -> str:
    from .rollout import rollout_sql

    return rollout_sql(migration)


def cmd_rollback(args) -> int:
    from .rollback import rollback_sql

    text = rollback_sql(_build(args))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
        return 0
    print(text, end="")
    return 0


def cmd_schema(args) -> int:
    migration = _build(args)
    text = Path(args.baseline).read_text(encoding="utf-8") if Path(args.baseline).is_file() else args.baseline
    before = parse_schema(text)
    after = schema_after(before, migration.statements)
    print(report.schema_diff(diff_schema(before, after), label=args.migration), end="")
    return 0


def cmd_compare(args) -> int:
    first = build(args.before, baseline=args.baseline, rows=args.rows, pg_version=args.pg_version)
    second = build(args.after, baseline=args.baseline, rows=args.rows, pg_version=args.pg_version)
    print(report.comparison(compare(first, second), max_items=args.max_items), end="")
    return 0


def cmd_rules(args) -> int:
    print(report.rules(), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrate-guard", description="실행 전에 마이그레이션을 읽는다")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(name: str, help_text: str, *, baseline: bool = False, rows: bool = True) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=help_text)
        child.add_argument("migration", help="마이그레이션 SQL 파일")
        if baseline:
            child.add_argument("--baseline", default=None, help="기준 스키마 SQL 파일")
        if rows:
            child.add_argument("--rows", default=None, help='행 수 JSON ({"users": 1400000} 또는 파일)')
        child.add_argument("--pg-version", type=int, default=PG_DEFAULT, help="PostgreSQL 버전(기본 16)")
        return child

    summary = common("summary", "한 화면 요약", baseline=True)
    summary.set_defaults(func=cmd_summary)

    listing = common("statements", "문장 목록", baseline=True)
    listing.add_argument("--max-items", type=int, default=40)
    listing.set_defaults(func=cmd_statements)

    locks = common("locks", "잠금 보고서", baseline=True)
    locks.add_argument("--max-items", type=int, default=20)
    locks.set_defaults(func=cmd_locks)

    risk = common("risk", "위험 판정", baseline=True)
    risk.add_argument("--severity", default="", help="치명 | 심각 | 보통 | 참고")
    risk.add_argument("--fail-on", default=None, help="이 등급 이상이면 종료 코드 2")
    risk.add_argument("--max-items", type=int, default=14)
    risk.set_defaults(func=cmd_risk)

    rollout = common("rollout", "확장·백필·전환으로 다시 쓴 SQL", baseline=True)
    rollout.add_argument("--out", default=None)
    rollout.set_defaults(func=cmd_rollout)

    rollback = common("rollback", "되돌리기 SQL", baseline=True, rows=False)
    rollback.add_argument("--out", default=None)
    rollback.set_defaults(func=cmd_rollback)

    schema = common("schema", "적용 전후 스키마 비교", rows=False)
    schema.add_argument("--baseline", default=None, required=True, help="기준 스키마 SQL 파일")
    schema.set_defaults(func=cmd_schema)

    compare_cmd = sub.add_parser("compare", help="마이그레이션 두 개 비교")
    compare_cmd.add_argument("before")
    compare_cmd.add_argument("after")
    compare_cmd.add_argument("--baseline", default=None)
    compare_cmd.add_argument("--rows", default=None)
    compare_cmd.add_argument("--pg-version", type=int, default=PG_DEFAULT)
    compare_cmd.add_argument("--max-items", type=int, default=10)
    compare_cmd.set_defaults(func=cmd_compare)

    rules_cmd = sub.add_parser("rules", help="규칙 목록")
    rules_cmd.set_defaults(func=cmd_rules, migration=None, pg_version=PG_DEFAULT, rows=None, baseline=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, FileNotFoundError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
