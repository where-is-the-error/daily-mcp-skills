"""사람이 읽는 출력 — 모든 툴과 CLI 가 같은 문장을 쓰도록 한 곳에 모은다."""

from __future__ import annotations

from . import order as order_mod
from . import risks
from .differences import describe as describe_diff
from .differences import diff_change, summary as diff_summary
from .plan import Change, Plan, short

MAX_LINES = 14


def _header(plan: Plan) -> str:
    return (
        f"terraform {plan.terraform_version} · plan format {plan.format_version}"
        + (f" · {plan.timestamp}" if plan.timestamp else "")
    )


def _counts_line(plan: Plan) -> str:
    k = plan.by_kind()
    parts = []
    for kind, label in (("create", "생성"), ("update", "수정"), ("replace", "재생성"), ("delete", "삭제")):
        if k[kind]:
            parts.append(f"{label} {k[kind]}")
    if not parts:
        parts.append("변경 없음")
    return " · ".join(parts)


def summary(plan: Plan) -> str:
    k = plan.by_kind()
    total = len(plan.real_changes())
    lines = [
        "# plan 요약",
        f"- {_header(plan)}",
        f"- 바뀌는 리소스 **{total}개** — {_counts_line(plan)}",
        f"- 삭제되는 것 {len(plan.destructive())}개 · 그중 재생성 {k['replace']}개",
    ]
    if plan.errored:
        lines.append("- ⚠️ 이 plan 은 오류 상태로 끝났습니다(errored=true). apply 하지 마세요.")
    if not plan.complete:
        lines.append("- ⚠️ 불완전한 plan 입니다(complete=false). 일부 리소스만 담겨 있습니다.")
    providers = plan.provider_short()
    if providers:
        lines.append("- provider: " + ", ".join(f"{name} {count}" for name, count in providers.items()))
    types = plan.types()
    if types:
        top = ", ".join(f"{name} {count}" for name, count in list(types.items())[:6])
        lines.append(f"- 리소스 종류: {top}")
    if not plan.destructive():
        lines.append("- 지우거나 다시 만드는 리소스가 없습니다.")
    lines.append("")
    lines.append("다음: `risk` 로 apply 전에 봐야 할 것을 확인하세요.")
    return "\n".join(lines)


def changes(plan: Plan, action: str = "", kind_filter: str = "", max_items: int = 30) -> str:
    wanted = (kind_filter or "").strip().lower()
    selected = plan.real_changes()
    if wanted:
        selected = [c for c in selected if c.kind == wanted or c.type == wanted]
    if not selected:
        return f"해당하는 변경이 없습니다. (전체 {len(plan.changes)}건 중 실제 변경 {len(plan.real_changes())}건)\n액션: " \
               "create · update · replace · delete"
    limit = max(1, int(max_items))
    lines = [f"# 변경 {len(selected)}건" + (f" (필터: {wanted})" if wanted else "")]
    for change in selected[:limit]:
        head = f"{change.ref} {change.address} [{change.kind_label}]"
        if change.reason_label:
            head += f" — {change.reason_label}"
        lines.append(head)
        diffs = diff_change(change)
        counts = diff_summary(diffs)
        tail = []
        for key, label in (("changed", "바뀜"), ("added", "생김"), ("removed", "사라짐")):
            if counts[key]:
                tail.append(f"{label} {counts[key]}")
        if tail:
            lines.append("   " + " · ".join(tail))
        picked = [d for d in diffs if d.kind == "changed"][:2]
        for diff in picked:
            lines.append(f"   · {diff.line()}")
    if len(selected) > limit:
        lines.append(f"… {len(selected) - limit}건 더 있습니다 (max_items 늘리기)")
    return "\n".join(lines)


def diff(plan: Plan, address: str, max_items: int = MAX_LINES) -> str:
    matching = plan.find(address)
    if not matching:
        addresses = ", ".join(c.address for c in plan.real_changes()[:5])
        return f"'{address}' 를 찾지 못했습니다. 예: {addresses}"
    change: Change = matching[0]
    diffs = diff_change(change)
    lines = [f"# {change.address} [{change.kind_label}] {change.ref}"]
    if change.reason_label:
        lines.append(f"사유: {change.reason_label}")
    if change.replace_paths:
        lines.append("재생성 이유: " + ", ".join(".".join(p) for p in change.replace_paths[:4]))
    lines.append("")
    if not diffs:
        lines.append(describe_diff(change)[0])
    else:
        counts = diff_summary(diffs)
        lines.append(
            f"바뀜 {counts['changed']} · 생김 {counts['added']} · 사라짐 {counts['removed']}"
            + (f" · 적용 후 결정 {counts['unknown']}" if counts["unknown"] else "")
        )
        lines.extend(describe_diff(change, max_items=max_items))
    masked = [d.path for d in diffs if d.sensitive]
    if masked:
        lines.append("")
        lines.append("가린 값: " + ", ".join(masked[:6]) + " — plan 파일에는 그대로 들어 있으니 공유 전에 `redact` 하세요.")
    return "\n".join(lines)


def risk(plan: Plan, severity: str = "", max_items: int = MAX_LINES) -> str:
    items = risks.findings(plan)
    wanted = (severity or "").strip()
    if wanted:
        order = list(risks.SEVERITY_ORDER)
        if wanted not in order:
            return "severity 는 치명 · 심각 · 보통 · 참고 중 하나입니다."
        limit_index = order.index(wanted)
        items = [i for i in items if risks.SEVERITY_ORDER[i.severity] <= limit_index]
    lines = [
        "# apply 전 확인",
        risks.verdict_line(items) if items else "판정 **통과** · 걸린 규칙 없음",
    ]
    if not items:
        lines.append("")
        lines.append("이 plan 에서 새로 생기는 삭제·재생성·공개 설정을 찾지 못했습니다.")
        lines.append("(이미 있던 위험은 이 도구가 다시 경고하지 않습니다 — 바뀐 것만 봅니다.)")
        return "\n".join(lines)
    limit = max(1, int(max_items))
    for finding in items[:limit]:
        lines.append("")
        lines.append(f"**{finding.severity} · {finding.title}** — `{finding.address}`")
        lines.append(f"- 근거: {finding.detail}")
        lines.append(f"- 고치기: {finding.fix}")
    if len(items) > limit:
        lines.append("")
        lines.append(f"… {len(items) - limit}건 더 있습니다.")
    return "\n".join(lines)


def order(plan: Plan) -> str:
    return "\n".join(["# 적용 순서", ""] + order_mod.describe(plan))


def rollback(plan: Plan) -> str:
    from . import rollback as rollback_mod

    return "\n".join(["# 되돌리기 계획", f"- {rollback_mod.summary_line(plan)}", ""] + rollback_mod.steps(plan))


def quick(plan: Plan) -> str:
    """한 화면 요약 — 요약 + 판정 + 가장 센 것 3개."""
    items = risks.findings(plan)
    lines = [
        f"**{_counts_line(plan)}** · 바뀌는 리소스 {len(plan.real_changes())}개",
        risks.verdict_line(items),
    ]
    for finding in items[:3]:
        lines.append(f"- [{finding.severity}] {finding.title} — {finding.address} ({short(finding.detail, 50)})")
    if not items:
        lines.append("- apply 전에 새로 생기는 위험은 없습니다.")
    return "\n".join(lines)
