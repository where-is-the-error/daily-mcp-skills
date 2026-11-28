"""CLI — MCP 없이 같은 검사를 돌린다.

    chart-guard check examples/before.json
    chart-guard fix examples/before.json > fixed.json
    chart-guard alt examples/before.json
    chart-guard compare examples/before.json examples/after.json
    chart-guard rules | chart-guard rules bar-truncated-baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import alttext, check, compare as compare_module, fix, normalize, report, rules
from .store import STORE
from .types import Chart

EXIT = {"pass": 0, "warn": 1, "hold": 2}


def _load(path: str) -> Chart:
    text = Path(path).read_text(encoding="utf-8")
    return normalize.normalize(text)


def _print(text: str) -> None:
    print(text)


def cmd_read(args: argparse.Namespace) -> int:
    chart = _load(args.spec)
    lines = report.chart_lines(chart)
    lines.append("")
    lines.append(report.LIMITS)
    _print("\n".join(lines))
    return 0


def cmd_distortion(args: argparse.Namespace) -> int:
    chart = _load(args.spec)
    lines = [f"왜곡 계산 — {chart.describe_type()}", ""]
    lines.extend(report.distortion_lines(chart))
    lines.append("")
    lines.append(report.LIMITS)
    _print("\n".join(lines))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    chart = _load(args.spec)
    result = check.run(chart)
    if args.json:
        payload = {
            "score": result.score,
            "verdict": result.verdict,
            "findings": [
                {"rule": f.rule_id, "severity": f.severity, "evidence": f.evidence, "fix": f.fix}
                for f in result.ordered()
            ],
            "skipped": result.skipped,
        }
        _print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        text = report.check_report(result).replace("{ref}", "(cli)")
        _print(text)
    return EXIT.get(result.verdict, 1)


def cmd_fix(args: argparse.Namespace) -> int:
    chart = _load(args.spec)
    _print(fix.spec_json(chart))
    return 0


def cmd_alt(args: argparse.Namespace) -> int:
    chart = _load(args.spec)
    _print(alttext.report(chart))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    before_chart = _load(args.before)
    after_chart = _load(args.after)
    before = check.run(before_chart)
    after = check.run(after_chart)
    _print(report.compare_lines(compare_module.compare(before, after)))
    return EXIT.get(after.verdict, 1)


def cmd_rules(args: argparse.Namespace) -> int:
    _print(report.rule_lines(args.rule or ""))
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    counts = rules.counts()
    severities = rules.by_severity()
    _print(
        "\n".join(
            [
                "chart-guard — 차트를 올리기 전에, 축·형식·색·글이 숫자를 왜곡하는지 본다.",
                "",
                f"규칙 {counts['total']}종 (막음 {severities['block']} · 주의 {severities['warn']} · 참고 {severities['info']})",
                "읽는 것: Vega-Lite · Chart.js · guard JSON 의 선언과 값",
                "계산하는 것: 축 하한이 만드는 화면 비율, 원 조각의 각도, 로그축 거리, 크기 인코딩의 넓이",
                "만드는 것: 고친 스펙(JSON) · 125자 대체 텍스트 · 데이터 표",
                "",
                report.LIMITS,
            ]
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chart-guard", description="차트를 올리기 전에 재는 검사기")
    sub = parser.add_subparsers(dest="command")

    for name, handler, help_text in (
        ("read", cmd_read, "차트 스펙을 읽어 사실을 보여준다"),
        ("distortion", cmd_distortion, "축이 만드는 과장을 숫자로 보여준다"),
        ("check", cmd_check, "규칙 41종으로 검사하고 점수·판정을 낸다"),
        ("fix", cmd_fix, "고친 스펙(guard JSON)을 출력한다"),
        ("alt", cmd_alt, "대체 텍스트와 데이터 표를 만든다"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("spec")
        if name == "check":
            cmd.add_argument("--json", action="store_true")
        cmd.set_defaults(func=handler)

    compare_parser = sub.add_parser("compare", help="두 검사 결과를 비교한다")
    compare_parser.add_argument("before")
    compare_parser.add_argument("after")
    compare_parser.set_defaults(func=cmd_compare)

    rules_parser = sub.add_parser("rules", help="규칙 목록")
    rules_parser.add_argument("rule", nargs="?", default="")
    rules_parser.set_defaults(func=cmd_rules)

    overview_parser = sub.add_parser("overview", help="이 도구가 무엇을 하고 무엇을 안 하는지")
    overview_parser.set_defaults(func=cmd_overview)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (normalize.SpecError, OSError, KeyError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())


_ = STORE  # CLI 는 상태를 남기지 않는다 — store 는 MCP 쪽에서만 쓴다
