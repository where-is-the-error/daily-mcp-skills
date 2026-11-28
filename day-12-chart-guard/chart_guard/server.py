"""MCP 배선 — 열 툴.

    CHART_GUARD_ROOT=/path/to/specs python -m chart_guard.server

    {"mcpServers": {"chart-guard": {
      "command": "python", "args": ["-m", "chart_guard.server"],
      "env": {"CHART_GUARD_ROOT": "/path/to/specs"}}}}

읽기 전용이다. 스펙 파일을 고치지 않고, 차트를 그리지 않고, 어디로도 보내지 않는다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import alttext, check, compare as compare_module, fix, normalize, report, rules
from .store import STORE
from .types import Chart

LIMITS = report.LIMITS

OVERVIEW = """chart-guard — 차트를 올리기 전에, 그림이 숫자를 왜곡하는지 본다.

1. read_chart 로 스펙(JSON)을 읽습니다 → ref.
2. describe_chart 로 무엇이 무엇을 나타내는지 확인하고, distortion_report 로 축이 만드는 과장을 숫자로 봅니다.
3. chart_check 한 번으로 41종 규칙을 걸어 점수·판정·고치기 순서를 받습니다.
4. fix_plan 으로 고친 스펙(JSON)을, alt_text 로 125자 대체 텍스트와 데이터 표를 만듭니다.

재는 것: 축 하한이 만드는 화면 길이비와 실제 값비(과장 배수), 원 조각의 각도와 합,
로그축의 화면 거리, 크기 인코딩의 넓이, 색 대비·색각 이상 차이, 라벨 자리(폭 추정).
읽는 것: y축 min/zero/beginAtZero, 축 제목·단위, 제목·출처·alt, 팔레트.
읽지 않는 것: 차트 이미지의 픽셀, 데이터의 사실 여부, 색의 의도, 렌더링 결과.

태도
· 선언된 것만 계산한다. 하한이 선언되지 않았으면 '선언되지 않았다'고 출력하고 기본값으로 계산한 근거를 적는다.
· '문제가 아닌 때'(fine_when)를 규칙마다 적어 두고, 예외에 해당하면 경고하지 않는다.
· 점수를 올리려고 값을 지우지 않는다 — 고친 뒤 사라진 범주·값을 compare_charts 가 먼저 알린다.
· 스펙을 고치지 않고, 차트를 그리지 않고, 어디로도 보내지 않는다.

""" + LIMITS

mcp = MCPServer(
    name="chart-guard",
    title="chart-guard",
    version="0.1.0",
    instructions=(
        "차트 스펙을 검사합니다. read_chart 로 스펙을 읽고, chart_check 로 규칙 41종을 걸어 점수·판정·고치기 순서를 받으세요. "
        "축이 숫자를 얼마나 과장하는지는 distortion_report 가 배수로 계산합니다. "
        "fix_plan 은 고친 스펙(JSON)을, alt_text 는 대체 텍스트와 데이터 표를 만듭니다. "
        "차트 이미지는 읽지 못하고 스펙만 읽습니다. 스펙을 고치거나 차트를 그리지 않습니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("CHART_GUARD_ROOT")
    return Path(root) if root else None


def _path(value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    root = _root()
    return str(root / path) if root else str(path)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _read(spec: str = "", path: str = "") -> tuple[Chart, str]:
    if spec.strip():
        chart = normalize.normalize(spec)
    elif path.strip():
        chart = normalize.normalize(Path(_path(path)).read_text(encoding="utf-8"))
    else:
        raise normalize.SpecError("spec(JSON 문자열) 또는 path 가 필요합니다.")
    return chart, STORE.add_chart(chart)


def _resolve(chart_ref: str = "", spec: str = "", path: str = "") -> tuple[Chart, str]:
    if chart_ref:
        return STORE.chart(chart_ref), chart_ref
    return _read(spec, path)


@mcp.tool()
def read_chart(spec: str = "", path: str = "") -> str:
    """차트 스펙을 읽어 사실(형식·범주·계열·축·값 범위·색)을 돌려준다.

    spec: JSON 문자열 (Vega-Lite · Chart.js · guard JSON).
    path: 스펙 파일 경로 (CHART_GUARD_ROOT 기준 상대경로 가능).
    이 툴은 판정하지 않는다 — 읽은 것만 보여주고 ref 를 준다.
    """
    try:
        chart, ref = _read(spec, path)
        lines = report.chart_lines(chart)
        if chart.warnings:
            lines.append("")
            lines.append("읽는 중 남긴 사실:")
            lines.extend("  · " + warning for warning in chart.warnings)
        lines.append("")
        lines.append(LIMITS)
        lines.append(f"차트 ref: {ref}")
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def describe_chart(chart_ref: str) -> str:
    """판정 전에 무엇이 무엇을 나타내는지 적는다 — 인코딩·계열·메시지, 그리고 한 줄 요약(alt).

    chart_ref: read_chart 가 돌려준 ref.
    """
    try:
        chart = STORE.chart(chart_ref)
        lines = [f"설명 — {chart.describe_type()}", ""]
        lines.append(f"  무엇을: x '{chart.x.title or '(없음)'}' · y '{chart.y.title or '(없음)'}'")
        if chart.series_count() > 1:
            lines.append(f"  나눈 기준: 계열 {chart.series_count()}개 — " + ", ".join(s.name or f"계열 {i + 1}" for i, s in enumerate(chart.series) if not s.hidden)[:200])
        else:
            lines.append("  나눈 기준: 없음(한 계열)")
        lines.append(f"  값: {len(chart.visible_numbers())}개 · 범주 {len(chart.categories)}개")
        lines.append(f"  형식: {chart.describe_type()}" + (" · 누적" if chart.stacked else "") + (" · 3D" if chart.three_d else ""))
        lines.append("")
        lines.append("한 줄 요약(alt 후보)")
        lines.append("  " + alttext.headline(chart))
        if chart.warnings:
            lines.append("")
            lines.append("읽는 중 남긴 사실:")
            lines.extend("  · " + warning for warning in chart.warnings)
        lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def distortion_report(chart_ref: str) -> str:
    """축·각도가 숫자를 얼마나 과장하는지 계산한다 — 화면 비율 vs 실제 값 비율.

    chart_ref: read_chart 가 돌려준 ref. 규칙 판정 없이 계산만 한다.
    """
    try:
        chart = STORE.chart(chart_ref)
        lines = [f"왜곡 계산 — {chart.describe_type()}", ""]
        lines.extend(report.distortion_lines(chart))
        lines.append("")
        lines.append("계산은 스펙의 선언(축 min·max·zero)과 값으로만 합니다. 렌더링 결과를 재지 않습니다.")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_problems(chart_ref: str, severity: str = "all") -> str:
    """41종 규칙을 걸어 걸린 것만 보여준다 (점수 없이).

    chart_ref: read_chart 가 돌려준 ref. severity: all | block | warn | info.
    """
    try:
        chart = STORE.chart(chart_ref)
        result = check.run(chart)
        findings = result.findings
        if severity in {"block", "warn", "info"}:
            findings = [f for f in findings if f.severity == severity]
        scoped = check.score(findings, chart=chart, skipped=result.skipped)
        lines = [
            f"문제 — {chart.title or chart.describe_type()} (규칙 {rules.counts()['total']}종 검사)",
            "",
            f"  막음 {len(result.blocking())} · 주의 {len(result.warnings())} · 참고 {len(result.infos())}",
            "",
        ]
        lines.extend(report.finding_lines(scoped))
        lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def chart_check(chart_ref: str = "", spec: str = "", path: str = "") -> str:
    """한 번에 검사 — 점수·판정·고치기 순서·고치면 달라지는 숫자.

    chart_ref 또는 spec/path 중 하나. 스펙을 고치지 않는다 — 고친 스펙은 fix_plan 이 문자열로 만든다.
    """
    try:
        if not chart_ref and not spec and not path:
            return "⚠️ chart_ref 또는 spec/path 가 필요합니다."
        chart, _ = _resolve(chart_ref, spec, path)
        result = check.run(chart)
        ref = STORE.add_report(result)
        return report.check_report(result).replace("{ref}", ref)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def fix_plan(chart_ref: str, include_spec: bool = True) -> str:
    """고치기 계획 — 순서, 항목별 문장, 고친 guard JSON 스펙.

    chart_ref: read_chart 가 돌려준 ref. 파일에 쓰지 않는다.
    """
    try:
        chart = STORE.chart(chart_ref)
        result = check.run(chart)
        lines = [f"고치기 — {chart.title or chart.describe_type()}", ""]
        lines.append(check.summary_line(result))
        lines.append("")
        for step in fix.FIX_ORDER:
            lines.append(step)
        lines.append("")
        if result.findings:
            lines.append("항목")
            for index, finding in enumerate(result.ordered(), start=1):
                label = {"block": "막음", "warn": "주의", "info": "참고"}[finding.severity]
                lines.append(f"  {index}. [{label}] {finding.title}")
                lines.append(f"     {finding.fix}")
            lines.append("")
            changed = fix.explain_difference(chart)
            if changed:
                lines.append("고치면 이렇게 바뀝니다")
                lines.extend("  · " + line for line in changed)
                lines.append("")
        else:
            lines.append("고칠 것이 없습니다.")
            lines.append("")
        if include_spec:
            lines.append("고친 스펙 (guard JSON)")
            lines.append("")
            lines.append(fix.spec_json(chart))
            lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def alt_text(chart_ref: str) -> str:
    """대체 텍스트(125자 alt + 긴 설명)와 데이터 표를 만든다.

    chart_ref: read_chart 가 돌려준 ref.
    """
    try:
        chart = STORE.chart(chart_ref)
        return alttext.report(chart)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_charts(before_ref: str, after_ref: str) -> str:
    """두 차트(고치기 전·후)를 비교한다 — 점수 변화, 고쳐진 규칙, 남은 규칙, 잃은 범주·값.

    before_ref · after_ref: read_chart 가 돌려준 ref.
    """
    try:
        before_chart = STORE.chart(before_ref)
        after_chart = STORE.chart(after_ref)
        before = check.run(before_chart)
        after = check.run(after_chart)
        return report.compare_lines(compare_module.compare(before, after))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog(rule: str = "") -> str:
    """규칙 목록과 각 규칙이 무엇을 보고 언제 문제가 아닌지. rule 을 주면 하나만.

    rule: 규칙 id (예: bar-truncated-baseline, rainbow-palette).
    """
    return report.rule_lines(rule)


@mcp.tool()
def overview() -> str:
    """이 서버가 무엇을 하고 무엇을 판정하지 않는지."""
    return OVERVIEW


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="chart-guard MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="스펙 기준 디렉터리 (CHART_GUARD_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["CHART_GUARD_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
