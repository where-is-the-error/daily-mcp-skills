"""검사 실행 — 규칙 41종을 차트 하나에 걸고 점수·판정을 낸다."""

from __future__ import annotations

from datetime import datetime, timezone

from .rules import RULES, Rule
from .types import Chart, Finding, Report


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(chart: Chart, rules: tuple[Rule, ...] | None = None) -> Report:
    findings: list[Finding] = []
    skipped: list[str] = []
    for rule in rules or RULES:
        try:
            result = rule.check(chart)
        except Exception as exc:  # 규칙 하나가 죽어도 검사 전체를 죽이지 않는다
            skipped.append(f"{rule.id} — 검사 중 오류: {exc}")
            continue
        if not result:
            continue
        if isinstance(result, tuple):
            evidence, fix = result
        else:
            evidence, fix = result, rule.fix
        findings.append(
            Finding(
                rule_id=rule.id,
                severity=rule.severity,
                title=rule.title,
                evidence=evidence,
                fix=fix,
                section=rule.section,
                weight=rule.weight,
            )
        )
    if chart.kind == "unknown":
        skipped.append("차트 형식 — mark 를 알아보지 못해 형식 규칙 일부를 건너뛰었습니다.")
    if not chart.visible_numbers():
        skipped.append("값 — 스펙에 값이 없어 비율·과장 계산을 하지 못했습니다.")
    if chart.warnings:
        skipped.extend(chart.warnings)
    return score(findings, chart=chart, skipped=skipped)


def score(findings: list[Finding], chart: Chart | None = None, skipped: list[str] | None = None) -> Report:
    total = min(100, sum(f.weight for f in findings))
    value = max(0, 100 - total)
    if any(f.severity == "block" for f in findings):
        verdict = "hold"
    elif any(f.severity == "warn" for f in findings):
        verdict = "warn"
    else:
        verdict = "pass"
    return Report(
        chart=chart,
        findings=findings,
        score=value,
        verdict=verdict,
        checked=len(RULES),
        skipped=list(skipped or []),
        created_at=_now(),
    )


def verdict_text(verdict: str) -> str:
    return {"pass": "통과", "warn": "주의", "hold": "보류"}.get(verdict, verdict)


def summary_line(report: Report) -> str:
    return (
        f"판정: {verdict_text(report.verdict)} ({report.score}/100) · "
        f"막음 {len(report.blocking())} · 주의 {len(report.warnings())} · 참고 {len(report.infos())}"
        f" · 규칙 {report.checked}종 검사"
    )
