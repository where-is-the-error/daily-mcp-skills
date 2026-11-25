"""사람이 읽는 보고서 — 선택·구멍·위험·계획을 한 장에.

모든 보고서 끝에는 '판정하지 않는 것'을 붙인다. 이 툴은 테스트가 통과할지 말하지 않는다.
"""

from __future__ import annotations

from . import plan as plan_module
from .risk import SEVERITIES, counts, verdict
from .select import ChangeSet
from .types import Plan, Risk

MARK = {0: "◆", 1: "●", 2: "◐", 3: "○"}
LEVEL_LABEL = {0: "테스트 자체", 1: "직접", 2: "전이", 3: "약한 근거"}


def _short(path: str, limit: int = 48) -> str:
    return path if len(path) <= limit else "…" + path[-limit + 1:]


def summary_lines(change_set: ChangeSet) -> list[str]:
    repo = change_set.repo
    info = repo.summary()
    added = sum(view.change.added_count() for view in change_set.views)
    removed = sum(view.change.removed_count() for view in change_set.views)
    lines = [
        f"🎯 test-radar · 변경 {len(change_set.views)}개 파일 +{added}/-{removed}",
        f"   저장소 모듈 {info['modules']} · 테스트 {info['tests']}파일/{info['test_items']}항목"
        f" · 해석 못 한 import {info['unresolved']}",
    ]
    if info["parse_errors"]:
        lines.append(f"   ⚠️ 파싱 실패 {info['parse_errors']}개 파일 — 그 파일들의 간선은 비어 있습니다")
    return lines


def selection_lines(change_set: ChangeSet, limit: int = 40) -> list[str]:
    selections = sorted(change_set.selections.values(), key=lambda sel: (sel.level, -sel.score, sel.path))
    if not selections:
        return ["선택: 없음 — 이 변경에 도달하는 테스트를 찾지 못했습니다"]
    total = change_set.total_items()
    lines = [
        f"선택: {len(selections)}파일 · {change_set.selected_items()}/{total}항목 ({change_set.share():.0%})",
    ]
    for sel in selections[:limit]:
        lines.append(
            f"   {MARK.get(sel.level, '·')} {_short(sel.path)}  L{sel.level} {LEVEL_LABEL.get(sel.level, '')}"
            f"  {sel.reason}  ({sel.items}항목)"
        )
    if len(selections) > limit:
        lines.append(f"   … {len(selections) - limit}개 더")
    return lines


def gap_lines(change_set: ChangeSet, limit: int = 12) -> list[str]:
    if not change_set.gaps:
        return ["테스트 근거 없는 변경: 없음"]
    lines = [f"테스트 근거 없는 변경: {len(change_set.gaps)}건"]
    seen: set[str] = set()
    for gap in change_set.gaps:
        key = f"{gap['kind']}:{gap['path']}:{gap.get('symbol', '')}"
        if key in seen:
            continue
        seen.add(key)
        where = gap["path"]
        if gap.get("line"):
            where += f":{gap['line']}"
        lines.append(f"   · {where} — {gap['detail']}")
        if len(lines) > limit:
            lines.append("   …")
            break
    return lines


def risk_lines(risks: list[Risk], limit: int = 14) -> list[str]:
    if not risks:
        return ["위험 규칙: 해당 없음"]
    tally = counts(risks)
    head = "위험 규칙: " + " · ".join(f"{severity} {tally[severity]}" for severity in SEVERITIES if tally[severity])
    lines = [head]
    for risk in risks[:limit]:
        where = f" ({risk.where})" if risk.where else ""
        lines.append(f"   [{risk.severity}] {risk.title}{where} — {risk.detail}")
    if len(risks) > limit:
        lines.append(f"   … {len(risks) - limit}건 더 (rule_catalog 로 규칙 설명)")
    return lines


def plan_lines(plan: Plan, change_set: ChangeSet) -> list[str]:
    lines: list[str] = []
    if plan.fallback.get("triggered"):
        lines.append("계획: 전체 실행")
        for reason in plan.fallback.get("reasons", []):
            lines.append(f"   ! {reason}")
    else:
        lines.append(f"계획: 선택 실행 · 예상 {plan_module.estimated_total(plan):.2f}초(모델)")
    for command in plan.commands:
        lines.append(f"   {command['command']}")
        lines.append(f"      └ {command['items']}항목 · 예상 {command['est_seconds']:.2f}초 · {command['note']}")
    lines.append(
        f"   전체 실행: {plan.fallback['command']} · {plan.fallback['items']}항목"
        f" · 예상 {plan.fallback['est_seconds']:.2f}초(모델)"
    )
    return lines


def limits_lines() -> list[str]:
    return [
        "판정하지 않음: 테스트가 실제로 통과하는지 · 실행 시간(모델임) · 커버리지 % · 동적 import 뒤의 간선"
        " · 네이티브 확장/설정 파일의 의미 · 같은 이름의 다른 심볼",
    ]


def impact_report(change_set: ChangeSet, risks: list[Risk], plan: Plan) -> str:
    lines: list[str] = []
    lines.extend(summary_lines(change_set))
    lines.append("")
    lines.extend(selection_lines(change_set))
    lines.append("")
    lines.extend(gap_lines(change_set))
    lines.append("")
    lines.extend(risk_lines(risks))
    lines.append("")
    lines.extend(plan_lines(plan, change_set))
    lines.append("")
    lines.append(f"판정: {verdict(risks, change_set.fallback)}")
    if change_set.notes:
        lines.append("메모: " + " / ".join(change_set.notes[:6]))
    lines.extend(limits_lines())
    return "\n".join(lines)


def change_lines(change_set: ChangeSet, include_hunks: bool = False) -> str:
    lines = [f"변경 {len(change_set.views)}개 파일"]
    for view in change_set.views:
        change = view.change
        flags = []
        if change.status != "modified":
            flags.append(change.status)
        if change.binary:
            flags.append("binary")
        if view.module_path:
            flags.append(f"모듈 {view.module_name}")
        lines.append(
            f"  {change.path}  +{change.added_count()}/-{change.removed_count()}"
            + (f"  [{', '.join(flags)}]" if flags else "")
        )
        if view.symbols:
            lines.append("      바뀐 심볼: " + ", ".join(symbol.qualname for symbol in view.symbols[:6]))
        if view.removed_defs:
            lines.append("      사라진 정의: " + ", ".join(view.removed_defs[:6]))
        if view.signature_changes:
            for name, old, new in view.signature_changes[:4]:
                lines.append(f"      인자 변경: {name}{old} → {new}")
        if include_hunks:
            for hunk in change.hunks[:6]:
                lines.append(f"      @@ -{hunk.old_start},{hunk.old_len} +{hunk.new_start},{hunk.new_len} @@ {hunk.section}".rstrip())
                for head, body in hunk.context()[:14]:
                    lines.append(f"        {head}{body}")
                if len(hunk.context()) > 14:
                    lines.append("        …")
            if len(change.hunks) > 6:
                lines.append(f"      … 덩어리 {len(change.hunks) - 6}개 더")
    return "\n".join(lines)


def tests_lines(change_set: ChangeSet, limit: int = 60) -> str:
    selections = sorted(change_set.selections.values(), key=lambda sel: (sel.level, -sel.score, sel.path))
    if not selections:
        return "선택된 테스트 없음 — 이 변경에 도달하는 테스트를 찾지 못했습니다"
    lines = [f"{len(selections)}파일 · {change_set.selected_items()}/{change_set.total_items()}항목"]
    for sel in selections[:limit]:
        test = change_set.repo.test(sel.path)
        items = ", ".join(item.name for item in (test.items[:3] if test else []))
        lines.append(
            f"{MARK.get(sel.level, '·')} {sel.path}  L{sel.level} {LEVEL_LABEL.get(sel.level, '')}"
            f" · {sel.items}항목 · {sel.reason}"
            + (f"  ({items}{'…' if test and len(test.items) > 3 else ''})" if items else "")
        )
    if len(selections) > limit:
        lines.append(f"… {len(selections) - limit}개 더")
    return "\n".join(lines)
