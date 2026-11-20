"""명령줄 — MCP 클라이언트 없이도 같은 검사를 돌린다 (CI·훅에서 쓰기).

    a11y-lens snapshot index.html
    a11y-lens audit  public/            # 폴더면 사이트 검사
    a11y-lens plan   index.html
    a11y-lens verify index.html --save  # 고치기 전 기준선
    a11y-lens verify index.html         # 고친 뒤 비교 (새 위반이 있으면 exit 1)
    a11y-lens rules

종료 코드: audit — 치명·심각이 있으면 1, 없으면 0
          verify — 새로 생긴 위반이 있으면 1, 없으면 0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import store
from .audit import (
    audit_page,
    audit_site,
    load_document,
    payload_json,
    render_page,
    render_plan,
    render_site,
)
from .rules import IMPACT_LABEL, IMPACT_ORDER, RULES, rule_by_id
from .snapshot import build


def _audit_page(source: str, rules: str, max_per_rule: int):
    ids = [part.strip() for part in rules.replace(",", " ").split() if part.strip()]
    return audit_page(source, rule_ids=ids, max_per_rule=max_per_rule)


def cmd_snapshot(args) -> int:
    doc = load_document(args.source)
    view = build(doc, depth=args.depth, max_nodes=args.max_nodes, root_ref=args.ref)
    print(view.render(show_source=not args.no_source))
    return 0


def cmd_audit(args) -> int:
    target = Path(args.source)
    if target.is_dir():
        site = audit_site(target, pattern=args.pattern, max_pages=args.max_pages)
        if args.json:
            print(json.dumps(site.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_site(site, max_groups=args.max_groups))
        counts = site.counts()
        return 0 if counts["critical"] == 0 and counts["serious"] == 0 else 1
    audit = _audit_page(args.source, args.rules, args.max_per_rule)
    if args.json:
        print(payload_json(audit))
    else:
        print(render_page(audit, max_per_rule=args.max_per_rule))
    return 0 if not any(v.rule.impact in {"critical", "serious"} for v in audit.violations) else 1


def cmd_plan(args) -> int:
    audit = _audit_page(args.source, args.rules, args.max_per_rule)
    if not audit.violations:
        print(f"✅ {audit.path}: 정적으로 판정 가능한 위반이 없습니다. 점수 {audit.score}/100.")
        return 0
    print(render_plan(audit, max_steps=args.max_steps))
    return 0


def cmd_verify(args) -> int:
    audit = _audit_page(args.source, args.rules, args.max_per_rule)
    name = args.baseline or Path(args.source).stem or "baseline"
    if args.save:
        path = store.save(name, audit)
        print(f"💾 기준선 저장: {path}")
        print(f"   {audit.path} · 위반 {len(audit.violations)}건 · 점수 {audit.score}/100")
        return 0
    data = store.load(name)
    result = store.compare(data, audit)
    if args.json:
        print(
            json.dumps(
                {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(store.render_compare(result, data, title=audit.path))
    return 0 if result["ok"] else 1


def cmd_rules(args) -> int:
    if args.id:
        rule = rule_by_id(args.id)
        if rule is None:
            print(f"⚠️ 그런 규칙이 없습니다: {args.id}")
            return 2
        print(f"{rule.id} — {rule.title}")
        print(f"  WCAG {rule.wcag} ({rule.level}) · {IMPACT_LABEL.get(rule.impact, rule.impact)}")
        print(f"  왜: {rule.why}")
        print(f"  고치기: {rule.fix}")
        return 0
    rows = sorted(RULES, key=lambda r: (IMPACT_ORDER.get(r.impact, 9), r.wcag, r.id))
    print(f"규칙 {len(rows)}종")
    for rule in rows:
        print(f"  {rule.id:<18} WCAG {rule.wcag:<5} {rule.level:<3} {IMPACT_LABEL.get(rule.impact, rule.impact):<3} {rule.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a11y-lens", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="접근성 트리 스냅샷 (ref·줄 번호)")
    snap.add_argument("source")
    snap.add_argument("--depth", type=int, default=0)
    snap.add_argument("--max-nodes", type=int, default=200, dest="max_nodes")
    snap.add_argument("--ref", default="")
    snap.add_argument("--no-source", action="store_true", dest="no_source")
    snap.set_defaults(func=cmd_snapshot)

    audit = sub.add_parser("audit", help="페이지 또는 폴더 검사")
    audit.add_argument("source")
    audit.add_argument("--rules", default="")
    audit.add_argument("--max-per-rule", type=int, default=30, dest="max_per_rule")
    audit.add_argument("--max-pages", type=int, default=50, dest="max_pages")
    audit.add_argument("--max-groups", type=int, default=15, dest="max_groups")
    audit.add_argument("--pattern", default="**/*.html")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=cmd_audit)

    plan = sub.add_parser("plan", help="고치기 순서")
    plan.add_argument("source")
    plan.add_argument("--rules", default="")
    plan.add_argument("--max-per-rule", type=int, default=30, dest="max_per_rule")
    plan.add_argument("--max-steps", type=int, default=8, dest="max_steps")
    plan.set_defaults(func=cmd_plan)

    verify = sub.add_parser("verify", help="기준선 저장/비교")
    verify.add_argument("source")
    verify.add_argument("--baseline", default="")
    verify.add_argument("--save", action="store_true")
    verify.add_argument("--rules", default="")
    verify.add_argument("--max-per-rule", type=int, default=30, dest="max_per_rule")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    rules = sub.add_parser("rules", help="규칙 목록 (id 하나를 주면 자세히)")
    rules.add_argument("id", nargs="?", default="")
    rules.set_defaults(func=cmd_rules)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
