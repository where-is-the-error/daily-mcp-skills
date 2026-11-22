"""plan 두 개 비교 — '고친 뒤' 무엇이 달라졌는지.

    a = load_plan("proposal.json")   # 위험한 제안
    b = load_plan("fixed.json")      # 리뷰 후 고친 것
    compare(a, b).render()

주소(address)를 기준으로 맞춘다. 같은 주소의 액션이 바뀌면(재생성 → 수정)
그것이 '고쳐진 것'이고, 새로 생긴 삭제는 '새로 생긴 위험'이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .plan import Plan
from . import risks


@dataclass
class AddressDelta:
    address: str
    before_kind: str
    after_kind: str

    @property
    def direction(self) -> str:
        severity = {"noop": 0, "read": 0, "create": 1, "update": 1, "delete": 2, "replace": 3, "other": 1}
        a, b = severity.get(self.before_kind, 1), severity.get(self.after_kind, 1)
        if a == b:
            return "같음"
        return "약해짐" if b < a else "강해짐"


@dataclass
class Comparison:
    before: Plan
    after: Plan
    changed: list[AddressDelta] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)   # 두 번째 plan 에서 사라진 주소
    added: list[str] = field(default_factory=list)     # 두 번째 plan 에 새로 생긴 주소
    before_findings: list[risks.Finding] = field(default_factory=list)
    after_findings: list[risks.Finding] = field(default_factory=list)

    @property
    def fixed(self) -> list[AddressDelta]:
        return [d for d in self.changed if d.direction == "약해짐"]

    @property
    def worse(self) -> list[AddressDelta]:
        return [d for d in self.changed if d.direction == "강해짐"]

    def counts_before(self) -> dict[str, int]:
        return risks.counts(self.before_findings)

    def counts_after(self) -> dict[str, int]:
        return risks.counts(self.after_findings)

    def render(self, max_items: int = 12) -> str:
        a = self.counts_before()
        b = self.counts_after()
        lines = [
            f"# 두 plan 비교  ({self.before.source or 'plan A'} → {self.after.source or 'plan B'})",
            "",
            f"- 판정: **{risks.verdict(self.before_findings)}** → **{risks.verdict(self.after_findings)}**",
            f"- 치명 {a[risks.CRITICAL]} → {b[risks.CRITICAL]} · 심각 {a[risks.HIGH]} → {b[risks.HIGH]} · "
            f"보통 {a[risks.MEDIUM]} → {b[risks.MEDIUM]}",
            f"- 리소스 변경: {len(self.before.real_changes())} → {len(self.after.real_changes())}",
            f"- 사라지는 리소스: {len(self.before.destructive())} → {len(self.after.destructive())}",
        ]
        if self.fixed:
            lines.append("")
            lines.append("## 약해진 것 (좋아짐)")
            for delta in self.fixed[:max_items]:
                lines.append(f"- {delta.address}: {_label(delta.before_kind)} → {_label(delta.after_kind)}")
        if self.worse:
            lines.append("")
            lines.append("## 강해진 것 (나빠짐)")
            for delta in self.worse[:max_items]:
                lines.append(f"- {delta.address}: {_label(delta.before_kind)} → {_label(delta.after_kind)}")
        if self.removed:
            lines.append("")
            lines.append("## 두 번째 plan 에서 빠진 리소스")
            for address in self.removed[:max_items]:
                lines.append(f"- {address}")
        if self.added:
            lines.append("")
            lines.append("## 두 번째 plan 에 새로 생긴 리소스")
            for address in self.added[:max_items]:
                lines.append(f"- {address}")
        if self.after_findings:
            lines.append("")
            lines.append("## 남은 위험")
            for finding in self.after_findings[:max_items]:
                lines.append(f"- [{finding.severity}] {finding.title} — {finding.address} ({finding.detail})")
        if not (self.fixed or self.worse or self.removed or self.added or self.after_findings):
            lines.append("")
            lines.append("두 plan 의 리소스 변경이 같습니다.")
        lines.append("")
        lines.append("주의: plan 두 개가 같은 state 에서 나왔는지 확인하세요. state 가 다르면 비교가 어긋납니다.")
        return "\n".join(lines)


def _label(kind: str) -> str:
    return {"create": "생성", "update": "수정", "delete": "삭제", "replace": "재생성",
            "noop": "변화 없음", "read": "읽기", "other": "기타"}.get(kind, kind)


def compare(before: Plan, after: Plan) -> Comparison:
    a = before.by_address()
    b = after.by_address()
    changed: list[AddressDelta] = []
    for address in sorted(set(a) & set(b)):
        if a[address].kind != b[address].kind:
            changed.append(AddressDelta(address, a[address].kind, b[address].kind))
    return Comparison(
        before=before,
        after=after,
        changed=changed,
        removed=sorted(set(a) - set(b)),
        added=sorted(set(b) - set(a)),
        before_findings=risks.findings(before),
        after_findings=risks.findings(after),
    )
