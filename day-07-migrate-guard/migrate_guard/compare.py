"""마이그레이션 두 개 비교 — 고친 파일이 정말 나아졌는지 숫자로 본다."""

from __future__ import annotations

from dataclasses import dataclass

from . import risks
from .dialect import Severity
from .fmt import duration
from .operations import Migration

__all__ = ["Comparison", "compare"]


@dataclass
class Comparison:
    before: Migration
    after: Migration
    before_findings: list[risks.Finding]
    after_findings: list[risks.Finding]

    @property
    def before_counts(self) -> dict[Severity, int]:
        return risks.summary_counts(self.before_findings)

    @property
    def after_counts(self) -> dict[Severity, int]:
        return risks.summary_counts(self.after_findings)

    def improved_rules(self) -> list[str]:
        before = {f.rule_id for f in self.before_findings}
        after = {f.rule_id for f in self.after_findings}
        return sorted(before - after)

    def new_rules(self) -> list[str]:
        before = {f.rule_id for f in self.before_findings}
        after = {f.rule_id for f in self.after_findings}
        return sorted(after - before)

    def render(self, max_items: int = 10) -> str:
        b_hold = self.before.hold_seconds()
        a_hold = self.after.hold_seconds()
        lines = ["# 두 마이그레이션 비교"]
        lines.append("")
        lines.append(f"- 이전: 문장 {len(self.before.sql_ops)}개 · 판정 **{risks.verdict(self.before_findings)}** · "
                     f"락 유지 {duration(b_hold)}")
        lines.append(f"- 이후: 문장 {len(self.after.sql_ops)}개 · 판정 **{risks.verdict(self.after_findings)}** · "
                     f"락 유지 {duration(a_hold)}")
        lines.append("")

        lines.append("## 등급별")
        for severity in Severity:
            before = self.before_counts[severity]
            after = self.after_counts[severity]
            arrow = "그대로" if before == after else ("감소" if after < before else "증가")
            lines.append(f"- {severity.name}: {before} → {after} ({arrow})")
        lines.append("")

        gone = self.improved_rules()
        if gone:
            lines.append("## 사라진 규칙")
            for rule_id in gone[:max_items]:
                rule = risks.rule(rule_id)
                lines.append(f"- {rule.rule_id} — {rule.title}")
            lines.append("")

        added = self.new_rules()
        if added:
            lines.append("## 새로 생긴 규칙")
            for rule_id in added[:max_items]:
                rule = risks.rule(rule_id)
                lines.append(f"- {rule.rule_id} — {rule.title}")
            lines.append("")

        worst_before = self.before.worst()
        worst_after = self.after.worst()
        if worst_before:
            lines.append(f"## 가장 긴 잠금")
            lines.append(f"- 이전: {worst_before.target} · {worst_before.lock_mode} · "
                         f"{duration(worst_before.estimate())}")
            if worst_after:
                lines.append(f"- 이후: {worst_after.target} · {worst_after.lock_mode} · "
                             f"{duration(worst_after.estimate())}")
            else:
                lines.append("- 이후: 읽기·쓰기를 막는 문장 없음")
            lines.append("")
        if self.before.transaction_wrapped and not self.after.transaction_wrapped:
            lines.append("- 트랜잭션 묶음: 이전은 BEGIN…COMMIT 하나, 이후는 문장별로 분리")
        return "\n".join(lines).rstrip() + "\n"


def compare(before: Migration, after: Migration) -> Comparison:
    return Comparison(
        before=before,
        after=after,
        before_findings=risks.findings(before),
        after_findings=risks.findings(after),
    )
