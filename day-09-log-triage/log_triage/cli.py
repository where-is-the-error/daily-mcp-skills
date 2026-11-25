"""명령줄 — MCP 없이도 같은 일을 한다.

    log-triage read logs/api.log
    log-triage sigs logs/api.log --limit 8
    log-triage problems logs/api.log        # 치명 있으면 exit 2, 주의 있으면 1
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report
from .compare import compare
from .parse import load_log, read_whole
from .rates import analyze as analyze_rates
from .redact import redact_text
from .rules import catalog as rule_catalog, check, counts, worst
from .search import find
from .signature import cluster
from .stack import stack_report
from .timeline import build as build_timeline


def _load(path: str, assume_year: int = 2026):
    log = load_log(path, assume_year=assume_year)
    return log, cluster(log)


def cmd_read(args) -> int:
    log = load_log(args.path, assume_year=args.year)
    print(report.table_summary(log))
    print()
    print(report.signature_view(cluster(log), log, limit=args.limit))
    print(f"\n{report.LIMITS}")
    return 0


def cmd_sigs(args) -> int:
    log, clusters = _load(args.path, args.year)
    print(report.signature_view(clusters, log, limit=args.limit))
    return 0


def cmd_rates(args) -> int:
    log, clusters = _load(args.path, args.year)
    rate = analyze_rates(log, bucket_seconds=args.bucket,
                         templates={c.signature: c.template for c in clusters})
    print(report.rate_view(rate, log))
    return 0


def cmd_compare(args) -> int:
    before, _ = _load(args.before, args.year)
    after, _ = _load(args.after, args.year)
    result = compare(before, after)
    print(report.compare_view(result, limit=args.limit))
    return 0


def cmd_stack(args) -> int:
    log, clusters = _load(args.path, args.year)
    print(report.stack_view(stack_report(log, clusters), log, limit=args.limit))
    return 0


def cmd_timeline(args) -> int:
    log, clusters = _load(args.path, args.year)
    baseline = None
    if args.baseline:
        baseline, _ = _load(args.baseline, args.year)
    timeline = build_timeline(log, gap_minutes=args.gap, clusters=clusters, baseline=baseline)
    print(report.timeline_view(timeline, log, limit=args.limit))
    return 0


def cmd_find(args) -> int:
    log, _ = _load(args.path, args.year)
    result = find(log, args.pattern, context=args.context, regex=args.regex,
                  ignore_case=not args.case_sensitive, max_matches=args.max_matches)
    if result.error:
        print(f"⚠️ {result.error}")
        return 2
    print(f"🔍 '{result.pattern}' — {result.total:,}줄 일치 (훑은 줄 {result.scanned:,})")
    for match in result.matches:
        for line_no, text in match.before:
            print(f"  {line_no:>7}   {text[:160]}")
        print(f"  {match.line_no:>7} > {match.text[:160]}")
        for line_no, text in match.after:
            print(f"  {line_no:>7}   {text[:160]}")
        print()
    return 0


def cmd_problems(args) -> int:
    log, _ = _load(args.path, args.year)
    now = datetime.fromisoformat(args.now) if args.now else None
    findings = check(log, now=now)
    print(report.table_summary(log))
    print()
    print(report.problems_view(findings, limit=args.limit))
    print()
    print(report.fix_order(findings))
    print(f"\n{report.LIMITS}")
    tally = counts(findings)
    if tally.get("critical"):
        return 2
    if tally.get("warn"):
        return 1
    return 0


def cmd_redact(args) -> int:
    log, text = read_whole(args.path)
    result = redact_text(text)
    out_path = ""
    if args.out:
        out_path = str(Path(args.out))
        Path(out_path).write_text("\n".join(line for _, line in result.texts) + "\n", encoding="utf-8")
    preview = [(number, line) for number, line in result.texts
               if line != text.splitlines()[number - 1]][: args.preview]
    print(report.redact_view(result, preview=preview, out=out_path,
                             checked_lines=len(text.splitlines())))
    if result.residual_total:
        print("   ⚠️ 남은 값이 있습니다 — 결과를 그대로 넘기지 마세요")
        return 2
    return 0


def cmd_catalog(args) -> int:
    print(report.catalog_view(args.rule))
    return 0


def cmd_overview(args) -> int:
    print(report.OVERVIEW)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="log-triage", description="로그를 넘기기 전에 읽는 도구")
    parser.add_argument("--year", type=int, default=2026, help="연도 없는 표기에 쓸 연도")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("read", help="파일 요약 + 서명")
    p.add_argument("path")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("sigs", help="서명 묶음")
    p.add_argument("path")
    p.add_argument("--limit", type=int, default=12)
    p.set_defaults(func=cmd_sigs)

    p = sub.add_parser("rates", help="분당 세기·폭주·끊김")
    p.add_argument("path")
    p.add_argument("--bucket", type=int, default=60)
    p.set_defaults(func=cmd_rates)

    p = sub.add_parser("compare", help="before/after 비교")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("stack", help="스택 위치·예외")
    p.add_argument("path")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_stack)

    p = sub.add_parser("timeline", help="첫 오류·에피소드")
    p.add_argument("path")
    p.add_argument("--baseline", default="")
    p.add_argument("--gap", type=float, default=5.0)
    p.add_argument("--limit", type=int, default=6)
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("find", help="문자열/정규식 검색")
    p.add_argument("path")
    p.add_argument("pattern")
    p.add_argument("--context", type=int, default=2)
    p.add_argument("--regex", action="store_true")
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--max-matches", type=int, default=20)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("problems", help="규칙 위반")
    p.add_argument("path")
    p.add_argument("--now", default="")
    p.add_argument("--limit", type=int, default=12)
    p.set_defaults(func=cmd_problems)

    p = sub.add_parser("redact", help="비밀·개인정보 마스킹")
    p.add_argument("path")
    p.add_argument("--out", default="")
    p.add_argument("--preview", type=int, default=5)
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("catalog", help="규칙 목록")
    p.add_argument("rule", nargs="?", default="")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("overview", help="이 도구 설명")
    p.set_defaults(func=cmd_overview)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"⚠️ {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
