"""정리 계획 — 고칠 수 있는 것만, 되돌릴 수 있는 순서로.

계획은 **값을 지어내지 않는다.** 확신이 없는 변환(앞자리 0 폭 맞추기 같은 것)은
`confidence`를 낮게 달고 `needs_review`로 표시해, 적용 뒤에도 사람이 확인할 수 있게 한다.
단위를 떼는 변환은 단위를 `<열>_단위` 열로 옮겨 정보를 잃지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rules import Finding

ORDER = {
    "strip_quotes": 0,
    "normalize": 1,
    "drop_rows": 2,
    "quarantine_rows": 2.5,
    "fill_down": 3,
    "pad_leading_zeros": 4,
    "to_number": 5,
    "to_iso_date": 6,
    "format_phone": 7,
    "drop_columns": 8,
    "dedupe_rows": 9,
}

KIND_LABELS = {
    "strip_quotes": "따옴표 제거",
    "normalize": "공백·전각 문자 정리",
    "drop_rows": "행 빼기",
    "quarantine_rows": "칸이 밀린 행 격리",
    "fill_down": "병합 칸 채우기",
    "pad_leading_zeros": "앞자리 0 되살리기",
    "to_number": "숫자로 바꾸기",
    "to_iso_date": "날짜를 YYYY-MM-DD로",
    "format_phone": "전화번호 형식 통일",
    "drop_columns": "빈 열 빼기",
    "dedupe_rows": "중복 행 합치기",
}

REVIEW_KINDS = ("rename_columns", "keep")


@dataclass
class Action:
    id: str
    kind: str
    params: dict
    reason: list[str]
    target: str
    affects: int = 0
    confidence: float = 1.0
    needs_review: bool = False
    note: str = ""

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "label": self.label, "params": self.params,
                "reason": self.reason, "target": self.target, "affects": self.affects,
                "confidence": self.confidence, "needs_review": self.needs_review, "note": self.note}


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    review: list[Finding] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    @property
    def changes(self) -> int:
        return sum(a.affects for a in self.actions)

    def as_dict(self) -> dict:
        return {"actions": [a.as_dict() for a in self.actions],
                "review": [f.as_dict() for f in self.review],
                "affects": self.changes}


def _column_index(table, name: str) -> int:
    names = table.column_names
    if name not in names:
        raise ValueError(f"'{name}' 열이 없습니다. 있는 열: {', '.join(names)}")
    return names.index(name)


def _estimate(table, kind: str, params: dict) -> int:
    if kind in ("drop_rows", "quarantine_rows"):
        return len(params.get("rows", []))
    if kind == "dedupe_rows":
        seen = set()
        extra = 0
        for row in table.data_rows:
            key = tuple(row.get(i).strip() for i in range(table.width))
            if key in seen:
                extra += 1
            seen.add(key)
        return extra
    if kind == "strip_quotes":
        return int(table.meta.get("stray_quotes") or 1)
    if kind == "fill_down":
        return len(params.get("ranges", []))
    column = params.get("column")
    if column is None:
        return sum(1 for row in table.rows for cell in row.cells if str(cell) != str(cell).strip())
    index = _column_index(table, column)
    if kind == "to_number":
        return sum(1 for i, row in enumerate(table.rows)
                   if table.value(i, index).kind in ("int", "float", "currency", "percent", "quantity")
                   and (table.value(i, index).flags or table.value(i, index).kind != "text"))
    if kind == "to_iso_date":
        return sum(1 for i, _ in enumerate(table.rows) if table.value(i, index).kind in ("date", "datetime"))
    if kind == "format_phone":
        return sum(1 for i, _ in enumerate(table.rows) if table.value(i, index).kind == "phone")
    if kind == "normalize":
        return sum(1 for i, _ in enumerate(table.rows)
                   if set(table.value(i, index).flags) & {"pad", "fullwidth"})
    if kind == "pad_leading_zeros":
        width = int(params.get("width", 0))
        return sum(1 for i, _ in enumerate(table.rows)
                   if table.value(i, index).kind in ("int",) and len(str(abs(int(table.value(i, index).value)))) < width)
    if kind == "drop_columns":
        return 1
    return 0


def build_plan(table, findings: list[Finding], only: tuple[str, ...] = ()) -> Plan:
    """발견에서 실행 가능한 것만 골라 순서를 정한다."""
    plan = Plan(rules=[f.rule for f in findings])
    taken: dict[tuple, Action] = {}

    for finding in findings:
        if only and finding.rule not in only:
            continue
        fix = finding.fix or {}
        kind = fix.get("kind")
        if not kind or kind in REVIEW_KINDS:
            if finding.severity in ("error", "warn"):
                plan.review.append(finding)
            continue
        if kind not in ORDER:
            plan.review.append(finding)
            continue

        params = {k: v for k, v in fix.items() if k != "kind"}
        if kind in ("drop_rows", "quarantine_rows"):
            params["rows"] = list(params.get("rows", finding.rows))
            if not params["rows"]:
                continue
        if kind == "fill_down":
            params["ranges"] = list(table.meta.get("merged") or [])
        if kind == "strip_quotes":
            params["rows"] = [r.ref for r in table.rows]

        key = (kind, params.get("column"), tuple(params.get("rows", []))[:1], tuple(params.get("ranges", []))[:1])
        if kind in ("drop_rows", "quarantine_rows", "dedupe_rows", "strip_quotes", "fill_down"):
            key = (kind,)
        if key in taken:
            action = taken[key]
            if kind in ("drop_rows", "quarantine_rows"):
                merged = list(action.params.get("rows", []))
                for ref in params.get("rows", []):
                    if ref not in merged:
                        merged.append(ref)
                action.params["rows"] = merged
                action.affects = len(merged)
                action.target = _target(kind, action.params)
            if finding.rule not in action.reason:
                action.reason.append(finding.rule)
            continue

        action = Action(
            id=f"a{len(plan.actions) + 1}",
            kind=kind,
            params=params,
            reason=[finding.rule],
            target=_target(kind, params),
            affects=_estimate(table, kind, params),
            confidence=_confidence(kind, finding),
            needs_review=kind == "pad_leading_zeros",
        )
        if kind == "to_number" and params.get("column"):
            index = _column_index(table, params["column"])
            units = {table.value(i, index).note for i in range(len(table.rows))
                     if table.value(i, index).kind in ("quantity", "percent", "currency") and table.value(i, index).note}
            if units:
                action.note = f"단위 {', '.join(sorted(units))}는 '{params['column']}_단위' 열로 옮깁니다."
        if kind == "pad_leading_zeros":
            action.note = (f"자릿수 {params.get('width')}로 맞추는 것은 추정입니다. 원래 0이 있었는지 원본과 대조하세요.")
        plan.actions.append(action)
        taken[key] = action

    plan.actions.sort(key=lambda a: (ORDER.get(a.kind, 99), a.id))
    for number, action in enumerate(plan.actions, 1):
        action.id = f"a{number}"
    # 고칠 수 없는 심각한 것은 '사람이 봐야 함'으로 남긴다
    for finding in findings:
        if finding.severity == "error" and not (finding.fix and finding.fix.get("kind") in ORDER):
            if finding not in plan.review:
                plan.review.append(finding)
    return plan


def _target(kind: str, params: dict) -> str:
    column = params.get("column")
    if kind in ("drop_rows", "quarantine_rows"):
        rows = params.get("rows", [])
        return f"행 {len(rows)}개({', '.join(rows[:4])}{'…' if len(rows) > 4 else ''})"
    if kind == "fill_down":
        return f"병합 칸 {len(params.get('ranges', []))}곳"
    if kind == "dedupe_rows":
        return "완전히 같은 행"
    if kind == "strip_quotes":
        return "따옴표가 홀로 있는 칸"
    if kind == "drop_columns":
        return f"'{column}' 열"
    if kind == "pad_leading_zeros":
        return f"'{column}' 열 {params.get('width')}자리"
    return f"'{column}' 열"


def _confidence(kind: str, finding: Finding) -> float:
    if kind == "pad_leading_zeros":
        return 0.55
    if kind == "to_iso_date":
        return 0.9 if "YY" in finding.detail else 1.0
    if kind == "format_phone":
        return 0.95
    if kind == "to_number":
        return 0.95
    return 1.0
