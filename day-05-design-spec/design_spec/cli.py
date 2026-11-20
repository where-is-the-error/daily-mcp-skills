"""같은 일을 명령줄로 — 종료 코드가 계약이다.

    0  검사 통과 (치명·심각 없음)
    1  치명 또는 심각 위반이 있음 (audit·plan)
    2  파일·인자 오류

    design-spec read checkout.json --mode layout --depth 2
    design-spec palette checkout.json
    design-spec scale checkout.json --kind spacing
    design-spec audit checkout.json
    design-spec plan checkout.json
    design-spec design-md checkout.json --out DESIGN.md
    design-spec rules contrast-text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import load_and_audit, payload_json, render, render_plan
from .designmd import build_design_md
from .nodes import DesignError, load_design
from .rules import RULES, RULES_BY_ID
from .walk import build


def _source(args) -> str:
    return str(args.source)


def _cmd_read(args) -> int:
    design = load_design(_source(args), base_dir=Path.cwd())
    view = build(design, mode=args.mode, depth=args.depth, max_nodes=args.max_nodes, root_ref=args.ref)
    print(view.render(max_nodes=args.max_nodes))
    return 0


def _cmd_find(args) -> int:
    import re

    design = load_design(_source(args), base_dir=Path.cwd())
    view = build(design, max_nodes=100000)
    pattern = re.compile(args.regex, re.I) if args.regex else None
    hits = view.matches(args.text or "", pattern)
    if not hits:
        print(f'"{args.text or args.regex}" 에 해당하는 노드가 없습니다. (노드 {view.total_nodes}개)')
        return 0
    for entry in hits[: args.max_results]:
        node = entry.node
        size = node.describe_size()
        print(f"ref={node.ref} · {node.type.lower()} \"{node.name}\" · {size}")
        print(f"  경로: {' > '.join(node.path[-3:]) or 'document'}")
    if len(hits) > args.max_results:
        print(f"… {len(hits) - args.max_results}개 더")
    return 0


def _cmd_palette(args) -> int:
    audit = load_and_audit(_source(args))
    palette = audit.analysis.palette
    coverage = palette.token_coverage
    print(f"# {audit.design.title} · 색 {palette.distinct}종")
    if coverage is not None:
        print(f"- 토큰 커버리지 {coverage:.0%} (칠한 노드 {palette.styled_fills + palette.hardcoded_fills}개)")
    for use in palette.uses[: args.max_colors]:
        worst = "-" if use.contrast_worst is None else f"{use.contrast_worst:.2f}:1"
        print(f"{use.color.hex}  ×{use.count:<3} {use.role_label():<8} {worst:>7}  {use.area:>10.0f}px²")
    if palette.near_duplicates:
        print("\n## 거의 같은 색")
        for first, second, gap in palette.near_duplicates[:6]:
            print(f"- {first.color.hex} ↔ {second.color.hex} · 거리 {gap:.1f}")
    return 0


def _cmd_scale(args) -> int:
    audit = load_and_audit(_source(args))
    if args.kind == "spacing":
        report = audit.analysis.spacing
        print(f"# 간격 · 기준 {report.base:g}px ({report.base_share:.0%}) · {report.distinct}종" if report.base else "# 간격 · 기준 단위 없음")
        for value, count in report.values:
            print(f"{value:>6g}  {'█' * count}  ×{count}")
        for value, count in report.off_scale:
            nearest = round(value / report.base) * report.base if report.base else 0
            print(f"  스케일 밖: {value:g} ({count}곳) → {nearest:g}")
        return 0
    if args.kind == "type":
        report = audit.analysis.typography
        print(f"# 글자 · {report.distinct}단계 · 글꼴 {len(report.families)}종")
        for size, count in sorted(report.sizes, key=lambda item: -item[0]):
            print(f"{size:>6g}px  ×{count}")
        for lower, upper, ratio in report.close_steps:
            print(f"  붙어 있는 단계: {lower:g} → {upper:g} (×{ratio:.2f})")
        return 0
    report = audit.analysis.radii
    print(f"# 반경 · {report.distinct}종 · 알약형 {report.pill} · 직각 {report.square}")
    for value, count in report.values:
        print(f"{value:>6g}px  ×{count}")
    return 0


def _cmd_audit(args) -> int:
    audit = load_and_audit(_source(args), rule_ids=args.rules.split(",") if args.rules else None)
    if args.json:
        print(payload_json(audit))
    else:
        print(render(audit, max_per_rule=args.max_per_rule))
    heavy = any(finding.severity in ("치명", "심각") for finding in audit.findings)
    return 1 if heavy else 0


def _cmd_plan(args) -> int:
    audit = load_and_audit(_source(args))
    print(render_plan(audit, max_steps=args.max_steps))
    heavy = any(finding.severity in ("치명", "심각") for finding in audit.findings)
    return 1 if heavy else 0


def _cmd_design_md(args) -> int:
    audit = load_and_audit(_source(args))
    text = build_design_md(audit)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"💾 {args.out}")
    else:
        print(text)
    return 0


def _cmd_rules(args) -> int:
    if args.rule and args.rule not in RULES_BY_ID:
        print(f"⚠️ 없는 규칙: {args.rule}", file=sys.stderr)
        return 2
    chosen = [RULES_BY_ID[args.rule]] if args.rule else list(RULES)
    for rule in chosen:
        print(f"{rule.id:<22} {rule.severity:<3} {rule.title}")
        print(f"  근거: {rule.basis}")
        print(f"  판정: {rule.what}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="design-spec", description="디자인 파일에서 색·간격·글자를 세고 DESIGN.md 를 뽑는다")
    sub = parser.add_subparsers(dest="command", required=True)

    read = sub.add_parser("read", help="트리로 읽기")
    read.add_argument("source")
    read.add_argument("--mode", default="all", choices=["all", "layout", "text", "visual"])
    read.add_argument("--depth", type=int, default=0)
    read.add_argument("--max-nodes", type=int, default=120)
    read.add_argument("--ref", default="")
    read.set_defaults(func=_cmd_read)

    find = sub.add_parser("find", help="노드 찾기")
    find.add_argument("source")
    find.add_argument("--text", default="")
    find.add_argument("--regex", default="")
    find.add_argument("--max-results", type=int, default=10)
    find.set_defaults(func=_cmd_find)

    palette = sub.add_parser("palette", help="색 보고")
    palette.add_argument("source")
    palette.add_argument("--max-colors", type=int, default=14)
    palette.set_defaults(func=_cmd_palette)

    scale = sub.add_parser("scale", help="간격·글자·반경 단계")
    scale.add_argument("source")
    scale.add_argument("--kind", default="spacing", choices=["spacing", "type", "radius"])
    scale.set_defaults(func=_cmd_scale)

    audit = sub.add_parser("audit", help="검사 (치명·심각이면 exit 1)")
    audit.add_argument("source")
    audit.add_argument("--rules", default="")
    audit.add_argument("--max-per-rule", type=int, default=20)
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=_cmd_audit)

    plan = sub.add_parser("plan", help="고치기 순서")
    plan.add_argument("source")
    plan.add_argument("--max-steps", type=int, default=8)
    plan.set_defaults(func=_cmd_plan)

    design_md = sub.add_parser("design-md", help="DESIGN.md 만들기")
    design_md.add_argument("source")
    design_md.add_argument("--out", default="")
    design_md.set_defaults(func=_cmd_design_md)

    rules = sub.add_parser("rules", help="규칙 목록")
    rules.add_argument("rule", nargs="?", default="")
    rules.set_defaults(func=_cmd_rules)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (DesignError, FileNotFoundError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
