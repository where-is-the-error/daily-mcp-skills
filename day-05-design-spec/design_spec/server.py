"""MCP 배선 — 일곱 툴: 트리 읽기 · 찾기 · 색/간격/글자 보고 · 검사 · DESIGN.md.

stdio 로 실행:

    DESIGN_SPEC_ROOT=/path/to/designs python -m design_spec.server

MCP 클라이언트 설정:

    {"mcpServers": {"design-spec": {
      "command": "python", "args": ["-m", "design_spec.server"],
      "env": {"DESIGN_SPEC_ROOT": "/Users/me/project/designs"}}}}
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .audit import audit_design as _audit_design
from .audit import load_and_audit, payload_json, render, render_plan
from .color import describe
from .designmd import build_design_md
from .palette import near_duplicate_pairs, role_label_for
from .nodes import load_design
from .rules import RULES, SEVERITY_ORDER
from .tokens import trim_to_tokens
from .walk import build

DEFAULT_BUDGET = 1400

mcp = MCPServer(
    name="design-spec",
    title="design-spec",
    version="0.1.0",
    instructions=(
        "디자인 파일(Figma REST 응답 모양의 JSON)을 읽어 색·간격·글자를 세고, 위반을 짚고, "
        "DESIGN.md 를 만들어 주는 서버입니다. read_design 으로 구조를 보고, "
        "audit_design 으로 점수와 고칠 순서를 받고, write_design_md 로 디자인 시스템 문서를 뽑으세요. "
        "그라디언트·이미지 위 글자의 대비와 줄 높이가 '자동'인 값은 판정하지 않습니다."
    ),
)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _budget(value: int | None) -> int:
    return DEFAULT_BUDGET if value is None else max(1, int(value))


def _finish(text: str, max_tokens: int) -> str:
    trimmed, cut = trim_to_tokens(text, max_tokens)
    if cut:
        trimmed += f"\n\n… ({max_tokens} 토큰에서 잘랐습니다)"
    return trimmed


def _root() -> Path | None:
    root = os.environ.get("DESIGN_SPEC_ROOT")
    return Path(root) if root else None


def _rule_ids(spec: str) -> list[str]:
    if not spec or not spec.strip():
        return []
    return [part.strip() for part in re.split(r"[,\s]+", spec) if part.strip()]


@mcp.tool()
def read_design(
    source: str,
    mode: str = "all",
    depth: int = 0,
    max_nodes: int = 120,
    ref: str = "",
    max_tokens: int = DEFAULT_BUDGET,
) -> str:
    """디자인 파일을 읽을 수 있는 트리로 보여 준다 — ref·크기·색·글자, 반복 스타일은 표로.

    source: 파일 경로 또는 Figma 응답 JSON 문자열.
    mode: all | layout(위치·간격만) | text(글자만) | visual(색·모양만).
    depth=0 은 무제한, ref="e14" 면 그 노드 하위만. `ref` 는 문서 순서로 고정된다.
    """
    try:
        design = load_design(source, base_dir=_root())
        view = build(design, mode=mode, depth=int(depth), max_nodes=int(max_nodes), root_ref=ref)
        return _finish(view.render(max_nodes=int(max_nodes)), _budget(max_tokens))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_in_design(source: str, text: str = "", regex: str = "", max_results: int = 10) -> str:
    """트리 안에서 이름·글자·타입으로 노드를 찾는다 — 전체를 읽지 않고 위치만 볼 때."""
    if not text and not regex:
        return "⚠️ text 또는 regex 중 하나를 주세요."
    try:
        pattern = re.compile(regex, re.I) if regex else None
    except re.error as exc:
        return _fail(ValueError(f"정규식이 올바르지 않습니다: {exc}"))
    try:
        design = load_design(source, base_dir=_root())
        view = build(design, max_nodes=100000)
    except Exception as exc:
        return _fail(exc)

    hits = view.matches(text, pattern)
    needle = text or regex
    if not hits:
        return f'"{needle}" 에 해당하는 노드가 없습니다. (노드 {view.total_nodes}개를 뒤졌습니다)'
    lines = [f"# {len(hits)}개 중 {min(len(hits), max(1, int(max_results)))}개"]
    for entry in hits[: max(1, int(max_results))]:
        node = entry.node
        size = node.describe_size()
        extra = f' “{node.characters.strip()[:30]}”' if node.characters.strip() else ""
        lines.append(f"- ref={node.ref} · {node.type.lower()} \"{node.name}\" · {size}{extra}")
        lines.append(f"  경로: {' > '.join(node.path[-3:]) or 'document'}")
    if len(hits) > max_results:
        lines.append(f"# … {len(hits) - max_results}개 더 (max_results 로 늘릴 수 있습니다)")
    return "\n".join(lines)


@mcp.tool()
def palette_report(source: str, tolerance: float = 10.0, max_colors: int = 14) -> str:
    """색 보고 — 무슨 색이 얼마나, 어떤 역할로, 무엇과 거의 같은지. 글자 대비 최악값까지."""
    try:
        audit = load_and_audit(source)
    except Exception as exc:
        return _fail(exc)
    palette = audit.analysis.palette
    coverage = palette.token_coverage
    lines = [
        f"# {audit.design.title} · 색 {palette.distinct}종",
        (
            f"- 칠한 노드 {palette.styled_fills + palette.hardcoded_fills}개 중 "
            f"색 스타일(토큰)을 쓰는 것 {palette.styled_fills}개"
            + (f" — 커버리지 {coverage:.0%}" if coverage is not None else "")
        ),
        "",
        "| 이름 | 값 | 역할 | 곳 | 면적 | 최악 대비 |",
        "|---|---|---|---|---|---|",
    ]
    role_korean = {
        "surface": "배경·카드", "text": "본문 글자", "muted": "보조 글자",
        "primary": "주요 동작", "border": "선·구분",
    }
    for use in palette.uses[: max(1, int(max_colors))]:
        role = role_label_for(palette, use.color)
        worst = "—" if use.contrast_worst is None else f"{use.contrast_worst:.2f}:1"
        lines.append(
            f"| {describe(use.color)} | `{use.color.hex}` | {role_korean.get(role, role)} | "
            f"{use.count} | {use.area:.0f} | {worst} |"
        )
    if palette.distinct > max_colors:
        lines.append(f"| … | {palette.distinct - max_colors}종 더 | | | | |")

    pairs = near_duplicate_pairs(palette.uses, float(tolerance))
    lines.append("")
    if pairs:
        lines.append(f"## 거의 같은 색 (거리 ≤ {tolerance:g})")
        for first, second, gap in pairs[:6]:
            lines.append(
                f"- `{first.color.hex}` ↔ `{second.color.hex}` · 거리 {gap:.1f} · "
                f"{first.count}곳 / {second.count}곳"
            )
    else:
        lines.append(f"## 거의 같은 색 없음 (거리 ≤ {tolerance:g})")

    if palette.roles:
        lines.append("")
        lines.append("## 역할(추정)")
        for role, color in palette.roles.items():
            lines.append(f"- {role_korean.get(role, role)}: `{color.hex}` {describe(color)}")
    if palette.text_over_image:
        lines += ["", f"> 그라디언트·이미지 위 글자 {len(palette.text_over_image)}곳은 대비를 계산하지 않았습니다."]
    return "\n".join(lines)


@mcp.tool()
def scale_report(source: str, kind: str = "spacing") -> str:
    """간격·글자·반경의 '단계'를 본다 — 기준 단위, 분포, 스케일 밖 값.

    kind: spacing | type | radius
    """
    try:
        audit = load_and_audit(source)
    except Exception as exc:
        return _fail(exc)
    kind = (kind or "spacing").lower()

    if kind == "spacing":
        report = audit.analysis.spacing
        lines = [f"# 간격 · {audit.design.title}"]
        if report.base:
            lines.append(f"- 기준 단위 **{report.base:g}px** — 값 {report.total}개 중 {report.base_share:.0%}가 배수")
        else:
            lines.append("- 기준 단위를 찾지 못했습니다 (값이 제각각이거나 간격 정보가 없음)")
        lines += ["", "| 값 | 곳 | 막대 |", "|---|---|---|"]
        peak = max((count for _, count in report.values), default=1)
        off = {value for value, _ in report.off_scale}
        for value, count in report.values[:16]:
            bar = "█" * max(1, round(count / peak * 12))
            flag = " ← 스케일 밖" if value in off else ""
            lines.append(f"| {value:g} | {count} | {bar}{flag} |")
        if report.padding_values:
            lines.append("")
            lines.append("여백(padding): " + ", ".join(f"{value:g}×{count}" for value, count in report.padding_values[:10]))
        if report.off_scale:
            lines.append("")
            lines.append("## 스케일 밖")
            for value, count in report.off_scale:
                nearest = round(value / report.base) * report.base if report.base else None
                lines.append(f"- {value:g}px ({count}곳) → {nearest:g}px")
        return "\n".join(lines)

    if kind in ("type", "typography", "text"):
        report = audit.analysis.typography
        lines = [f"# 글자 · {audit.design.title}"]
        lines.append(f"- 크기 {report.distinct}단계 · 글꼴 {len(report.families)}종 · 굵기 {len(report.weights)}종")
        lines += ["", "| 크기 | 곳 |", "|---|---|"]
        for size, count in sorted(report.sizes, key=lambda item: -item[0]):
            lines.append(f"| {size:g}px | {count} |")
        if report.steps:
            lines.append("")
            lines.append("단계 간격: " + ", ".join(f"{lower:g}→{upper:g} (×{ratio:.2f})" for lower, upper, ratio in report.steps))
        if report.close_steps:
            lines.append("- 붙어 있는 단계: " + ", ".join(f"{lower:g}/{upper:g}" for lower, upper, _ in report.close_steps))
        if report.one_offs:
            lines.append("- 한 번만 쓰인 크기: " + ", ".join(f"{size:g}px" for size in report.one_offs))
        if report.families:
            lines.append("- 글꼴: " + ", ".join(f"{family or '(이름 없음)'}×{count}" for family, count in report.families))
        if report.weights:
            lines.append("- 굵기: " + ", ".join(f"{weight}×{count}" for weight, count in report.weights))
        if report.no_line_height:
            lines.append(f"- 줄 높이가 '자동'인 글자 {report.no_line_height}곳 (판정하지 않음)")
        return "\n".join(lines)

    if kind in ("radius", "radii"):
        report = audit.analysis.radii
        lines = [f"# 반경 · {audit.design.title}", f"- {report.distinct}종류 · 알약형 {report.pill} · 직각 {report.square}"]
        lines += ["", "| 반경 | 곳 |", "|---|---|"]
        for value, count in report.values:
            lines.append(f"| {value:g}px | {count} |")
        return "\n".join(lines)

    return "⚠️ kind 는 spacing · type · radius 중 하나여야 합니다."


@mcp.tool()
def audit_design(
    source: str,
    rules: str = "",
    max_per_rule: int = 20,
    min_touch: float = 44.0,
    format: str = "markdown",
) -> str:
    """한 파일을 규칙 17종으로 검사한다 — 점수·위반·고치는 값(제안 색까지).

    rules: 쉼표로 규칙 id 만 (예: "contrast-text,touch-target"). 비우면 전체.
    min_touch: 누르는 영역 최소 크기 (iOS 44 · Android 48).
    format="json" 이면 기계가 읽는 형태.
    """
    try:
        audit = load_and_audit(source, rule_ids=_rule_ids(rules), min_touch=float(min_touch))
    except Exception as exc:
        return _fail(exc)
    if format.lower() == "json":
        return payload_json(audit)
    return render(audit, max_per_rule=max(0, int(max_per_rule)))


@mcp.tool()
def fix_order(source: str, max_steps: int = 8) -> str:
    """고치는 순서 — 무거운 것부터, 같은 등급이면 여러 번 나온 것부터. 단계마다 첫 위치까지."""
    try:
        audit = load_and_audit(source)
    except Exception as exc:
        return _fail(exc)
    return render_plan(audit, max_steps=int(max_steps))


@mcp.tool()
def write_design_md(source: str, save_to: str = "", max_tokens: int = 1800) -> str:
    """DESIGN.md 를 만든다 — Stitch `design-md` 스킬의 다섯 칸 구조로.

    save_to: 저장할 경로(비우면 문서만 돌려줌). DESIGN_SPEC_ROOT 안이어야 합니다.
    """
    try:
        audit = load_and_audit(source)
        text = build_design_md(audit)
    except Exception as exc:
        return _fail(exc)
    if save_to.strip():
        try:
            root = _root() or Path.cwd()
            target = Path(save_to)
            if not target.is_absolute():
                target = root / save_to
            target = target.resolve()
            base = root.resolve()
            if base not in target.parents and target != base:
                return f"⚠️ DESIGN_SPEC_ROOT 밖에는 쓰지 않습니다: {target}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            head = f"💾 {target}\n\n"
        except Exception as exc:
            return _fail(exc)
    else:
        head = ""
    return head + _finish(text, _budget(max_tokens))


@mcp.tool()
def overview(max_tokens: int = 900) -> str:
    """이 서버가 무엇을 판정하고 무엇을 판정하지 않는지 — 규칙 17종과 한계."""
    rows = [f"| `{rule.id}` | {rule.title} | {rule.basis} | {rule.severity} |" for rule in RULES]
    text = "\n".join(
        [
            "# design-spec — 디자인 파일에서 색·간격·글자를 세고 DESIGN.md 를 뽑는다",
            "",
            "**여덟 툴**: `read_design` · `find_in_design` · `palette_report` · `scale_report` · "
            "`audit_design` · `fix_order` · `write_design_md` · `overview`",
            "",
            "## 왜 디자인 파일에서",
            "구현이 끝난 화면을 재는 도구는 많지만, **디자인 단계**에서 색이 몇 종인지·간격이",
            "스케일을 벗어났는지·글자 단계가 몇 개인지는 아무도 세어 주지 않습니다. 여기서 세면",
            "코드를 한 줄도 안 쓰고 고칠 수 있습니다.",
            "",
            f"## 판정하는 것 (규칙 {len(RULES)}종)",
            "| 규칙 | 내용 | 근거 | 등급 |",
            "|---|---|---|---|",
            *rows,
            "",
            "## 판정하지 않는 것 (계산한 척하지 않습니다)",
            "그라디언트·이미지 위 글자의 대비 · 줄 높이가 '자동'인 글자 · 실제 렌더링 결과(폰트 폴백,",
            "자간 늘어짐) · 화면 밖 스크롤 · 애니메이션 상태 · 다크 모드 대응(별도 파일이면 별도 검사).",
            "",
            "## 한 번에 흐르는 순서",
            '1. `read_design("checkout.json")` — 구조를 본다',
            '2. `audit_design("checkout.json")` — 점수와 위반',
            '3. `fix_order("checkout.json")` — 위에서부터 고친다',
            '4. `write_design_md("checkout.json", save_to="DESIGN.md")` — 디자인 시스템 문서',
            "",
            "> 점수 = 100 − Σ(규칙별 감점: 치명 25 · 심각 12 · 보통 4). 같은 규칙이 여러 번 나와도 한 번만 깎습니다.",
            "> 등급: " + " · ".join(f"{label}" for label in SEVERITY_ORDER),
        ]
    )
    return _finish(text, _budget(max_tokens))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="design-spec-mcp", description=__doc__)
    parser.add_argument("--root", default=None, help="상대 경로의 기준 폴더 (기본: 현재 폴더)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["DESIGN_SPEC_ROOT"] = str(Path(args.root).resolve())
    mcp.run()


if __name__ == "__main__":
    main()


_ = (_audit_design,)
