"""명령줄 — 저장소와 diff 로 한 번에 돌린다.

    test-radar scan . --diff change.patch          # 보고서
    test-radar scan . --diff -                     # 표준입력
    test-radar scan . --base origin/main           # git diff 로 직접 뽑기
    test-radar scan . --diff change.patch --json
    test-radar rules                               # 규칙 22종

종료 코드: 0 통과 · 1 사용 오류 · 2 치명 규칙 있음.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import diffparse, risk as risk_module
from .graph import load
from .plan import build as build_plan
from .report import change_lines, impact_report
from .select import build as build_set


def _read_diff(args) -> str:
    if args.diff:
        if args.diff == "-":
            return sys.stdin.read()
        return Path(args.diff).read_text(encoding="utf-8")
    if args.base:
        command = ["git", "-C", args.repo, "diff", "--no-color", args.base]
        if args.staged:
            command.insert(4, "--cached")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise SystemExit(f"git diff 실패: {result.stderr.strip()[:400]}")
        return result.stdout
    raise SystemExit("--diff 또는 --base 가 필요합니다 (예: --diff - < change.patch)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test-radar", description="바뀐 코드에 도달하는 테스트만 고른다")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="저장소 + diff → 선택·구멍·위험·계획")
    scan.add_argument("repo", help="저장소 루트")
    scan.add_argument("--diff", default="", help="unified diff 파일 (또는 '-' 표준입력)")
    scan.add_argument("--base", default="", help="git diff <base> 로 직접 뽑기")
    scan.add_argument("--staged", action="store_true", help="--base 와 함께 쓰면 --cached")
    scan.add_argument("--shards", type=int, default=2, help="필수 테스트를 나눌 조각 수 (기본 2)")
    scan.add_argument("--per-item-ms", type=int, default=50, help="시간 모델: 항목당 ms")
    scan.add_argument("--json", action="store_true", help="기계가 읽는 JSON")
    scan.add_argument("--changes", action="store_true", help="바뀐 파일·심볼 목록도 출력")
    scan.add_argument("--hunks", action="store_true", help="--changes 와 함께 덩어리까지")

    rules = sub.add_parser("rules", help="규칙 목록")
    rules.add_argument("rule", nargs="?", default="")
    rules.add_argument("--json", action="store_true")

    return parser


def _payload(repo, change_set, risks, plan) -> dict:
    return {
        "repo": repo.summary(),
        "diff": {
            "files": len(change_set.views),
            "paths": [view.change.path for view in change_set.views],
            "added": sum(view.change.added_count() for view in change_set.views),
            "removed": sum(view.change.removed_count() for view in change_set.views),
        },
        "selection": {
            "files": len(change_set.selections),
            "items": change_set.selected_items(),
            "total_items": change_set.total_items(),
            "share": change_set.share(),
            "tests": [
                {
                    "path": sel.path,
                    "level": sel.level,
                    "reason": sel.reason,
                    "items": sel.items,
                    "mandatory": sel.mandatory,
                }
                for sel in sorted(change_set.selections.values(), key=lambda s: (s.level, -s.score))
            ],
        },
        "gaps": change_set.gaps,
        "risks": [
            {"rule": risk.rule, "severity": risk.severity, "title": risk.title,
             "detail": risk.detail, "where": risk.where}
            for risk in risks
        ],
        "plan": {
            "commands": plan.commands,
            "fallback": plan.fallback,
            "assumed": plan.assumed,
        },
        "fallback": change_set.fallback,
        "verdict": risk_module.verdict(risks, change_set.fallback),
        "limits": [
            "테스트가 실제로 통과하는지는 판정하지 않습니다",
            "시간은 모델입니다(항목 수 × 가정값)",
            "동적 import 뒤의 간선은 보이지 않습니다",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "rules":
        rows = risk_module.catalog(args.rule)
        if not rows:
            print(f"그런 규칙이 없습니다: {args.rule}")
            return 1
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        for row in rows:
            print(f"[{row['severity']}] {row['rule']} — {row['title']}\n    {row['doc']}")
        return 0

    if args.command != "scan":
        parser.print_help()
        return 1

    try:
        repo = load(args.repo)
    except FileNotFoundError as exc:
        print(f"⚠️ {exc}")
        return 1

    text = _read_diff(args)
    diff = diffparse.parse_or_empty(text)
    if not diff.changes:
        print("⚠️ diff 에서 바뀐 파일을 읽지 못했습니다 — unified diff 인지 확인하세요")
        return 1

    change_set = build_set(repo, diff)
    risks = risk_module.check(change_set)
    plan = build_plan(change_set, shards=args.shards, per_item_ms=args.per_item_ms)

    if args.json:
        print(json.dumps(_payload(repo, change_set, risks, plan), ensure_ascii=False, indent=2))
    else:
        if args.changes:
            print(change_lines(change_set, include_hunks=args.hunks))
            print()
        print(impact_report(change_set, risks, plan))
    tally = risk_module.counts(risks)
    return 2 if tally["치명"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
