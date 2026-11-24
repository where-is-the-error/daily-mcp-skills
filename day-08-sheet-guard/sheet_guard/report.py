"""MCP 툴과 CLI가 함께 쓰는 한국어 출력."""

from __future__ import annotations

from .apply import Applied
from .compare import Diff
from .plan import Plan
from .rules import RULES, SEVERITIES, SEVERITY_LABELS, Finding, counts
from .types import KIND_LABELS

ICON = {"error": "🔴", "warn": "🟠", "info": "⚪"}
KIND_WIDTH = 4


def _pad(text: str, width: int) -> str:
    span = sum(2 if ord(ch) > 0x1100 else 1 for ch in text)
    return text + " " * max(0, width - span)


def table_summary(table) -> str:
    from .rules import check

    if not table.columns:
        return f"⚠️ {table.source}: 읽을 표가 없습니다. {' '.join(table.notes)}"
    findings = check(table)
    tally = counts(findings)
    lines = []
    head = f"📄 {table.source}"
    if table.sheet:
        head += f" [{table.sheet}]"
    lines.append(head)
    lines.append(
        f"   인코딩 {table.encoding.upper()}(확신 {table.encoding_confidence:.2f}) · 구분자 "
        f"{'탭' if table.delimiter == chr(9) else table.delimiter} · "
        f"{len(table.data_rows):,}행 × {table.width}열"
    )
    header_note = f"머리글 {table.header_span}줄" if table.header_span else "머리글 없음(첫 줄부터 데이터)"
    if table.preamble:
        header_note += f", 앞머리 {len(table.preamble)}줄 뺌"
    lines.append(f"   {header_note}")
    if table.notes:
        lines.append("   · " + " / ".join(table.notes[:3]))
    lines.append("")
    lines.append(f"   {_pad('열', 18)} {_pad('종류', 12)} {'채움':>4}  값")
    for stat in table.stats()[:14]:
        examples = stat.examples.get(stat.kind, "")
        value = f"{len(stat.distinct):,}종" + (f" · {examples[:24]}" if examples else "")
        lines.append(f"   {_pad(stat.name[:18], 18)} {_pad(KIND_LABELS.get(stat.kind, stat.kind), 12)} "
                     f"{stat.fill_rate * 100:4.0f}%  {value}")
    if table.width > 14:
        lines.append(f"   … {table.width - 14}열 더")
    lines.append("")
    verdict = f"치명 {tally['error']} · 주의 {tally['warn']} · 참고 {tally['info']}"
    lines.append(f"   판정: {verdict}" + ("  → find_problems 로 자세히" if tally["error"] or tally["warn"] else " (막는 문제 없음)"))
    if table.meta.get("merged"):
        lines.append(f"   병합 칸 {len(table.meta['merged'])}곳")
    return "\n".join(lines)


def problems_view(findings: list[Finding], max_items: int = 12, severity: str = "") -> str:
    tally = counts(findings)
    if not findings:
        return "✅ 막는 문제를 찾지 못했습니다."
    lines = [" · ".join(f"{SEVERITY_LABELS[s]} {tally[s]}" for s in SEVERITIES if tally[s]) + "  (건수는 규칙 단위)"]
    shown = 0
    for finding in findings:
        if severity and finding.severity != severity:
            continue
        if shown >= max_items:
            remaining = len([f for f in findings if not severity or f.severity == severity]) - shown
            lines.append(f"… {remaining}건 더 (max_items 로 늘리세요)")
            break
        lines.append("")
        lines.append(f"{ICON.get(finding.severity, '·')} {finding.rule} — {finding.title}")
        lines.append(f"   {finding.detail}")
        if finding.rows:
            lines.append(f"   행: {', '.join(finding.rows[:8])}" + (f" 외 {finding.count - 8}건" if finding.count > 8 else ""))
        if finding.fix:
            lines.append(f"   고치기: {finding.fix.get('kind')} (clean_plan 에 들어감)")
        shown += 1
    return "\n".join(lines)


def plan_view(plan: Plan) -> str:
    if not plan.actions:
        return "고칠 것이 없습니다." + (f"\n사람이 봐야 함: {', '.join(f.rule for f in plan.review)}" if plan.review else "")
    lines = [f"🧹 정리 계획 — {len(plan.actions)}단계 · 바뀌는 칸 {plan.changes:,}개"]
    for action in plan.actions:
        review = " ⚠️확인" if action.needs_review else ""
        lines.append(f"   {action.id} {_pad(action.label, 16)} {action.target} · {action.affects:,}개 "
                     f"(확신 {action.confidence:.2f}){review}")
        if action.note:
            lines.append(f"      ↳ {action.note}")
        lines.append(f"      이유: {', '.join(action.reason)}")
    if plan.review:
        lines.append("")
        lines.append("사람이 봐야 함(자동으로 고치지 않음): " + ", ".join(f"{f.rule}" for f in plan.review))
    lines.append("")
    lines.append("적용: apply_plan — 원본은 그대로 두고 정리본을 새로 씁니다.")
    return "\n".join(lines)


def applied_view(applied: Applied, out_path: str = "") -> str:
    lines = [f"✅ 적용 완료 — 값 {len(applied.changes):,}칸 · 뺀 행 {len(applied.dropped):,}개"
             + (f" · 격리 {len(applied.quarantined)}행" if applied.quarantined else "")
             + (f" · 새 열 {', '.join(applied.added_columns)}" if applied.added_columns else "")]
    for action_id, count in applied.per_action.items():
        if count:
            lines.append(f"   {action_id}: {count:,}개")
    if out_path:
        lines.append(f"   정리본: {out_path} ({len(applied.table.rows):,}행 × {applied.table.width}열, UTF-8 BOM)")
    for note in applied.notes:
        lines.append(f"   · {note}")
    if applied.review:
        lines.append("   확인 필요: " + ", ".join(f["rule"] for f in applied.review))
    samples = applied.changes[:5]
    if samples:
        lines.append("")
        lines.append("바뀐 예")
        for change in samples:
            before = change.before if len(change.before) <= 24 else change.before[:24] + "…"
            after = change.after if len(change.after) <= 24 else change.after[:24] + "…"
            lines.append(f"   {change.row} {change.column}: '{before}' → '{after}' ({change.action})")
    return "\n".join(lines)


def diff_view(diff: Diff) -> str:
    lines = [f"🔍 정리 전 {diff.rows_before:,}행 → 정리 후 {diff.rows_after:,}행 · 짝지은 행 {diff.matched:,} "
             f"({diff.kept_ratio * 100:.1f}% 유지)"]
    lines.append(f"   판정: {diff.verdict}")
    if diff.cells_changed:
        lines.append(f"   바뀐 칸 {diff.cells_changed:,}개")
    if diff.rows_removed:
        lines.append(f"   빠진 행 {len(diff.rows_removed):,}개: {', '.join(diff.rows_removed[:8])}"
                     + (" …" if len(diff.rows_removed) > 8 else ""))
    if diff.rows_added:
        lines.append(f"   새로 생긴 행 {len(diff.rows_added):,}개: {', '.join(diff.rows_added[:8])}")
    if diff.columns_added:
        lines.append(f"   새 열: {', '.join(diff.columns_added)}")
    if diff.values_lost:
        lines.append(f"   ⚠️ 값이 사라진 칸 {len(diff.values_lost)}개")
        for lost in diff.values_lost[:5]:
            lines.append(f"      {lost['row']} {lost['column']}: '{lost['was']}' → (빈칸)")
    for note in diff.notes:
        lines.append(f"   · {note}")
    return "\n".join(lines)


def catalog_view(rule: str = "") -> str:
    if rule:
        meta = RULES.get(rule)
        if not meta:
            raise ValueError(f"'{rule}' 규칙이 없습니다. rule_catalog 로 목록을 보세요.")
        return f"{rule} — {meta['title']}\n   왜: {meta['why']}\n   고치기: {meta.get('action') or '자동으로 고치지 않음(사람이 판단)'}"
    lines = [f"규칙 {len(RULES)}종 — 표를 쓰기 전에 확인하는 것들"]
    for key in sorted(RULES):
        meta = RULES[key]
        action = meta.get("action") or "—"
        lines.append(f"   {_pad(key, 22)} {meta['title']}  [{action}]")
    lines.append("")
    lines.append("규칙 하나를 자세히: rule_catalog(rule=\"duplicate-rows\")")
    return "\n".join(lines)


OVERVIEW = """sheet-guard — 표를 LLM·엑셀에 넣기 전에 읽는다

공공데이터 CSV/엑셀에서 실제로 자주 깨지는 곳을 먼저 잡는다.
  · 인코딩: CP949(EUC-KR) 파일을 UTF-8로 읽어 한글이 깨지는 문제
  · 머리글: 제목·단위 줄, 2줄 머리글, 이름 없는 열
  · 행: 데이터 사이 소계·합계, 구역 제목, 각주, 빈 줄
  · 값: 앞자리 0(우편번호·코드), 날짜 표기 혼용, 천 단위 쉼표, 값 안의 단위,
        전각 숫자, 앞뒤 공백, 완전 중복 행

툴 9개
  read_table(path)        파일을 읽어 인코딩·머리글·열 요약과 ref를 준다
  profile_columns(ref)    열마다 종류·채움률·값 분포
  find_problems(ref)      규칙 위반 목록(행 참조 포함)
  clean_plan(ref)         고칠 순서와 확신도
  apply_plan(ref, out)    정리본 CSV + 바뀐 곳 기록(changelog) — 원본은 그대로
  to_markdown(ref)        LLM에 넣기 좋은 마크다운 표
  compare_tables(a, b)    정리 전후 행·값 대조
  rule_catalog(rule)      규칙 설명
  overview()              이 안내

판정하지 않는 것
  · 숫자의 의미(단위가 맞는지, 값이 현실적인지) — 통계적 이상값은 보지 않는다
  · 수식의 계산 결과 — 엑셀에 저장된 값만 읽는다(계산값이 없으면 그렇다고 표시)
  · 병합 칸의 의도 — 병합을 풀어 채우는 것은 제안이며 확신도가 낮다
  · 셀 서식(색·굵기)·차트·피벗 — 값만 본다
"""


LIMITS = (
    "한계: 값의 의미·통계적 이상값은 판정하지 않고, 엑셀 수식은 저장된 계산값만 읽습니다. "
    "앞자리 0 복원은 자릿수 추정이라 확신도가 낮습니다."
)
