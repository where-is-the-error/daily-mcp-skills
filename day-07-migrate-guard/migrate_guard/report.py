"""화면에 보이는 글 — 요약·문장·잠금·판정·단계·되돌리기·스키마·규칙.

문장은 짧게, 숫자는 항상 붙인다. 판정과 근거를 같은 화면에 둔다.
"""

from __future__ import annotations

from . import risks
from .dialect import CostKind, Severity
from .fmt import duration, rows as fmt_rows, secs
from .operations import Migration
from .rollback import rollback_sql
from .rollout import expand_contract
from .schema import SchemaDiff
from .compare import Comparison

__all__ = [
    "summary",
    "statements",
    "locks",
    "risk",
    "rollout",
    "rollback",
    "schema_diff",
    "comparison",
    "rules",
]


def _label(migration: Migration) -> str:
    return migration.label or "마이그레이션"


def _counts_line(counts: dict[Severity, int]) -> str:
    return " · ".join(f"{s.name} {counts[s]}" for s in Severity)


# --------------------------------------------------------------------- 요약
def summary(migration: Migration, rates=None) -> str:
    items = risks.findings(migration, rates)
    counts = risks.summary_counts(items)
    worst = migration.worst(rates)
    hold = migration.hold_seconds(rates)

    lines = [f"# {_label(migration)}"]
    head = f"문장 {len(migration.sql_ops)}개 · 표 {len(migration.tables())}개 · 판정 **{risks.verdict(items)}**"
    if worst:
        head += f" · 최대 잠금 {duration(worst.estimate(rates))} ({worst.target} · {worst.lock_mode})"
    else:
        lines_head = "읽기·쓰기를 막는 문장 없음"
        head += f" · {lines_head}"
    lines.append(head)
    lines.append("")
    if migration.tables():
        lines.append("- 바뀌는 표: " + ", ".join(migration.tables()))
    lines.append(f"- 위험: {_counts_line(counts)}")
    if migration.transaction_wrapped:
        lines.append(f"- BEGIN…COMMIT 하나로 묶여 있음 → 락이 커밋까지 유지 (합계 {duration(hold)})")
    elif hold:
        lines.append(f"- 문장별 실행 → 가장 긴 잠금 {duration(hold)}")
    lost = [op for op in migration.ops if op.irreversible]
    if lost:
        lines.append(f"- 값이 사라지는 문장 {len(lost)}개: " + ", ".join(f"{op.ref}({op.kind})" for op in lost))
    if not migration.rows:
        lines.append("- 행 수 추정치가 없어 표마다 100,000행으로 가정했습니다 (--rows 로 실제 값을 주세요)")
    lines.append("")
    lines.append("## 먼저 볼 문장")
    for finding in [f for f in items if f.severity <= Severity.심각][:5]:
        lines.append(f"- {finding.ref} (줄 {finding.line}) · {finding.severity.name} · {finding.rule.title}"
                     f" — {finding.table or ''}".rstrip(" —"))
    if not [f for f in items if f.severity <= Severity.심각]:
        lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------- 문장
def statements(migration: Migration, max_items: int = 40) -> str:
    lines = [f"# {_label(migration)} — 문장 {len(migration.sql_ops)}개"]
    lines.append("")
    for op in migration.ops[:max_items]:
        lock_bit = "경합 없음" if not op.contends else f"{op.lock_mode} · {op.lock.describe()}"
        lines.append(f"{op.ref} · 줄 {op.line} · {op.kind} · {op.table or '-'} · {lock_bit}")
        lines.append(f"    {op.sql[:120]}{'…' if len(op.sql) > 120 else ''}")
    if len(migration.ops) > max_items:
        lines.append(f"… {len(migration.ops) - max_items}개 더 (max_items 로 늘릴 수 있습니다)")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------- 잠금
def locks(migration: Migration, rates=None, max_items: int = 20) -> str:
    worst = migration.worst(rates)
    head = f"# {_label(migration)} — 잠금"
    if worst:
        head += f" · 최대 {duration(worst.estimate(rates))} ({worst.target} · {worst.lock_mode})"
    lines = [head, ""]
    if not migration.blocking_ops:
        lines.append("읽기·쓰기를 막는 잠금이 없습니다.")
        return "\n".join(lines) + "\n"

    lines.append("문장 · 표 · 락 모드 · 막는 것 · 예상 시간")
    for op in migration.ops[:max_items]:
        if not op.blocking:
            continue
        lines.append(
            f"- {op.ref} 줄 {op.line} · {op.target} · {op.lock_mode} · {op.lock.describe()} · "
            f"약 {duration(op.estimate(rates))}"
        )
        if op.cost.kind is not CostKind.NONE:
            source = "실제 행 수" if migration.table_rows(op.table)[1] else "가정"
            lines.append(f"    {op.cost.note or op.cost.kind.name} · {fmt_rows(op.cost.rows)}행 ({source})")
    lines.append("")
    lines.append(f"**락 유지 합계** {duration(migration.hold_seconds(rates))}"
                 + (" (BEGIN…COMMIT 하나)" if migration.transaction_wrapped else " (문장별 최댓값)"))
    lines.append("")
    lines.append("예상 시간은 모델입니다 — 재작성 60,000행/초 · 스캔 250,000행/초 · 인덱스 90,000행/초 가정.")
    lines.append("실측이 아니므로 배포 전에 스테이징에서 같은 크기의 표로 한 번 재 보세요.")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------- 판정
def risk(migration: Migration, rates=None, severity: str = "", max_items: int = 14) -> str:
    items = risks.findings(migration, rates)
    if severity:
        threshold = severity.strip()
        if threshold not in risks.SEVERITY_ORDER:
            raise ValueError("severity 는 치명 · 심각 · 보통 · 참고 중 하나입니다.")
        limit = risks.SEVERITY_ORDER[threshold]
        items = [f for f in items if risks.SEVERITY_ORDER[f.severity.name] <= limit]

    counts = risks.summary_counts(risks.findings(migration, rates))
    lines = [f"# {_label(migration)} — 판정 **{risks.verdict(risks.findings(migration, rates))}**"]
    lines.append(_counts_line(counts))
    lines.append("")
    if not items:
        lines.append("해당 등급의 위험이 없습니다.")
        return "\n".join(lines) + "\n"

    for finding in items[:max_items]:
        lines.append(f"**{finding.severity.name} · {finding.rule.title}** — `{finding.ref}` (줄 {finding.line})"
                     f" {finding.table or ''}".rstrip())
        lines.append(f"- 문장: {finding.summary}")
        for evidence in finding.evidence:
            if evidence:
                lines.append(f"- 근거: {evidence}")
        lines.append(f"- 고치기: {finding.fix}")
        lines.append("")
    if len(items) > max_items:
        lines.append(f"… {len(items) - max_items}건 더 (max_items 로 늘릴 수 있습니다)")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------- 단계
def rollout(migration: Migration, rates=None) -> str:
    phases = expand_contract(migration)
    before = migration.hold_seconds(rates)
    lines = [f"# {_label(migration)} — 다시 쓴 단계"]
    total_steps = sum(len(p.steps) for p in phases)
    lines.append(f"문장 {len(migration.sql_ops)}개 → 단계 {total_steps}개 · 최대 잠금 {duration(before)} → "
                 f"{duration(_phase_peak(phases))}")
    lines.append("")
    for phase in phases:
        lines.append(f"## {phase.title}")
        for reason in phase.why:
            lines.append(f"- 바꾼 이유: {reason}")
        for step in phase.steps:
            if step.note:
                lines.append(f"-- {step.note}")
            for raw in step.sql.splitlines():
                lines.append(raw.rstrip() + (";" if not raw.rstrip().endswith(";") else ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _phase_peak(phases) -> float:
    worst = 0.0
    for phase in phases:
        for step in phase.steps:
            if step.blocks:
                worst = max(worst, step.seconds)
    return worst


# --------------------------------------------------------------------- 되돌리기
def rollback(migration: Migration) -> str:
    return rollback_sql(migration)


# --------------------------------------------------------------------- 스키마
def schema_diff(diff: SchemaDiff, label: str = "") -> str:
    head = f"# 스키마 변화{f' — {label}' if label else ''}"
    lines = [head, ""]
    if diff.empty:
        lines.append("스키마가 바뀌지 않습니다.")
        return "\n".join(lines) + "\n"
    if diff.tables_added:
        lines.append("- 새 표: " + ", ".join(diff.tables_added))
    if diff.tables_removed:
        lines.append("- 사라지는 표: " + ", ".join(diff.tables_removed))
    if diff.columns_added:
        lines.append("- 새 컬럼: " + ", ".join(f"{t}.{c}" for t, c in diff.columns_added))
    if diff.columns_removed:
        lines.append("- 사라지는 컬럼: " + ", ".join(f"{t}.{c}" for t, c in diff.columns_removed))
    for change in diff.columns_changed:
        lines.append(f"- 바뀌는 컬럼: {change.table}.{change.column} · {change.field} {change.before} → {change.after}")
    if diff.indexes_added:
        lines.append("- 새 인덱스: " + ", ".join(diff.indexes_added))
    if diff.indexes_removed:
        lines.append("- 사라지는 인덱스: " + ", ".join(diff.indexes_removed))
    for name, detail in diff.indexes_changed:
        lines.append(f"- 바뀌는 인덱스: {name} · {detail}")
    if diff.constraints_added:
        lines.append("- 새 제약: " + ", ".join(f"{t}.{c}" for t, c in diff.constraints_added))
    if diff.constraints_removed:
        lines.append("- 사라지는 제약: " + ", ".join(f"{t}.{c}" for t, c in diff.constraints_removed))
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------- 비교
def comparison(result: Comparison, max_items: int = 10) -> str:
    return result.render(max_items=max_items)


# --------------------------------------------------------------------- 규칙
def rules() -> str:
    lines = [f"# 규칙 {len(risks.CATALOG)}종", ""]
    for item in risks.CATALOG:
        lines.append(f"- {item.severity.name} · {item.rule_id} — {item.title}")
        lines.append(f"    {item.why}")
    lines.append("")
    lines.append("## 판정하지 않는 것")
    for text in NOT_JUDGED:
        lines.append(f"- {text}")
    return "\n".join(lines).rstrip() + "\n"


NOT_JUDGED = [
    "실행 시간의 실측 — 행/초 가정으로만 계산합니다 (테이블 크기·I/O·캐시에 따라 몇 배씩 달라집니다)",
    "동시 트랜잭션이 잡고 있는 락·대기열 — 지금 이 순간의 pg_locks 는 보지 않습니다",
    "복제 지연·디스크·WAL 크기 — 재작성의 부수 비용은 계산하지 않습니다",
    "데이터 값의 분포 — 타입 축소가 실제로 실패할지는 세어 보지 않습니다(확인 쿼리를 제안만 합니다)",
    "MySQL·Oracle 등 다른 방언 — PostgreSQL 문법 기준입니다",
    "마이그레이션 도구의 동작 — Flyway·Alembic 이 트랜잭션을 씌우는지는 도구 설정을 봐야 합니다",
    "제약 이름이 없는 ADD CONSTRAINT 의 실제 이름 — PostgreSQL 이 붙이는 이름은 미리 알 수 없습니다",
]
