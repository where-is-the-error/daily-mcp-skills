"""검사 한 번 — 점수·보고·고치는 순서.

점수 = 100 − Σ(규칙별 감점). 같은 규칙이 여러 번 나와도 **한 번만** 깎습니다.
  치명 25 · 심각 12 · 보통 4
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .color import Color
from .nodes import Design, load_design
from .palette import Palette, analyse_palette, PAGE_WHITE
from .rules import (
    SEVERITY_ORDER,
    SEVERITY_WEIGHT,
    Analysis,
    Finding,
    analyse,
    run_rules,
)
from .spacing import RadiiReport, SpacingReport, analyse_radii, analyse_spacing
from .typography import TypeReport, analyse_type

__all__ = ["Audit", "audit_design", "load_and_audit", "render", "render_plan", "payload_json", "GRADE_BANDS"]

GRADE_BANDS = ((90, "양호"), (70, "주의"), (40, "위험"), (0, "심각"))


def _grade(score: int) -> str:
    for floor, label in GRADE_BANDS:
        if score >= floor:
            return label
    return "심각"  # pragma: no cover


@dataclass
class Audit:
    design: Design
    analysis: Analysis
    findings: list[Finding] = field(default_factory=list)

    # ------------------------------------------------------------ 계산
    @property
    def rule_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.rule] = counts.get(finding.rule, 0) + 1
        return counts

    @property
    def penalty(self) -> int:
        return sum(SEVERITY_WEIGHT.get(finding.severity, 0) for finding in self.findings_by_rule())

    @property
    def score(self) -> int:
        return max(0, 100 - self.penalty)

    @property
    def grade(self) -> str:
        return _grade(self.score)

    @property
    def path_label(self) -> str:
        return self.design.source or "inline"

    def severity_counts(self) -> dict[str, int]:
        counts = {severity: 0 for severity in SEVERITY_ORDER}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def findings_by_rule(self) -> list[Finding]:
        """규칙마다 첫 번째만 — 감점·요약은 '고칠 곳 하나' 단위로 센다."""
        seen: set[str] = set()
        firsts: list[Finding] = []
        for finding in self.sorted_findings():
            if finding.rule in seen:
                continue
            seen.add(finding.rule)
            firsts.append(finding)
        return firsts

    def sorted_findings(self) -> list[Finding]:
        order = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}

        def key(finding: Finding):
            return (order.get(finding.severity, len(order)), finding.rule, finding.ref)

        return sorted(self.findings, key=key)

    def to_dict(self) -> dict:
        return {
            "path": self.path_label,
            "title": self.design.title,
            "score": self.score,
            "grade": self.grade,
            "rules_hit": len(self.findings_by_rule()),
            "violations": [finding.as_dict() for finding in self.sorted_findings()],
            "stats": self.stats(),
            "palette": [
                {
                    "hex": use.color.hex,
                    "name": use.role_label(),
                    "count": use.count,
                    "area": round(use.area, 1),
                    "contrast_worst": None if use.contrast_worst is None else round(use.contrast_worst, 2),
                }
                for use in self.analysis.palette.uses
            ],
            "not_judged": self.not_judged(),
        }

    def stats(self) -> dict:
        design = self.design
        analysis = self.analysis
        return {
            "screens": len(design.screens),
            "nodes": len(design.nodes),
            "visible_nodes": len(design.visible_nodes),
            "texts": len(design.texts),
            "colors": analysis.palette.distinct,
            "type_sizes": analysis.typography.distinct,
            "spacing_values": analysis.spacing.distinct,
            "spacing_base": analysis.spacing.base,
            "radii": analysis.radii.distinct,
        }

    def not_judged(self) -> list[str]:
        palette: Palette = self.analysis.palette
        notes: list[str] = []
        if palette.text_over_image:
            notes.append(
                f"그라디언트·이미지 위 글자 {len(palette.text_over_image)}곳은 대비를 계산하지 않았습니다"
            )
        if palette.gradients:
            notes.append(f"단색이 아닌 칠 {palette.gradients}곳(그라디언트·이미지)은 색 통계에서 뺐습니다")
        typography: TypeReport = self.analysis.typography
        if typography.no_line_height:
            notes.append(f"줄 높이가 '자동'인 글자 {typography.no_line_height}곳은 줄 높이를 판정하지 않았습니다")
        if typography.no_size:
            notes.append(f"글자 크기가 없는 텍스트 {typography.no_size}곳")
        if not self.analysis.design.screens:
            notes.append("화면(프레임)을 찾지 못했습니다 — 노드 하나만 있는 파일일 수 있습니다")
        return notes


# ------------------------------------------------------------------ 실행
def audit_design(
    design: Design,
    rule_ids: list[str] | None = None,
    min_touch: float = 44.0,
    page: Color | None = None,
) -> Audit:
    page_color = page or PAGE_WHITE
    for screen in design.screens:
        color = screen.opaque_fill()
        if color is not None:
            page_color = color
            break
    palette = analyse_palette(design, page_color)
    spacing: SpacingReport = analyse_spacing(design)
    radii: RadiiReport = analyse_radii(design)
    typography: TypeReport = analyse_type(design)
    context = analyse(design, palette, spacing, radii, typography, page_color, min_touch=min_touch)
    findings = run_rules(context, rule_ids)
    return Audit(design=design, analysis=context, findings=findings)


def load_and_audit(source, base_dir: Path | None = None, **kwargs) -> Audit:
    return audit_design(load_design(source, base_dir=base_dir), **kwargs)


def payload_json(audit: Audit) -> str:
    return json.dumps(audit.to_dict(), ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ 보고
def render(audit: Audit, max_per_rule: int = 20) -> str:
    design = audit.design
    stats = audit.stats()
    counts = audit.severity_counts()
    lines = [
        f"# design-spec · {design.title}  ({audit.path_label})",
        "",
        (
            f"- 화면 {stats['screens']}개 · 노드 {stats['nodes']}개 · 글자 {stats['texts']}개 · "
            f"색 {stats['colors']}종 · 크기 {stats['type_sizes']}단계 · "
            f"간격 값 {stats['spacing_values']}종"
            + (f" (기준 {stats['spacing_base']:g}px)" if stats["spacing_base"] else "")
        ),
    ]
    if not audit.findings:
        lines.append(f"- 점수 **{audit.score}/100** ({audit.grade}) · 위반 없음")
    else:
        lines.append(
            f"- 점수 **{audit.score}/100** ({audit.grade}) · 위반 **{len(audit.findings)}건** "
            f"(치명 {counts['치명']} · 심각 {counts['심각']} · 보통 {counts['보통']}) "
            f"· 규칙 {len(audit.findings_by_rule())}종"
        )

    by_rule: dict[str, list[Finding]] = {}
    for finding in audit.sorted_findings():
        by_rule.setdefault(finding.rule, []).append(finding)

    if by_rule:
        lines += ["", "## 위반 (무거운 것부터)"]
        for index, (rule_id, items) in enumerate(by_rule.items(), start=1):
            head = items[0]
            lines.append("")
            lines.append(f"{index}. **{rule_id}** {head.detail} — {head.severity}")
            shown = items[: max(1, max_per_rule)]
            for item in shown:
                where = item.where or design.title
                line = f"   - `{item.ref}` {where}" if item.ref else f"   - {where}"
                if item.detail and item.detail != head.detail:
                    line += f" · {item.detail}"
                lines.append(line)
                if item.evidence and item.evidence != item.detail:
                    lines.append(f"     근거: {item.evidence}")
                if item.fix:
                    lines.append(f"     고치기: {item.fix}")
            if len(items) > len(shown):
                lines.append(f"   - … {len(items) - len(shown)}곳 더 (max_per_rule 로 늘릴 수 있습니다)")

    notes = audit.not_judged()
    if notes:
        lines += ["", "## 판정하지 않은 것", *[f"- {note}" for note in notes]]
    return "\n".join(lines)


def render_plan(audit: Audit, max_steps: int = 8) -> str:
    if not audit.findings:
        return f"✅ {audit.path_label}: 고칠 것이 없습니다. 점수 {audit.score}/100."
    by_rule: dict[str, list[Finding]] = {}
    for finding in audit.sorted_findings():
        by_rule.setdefault(finding.rule, []).append(finding)
    order = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    ranked = sorted(
        by_rule.items(),
        key=lambda item: (order.get(item[1][0].severity, 9), -len(item[1]), item[0]),
    )
    lines = [
        f"# 고치기 순서 · {audit.design.title}",
        "",
        f"- 점수 {audit.score}/100 ({audit.grade}) · 규칙 {len(by_rule)}종 · 위반 {len(audit.findings)}건",
        "",
    ]
    for step, (rule_id, items) in enumerate(ranked[: max(1, max_steps)], start=1):
        head = items[0]
        lines.append(f"{step}. **{rule_id}** ({head.severity} · {len(items)}곳) — {head.detail}")
        lines.append(f"   - 바꿀 것: {head.fix or '위치를 확인하고 값을 맞추세요'}")
        lines.append(f"   - 첫 곳: `{head.ref}` {head.where}")
    if len(ranked) > max_steps:
        lines.append(f"… {len(ranked) - max_steps}종 더")
    lines += ["", "> 고친 뒤 같은 명령을 다시 돌려 점수가 올랐는지 확인하세요."]
    return "\n".join(lines)
