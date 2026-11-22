"""CLI — plan 하나를 여러 각도로 본다.

    plan-guard summary  plan.json
    plan-guard risk     plan.json --fail-on 치명
    plan-guard changes  plan.json --kind replace
    plan-guard diff     plan.json aws_db_instance.main
    plan-guard order    plan.json
    plan-guard rollback plan.json
    plan-guard compare  proposal.json fixed.json
    plan-guard redact   plan.json -o plan.share.json
    plan-guard rules

종료 코드: 0 정상, 1 입력 오류, 2 `--fail-on` 기준에 걸림(CI 게이트).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from . import risks
from .compare import compare
from .plan import PlanError, load_plan
from .redact import redact_document, to_json


def _load(path: str, root: Path | None):
    return load_plan(path, base_dir=root)


def cmd_summary(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.summary(plan))
    return 0


def cmd_risk(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.risk(plan, severity=args.severity, max_items=args.max_items))
    if args.fail_on:
        threshold = args.fail_on.strip()
        if threshold not in risks.SEVERITY_ORDER:
            print("--fail-on 은 치명 · 심각 · 보통 · 참고 중 하나입니다.", file=sys.stderr)
            return 1
        limit = risks.SEVERITY_ORDER[threshold]
        if any(risks.SEVERITY_ORDER[f.severity] <= limit for f in risks.findings(plan)):
            print(f"\n게이트: {threshold} 이상이 있어 종료 코드 2 로 끝냅니다.", file=sys.stderr)
            return 2
    return 0


def cmd_changes(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.changes(plan, kind_filter=args.kind, max_items=args.max_items))
    return 0


def cmd_diff(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.diff(plan, args.address, max_items=args.max_items))
    return 0


def cmd_order(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.order(plan))
    return 0


def cmd_rollback(args, root: Path | None) -> int:
    plan = _load(args.plan, root)
    print(report.rollback(plan))
    return 0


def cmd_compare(args, root: Path | None) -> int:
    before = _load(args.before, root)
    after = _load(args.after, root)
    print(compare(before, after).render(max_items=args.max_items))
    return 0


def cmd_redact(args, root: Path | None) -> int:
    import json

    path = Path(args.plan)
    if not path.is_absolute() and root is not None:
        path = root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    redacted, masked = redact_document(data)
    text = to_json(redacted)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{args.out} · 민감값 {masked}개를 «민감» 으로 가렸습니다.")
    else:
        print(text)
    return 0


def cmd_rules(args, root: Path | None) -> int:
    print("# 규칙 " + str(len(risks.CATALOG)) + "종")
    for rule in risks.CATALOG:
        print(f"- {rule.severity} · {rule.rule_id} — {rule.title}")
        print(f"    {rule.why}")
    print("\n한계: plan 에 적힌 값만 봅니다. 비용·실제 데이터 크기·apply 시점 결과는 판정하지 않습니다.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan-guard", description="terraform plan JSON 을 apply 전에 읽는다")
    parser.add_argument("--root", default=None, help="plan 파일을 찾을 기준 디렉터리")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("summary", help="한 화면 요약")
    p.add_argument("plan")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("risk", help="apply 전에 봐야 할 것")
    p.add_argument("plan")
    p.add_argument("--severity", default="", help="치명 · 심각 · 보통 · 참고 (그 이상만)")
    p.add_argument("--max-items", type=int, default=report.MAX_LINES)
    p.add_argument("--fail-on", default="", help="이 등급 이상이면 종료 코드 2 (CI 게이트)")
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("changes", help="바뀌는 리소스 목록")
    p.add_argument("plan")
    p.add_argument("--kind", default="", help="create · update · replace · delete 또는 리소스 타입")
    p.add_argument("--max-items", type=int, default=30)
    p.set_defaults(func=cmd_changes)

    p = sub.add_parser("diff", help="리소스 하나의 속성 diff")
    p.add_argument("plan")
    p.add_argument("address")
    p.add_argument("--max-items", type=int, default=report.MAX_LINES)
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("order", help="적용·삭제 순서와 참조")
    p.add_argument("plan")
    p.set_defaults(func=cmd_order)

    p = sub.add_parser("rollback", help="되돌리기 계획")
    p.add_argument("plan")
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("compare", help="plan 두 개 비교")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--max-items", type=int, default=12)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("redact", help="민감값을 가린 공유용 사본")
    p.add_argument("plan")
    p.add_argument("-o", "--out", default="")
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("rules", help="규칙 목록과 한계")
    p.set_defaults(func=cmd_rules)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else None
    try:
        return int(args.func(args, root))
    except PlanError as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"⚠️ 파일을 찾을 수 없습니다: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
