"""CLI — MCP 없이도 같은 일을 한다.

    sheet-guard read examples/raw.csv
    sheet-guard problems examples/raw.csv
    sheet-guard clean examples/raw.csv --out out/clean.csv
    sheet-guard md examples/raw.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from .apply import apply_plan, write_changelog, write_csv, write_quarantine
from .compare import compare
from .markdown import to_markdown
from .plan import build_plan
from .rules import check, counts
from .store import STORE, file_fingerprint
from .table import load_table


def _load(path: str, sheet: str | None = None):
    table = load_table(Path(path), sheet=sheet)
    ref = STORE.put(table, file_fingerprint(path))
    return table, ref


def _problems(args) -> int:
    table, ref = _load(args.path, args.sheet)
    findings = check(table, key=args.key)
    print(f"[{ref}]")
    print(report.problems_view(findings, max_items=args.max_items, severity=args.severity))
    return 2 if counts(findings)["error"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sheet-guard", description="표를 쓰기 전에 읽는다")
    sub = parser.add_subparsers(dest="command", required=True)

    read = sub.add_parser("read", help="표 구조와 열 요약")
    read.add_argument("path")
    read.add_argument("--sheet", default=None)

    profile = sub.add_parser("profile", help="열마다 종류·채움률")
    profile.add_argument("path")
    profile.add_argument("--sheet", default=None)
    profile.add_argument("--all", action="store_true", help="모든 열 보기")

    problems = sub.add_parser("problems", help="규칙 위반 목록")
    problems.add_argument("path")
    problems.add_argument("--sheet", default=None)
    problems.add_argument("--key", default="", help="키 열 이름(중복 확인)")
    problems.add_argument("--severity", default="", choices=["", "error", "warn", "info"])
    problems.add_argument("--max-items", type=int, default=20)

    plan = sub.add_parser("plan", help="정리 계획")
    plan.add_argument("path")
    plan.add_argument("--sheet", default=None)
    plan.add_argument("--key", default="")
    plan.add_argument("--only", default="", help="규칙 id 쉼표 목록만 반영")

    clean = sub.add_parser("clean", help="정리본 만들기")
    clean.add_argument("path")
    clean.add_argument("--out", required=True)
    clean.add_argument("--sheet", default=None)
    clean.add_argument("--changelog", default="")
    clean.add_argument("--key", default="")
    clean.add_argument("--only", default="")
    clean.add_argument("--dry-run", action="store_true")

    md = sub.add_parser("md", help="마크다운 표")
    md.add_argument("path")
    md.add_argument("--sheet", default=None)
    md.add_argument("--max-rows", type=int, default=20)
    md.add_argument("--clean", action="store_true", help="정리 계획을 적용한 표로 출력")

    diff = sub.add_parser("compare", help="정리 전후 비교")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--key", default="")

    rules = sub.add_parser("rules", help="규칙 목록")
    rules.add_argument("rule", nargs="?", default="")

    args = parser.parse_args(argv)

    try:
        if args.command == "read":
            table, ref = _load(args.path, args.sheet)
            print(f"[{ref}]")
            print(report.table_summary(table))
            return 0
        if args.command == "profile":
            table, ref = _load(args.path, args.sheet)
            print(f"[{ref}]")
            stats = table.stats() if args.all else table.stats()[:20]
            for stat in stats:
                data = stat.summary()
                print(f"{data['name']}: {data['kind']} · 채움 {data['fill'] * 100:.0f}% · "
                      f"{data['distinct']:,}종 · {data['kinds']}")
            return 0
        if args.command == "problems":
            return _problems(args)
        if args.command == "plan":
            table, ref = _load(args.path, args.sheet)
            findings = check(table, key=args.key)
            only = tuple(x.strip() for x in args.only.split(",") if x.strip())
            plan = build_plan(table, findings, only=only)
            print(f"[{ref}]")
            print(report.problems_view(findings, max_items=6, severity="error"))
            print()
            print(report.plan_view(plan))
            return 2 if counts(findings)["error"] else 0
        if args.command == "clean":
            table, ref = _load(args.path, args.sheet)
            findings = check(table, key=args.key)
            only = tuple(x.strip() for x in args.only.split(",") if x.strip())
            plan = build_plan(table, findings, only=only)
            applied = apply_plan(table, plan)
            print(f"[{ref}]")
            print(report.plan_view(plan))
            print()
            if args.dry_run:
                print("(--dry-run: 파일을 쓰지 않았습니다)")
                return 0
            out = write_csv(applied.table, args.out)
            changelog = args.changelog or str(Path(args.out).with_name(Path(args.out).stem + ".changes.csv"))
            write_changelog(applied, changelog)
            print(report.applied_view(applied, out_path=str(out)))
            print(f"   바뀐 곳 기록: {changelog}")
            ragged = write_quarantine(applied, Path(args.out).with_name(Path(args.out).stem + ".ragged.csv"),
                                      table.column_names)
            if ragged:
                print(f"   격리한 행: {ragged}")
            print()
            print(report.diff_view(compare(table, applied.table)))
            return 0
        if args.command == "md":
            table, ref = _load(args.path, args.sheet)
            if args.clean:
                findings = check(table)
                applied = apply_plan(table, build_plan(table, findings))
                table = applied.table
            print(f"[{ref}]")
            print(to_markdown(table, max_rows=args.max_rows))
            return 0
        if args.command == "compare":
            before, ref_a = _load(args.before)
            after, ref_b = _load(args.after)
            print(f"[{ref_a} → {ref_b}]")
            print(report.diff_view(compare(before, after, key=args.key or None)))
            return 0
        if args.command == "rules":
            print(report.catalog_view(args.rule))
            return 0
        return 1
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
