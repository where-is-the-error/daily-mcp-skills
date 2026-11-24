"""규칙 — 표를 쓰기 전에 확인할 것들.

규칙은 두 종류다.

* **구조** — 인코딩·구분자·머리글·행 역할. 잘못 읽으면 그 뒤 계산이 전부 틀어진다.
* **값** — 앞자리 0, 날짜 표기, 단위, 전각 숫자. 읽기는 됐지만 합계·정렬·조인에서 깨진다.

모든 규칙은 `Finding` 하나를 돌려주고, 고칠 수 있는 것은 `fix`(무엇을 할지)를 함께 준다.
고치기 전에 보여 주는 것이 목적이므로 판정만 하고 값을 바꾸지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import KIND_LABELS, header_hint, parse_value

SEVERITIES = ("error", "warn", "info")
SEVERITY_LABELS = {"error": "치명", "warn": "주의", "info": "참고"}

RULES: dict[str, dict] = {
    "no-rows": {"title": "읽을 행이 없음", "why": "빈 파일이거나 구분자를 잘못 골랐습니다.", "action": None},
    "cp949-encoding": {"title": "UTF-8이 아님", "why": "엑셀 기본 저장은 CP949입니다. 다른 도구에서 글자가 깨집니다.", "action": None},
    "bom-prefix": {"title": "BOM이 붙어 있음", "why": "첫 칸 이름 앞에 보이지 않는 문자가 붙어 첫 열 이름이 어긋납니다.", "action": None},
    "line-ending-mixed": {"title": "줄바꿈 문자가 섞임", "why": "CRLF와 LF가 섞이면 일부 도구가 한 줄로 붙여 읽습니다.", "action": None},
    "preamble-rows": {"title": "머리글 앞 제목·단위 줄", "why": "데이터로 읽으면 칸이 한 칸씩 밀립니다.", "action": None},
    "multi-row-header": {"title": "두 줄 머리글", "why": "위아래를 합쳐야 열 이름이 완성됩니다.", "action": None},
    "ragged-row": {"title": "칸 수가 다른 행", "why": "따옴표 없는 쉼표·줄바꿈 때문에 열이 밀렸습니다.", "action": "drop_or_fix"},
    "stray-quote": {"title": "따옴표 짝 안 맞음", "why": "따옴표가 홀로 있으면 그 뒤 행이 한 칸으로 붙습니다.", "action": "strip_quotes"},
    "duplicate-header": {"title": "같은 열 이름", "why": "이름이 같으면 조인·선택에서 엉뚱한 열을 고릅니다.", "action": "rename_columns"},
    "unnamed-column": {"title": "이름 없는 열", "why": "머리글 칸이 비어 있어 열1 같은 임시 이름이 붙었습니다.", "action": "rename_columns"},
    "empty-column": {"title": "전부 빈 열", "why": "값이 없으면 합계·피벗에서 빈 열만 늘어납니다.", "action": "drop_columns"},
    "constant-column": {"title": "값이 하나뿐인 열", "why": "상수 열은 필터·피벗에서 의미가 없습니다.", "action": None},
    "subtotal-row": {"title": "데이터 사이 소계·합계 행", "why": "이 행을 그대로 더하면 합계가 두 배가 됩니다.", "action": "drop_rows"},
    "trailing-total": {"title": "맨 끝 합계 행", "why": "합계 행은 데이터가 아닙니다. 지우거나 따로 보관하세요.", "action": "drop_rows"},
    "section-row": {"title": "데이터 사이 구역 제목", "why": "한 칸만 채워진 행이라 정렬하면 엉뚱한 곳으로 갑니다.", "action": "drop_rows"},
    "footnote-row": {"title": "각주 행", "why": "값이 아니라 설명입니다.", "action": "drop_rows"},
    "blank-row": {"title": "빈 행", "why": "빈 행은 필터·정렬에서 구분선처럼 남습니다.", "action": "drop_rows"},
    "mixed-type-column": {"title": "숫자와 글자가 섞인 열", "why": "합계·정렬이 조용히 틀립니다(글자는 0으로 계산됨).", "action": None},
    "text-in-numeric-column": {"title": "숫자 열 안의 글자", "why": "거의 다 숫자인 열에 글자가 몇 개 있으면 그 행만 합계에서 빠집니다.", "action": None},
    "id-in-text": {"title": "이름 칸에 코드가 붙음", "why": "한 칸에 이름과 코드가 같이 있으면 이름으로 조인·정렬할 수 없습니다.", "action": None},
    "leading-zero-risk": {"title": "앞자리 0이 사라질 수 있는 열", "why": "우편번호·코드를 숫자로 읽으면 00123이 123이 됩니다.", "action": "pad_leading_zeros"},
    "leading-zero-kept": {"title": "앞자리 0이 있는 코드 열", "why": "지금은 살아 있지만 숫자로 바꾸는 순간 사라집니다.", "action": None},
    "phone-inconsistent": {"title": "전화번호 표기가 제각각", "why": "하이픈·국가번호·자릿수가 섞이면 문자 발송이 실패합니다.", "action": "format_phone"},
    "date-format-mixed": {"title": "날짜 표기가 섞임", "why": "2024.1.5와 2024-01-05가 섞이면 정렬이 글자 순서가 됩니다.", "action": "to_iso_date"},
    "date-invalid": {"title": "달력에 없는 날짜", "why": "2024-02-31 같은 값은 계산에서 조용히 빠집니다.", "action": None},
    "thousands-separator": {"title": "천 단위 쉼표", "why": "CSV에서 쉼표가 붙은 숫자는 엑셀에서 글자로 들어옵니다.", "action": "to_number"},
    "unit-in-cell": {"title": "값 안에 단위", "why": "'12.5㎡'는 숫자가 아니라 글자입니다. 합계가 안 됩니다.", "action": "to_number"},
    "percent-as-text": {"title": "백분율이 글자", "why": "%가 붙은 값은 0.123이 아니라 '12.3%' 글자입니다.", "action": "to_number"},
    "accounting-negative": {"title": "괄호 음수", "why": "(1,234)는 -1234입니다. 그대로 두면 양수로 읽힙니다.", "action": "to_number"},
    "fullwidth-digit": {"title": "전각 숫자", "why": "한글 문서에서 붙여넣으면 １２３이 됩니다. 숫자로 안 읽힙니다.", "action": "normalize"},
    "whitespace-padding": {"title": "앞뒤 공백", "why": "' 서울'과 '서울'은 조인에서 다른 값입니다.", "action": "normalize"},
    "duplicate-rows": {"title": "완전히 같은 행", "why": "중복 행은 합계를 부풀립니다.", "action": "dedupe_rows"},
    "duplicate-key": {"title": "키가 중복", "why": "키가 겹치면 조인에서 행이 불어납니다.", "action": None},
    "merged-cell-gap": {"title": "병합 칸의 빈 자리", "why": "병합된 칸은 첫 칸에만 값이 있어 나머지가 빈칸으로 읽힙니다.", "action": "fill_down"},
    "formula-missing": {"title": "계산값이 저장되지 않은 수식", "why": "엑셀에서 한 번도 열지 않은 파일은 수식 결과가 비어 있습니다.", "action": None},
}


@dataclass
class Finding:
    rule: str
    severity: str
    title: str
    detail: str
    count: int = 1
    rows: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    fix: dict | None = None
    confidence: float = 1.0

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, self.severity)

    def as_dict(self) -> dict:
        return {
            "rule": self.rule, "severity": self.severity, "title": self.title,
            "detail": self.detail, "count": self.count, "rows": self.rows,
            "columns": self.columns, "examples": self.examples, "fix": self.fix,
        }


def _finding(rule: str, detail: str, severity: str | None = None, **kwargs) -> Finding:
    meta = RULES.get(rule, {"title": rule, "action": None})
    return Finding(rule=rule, severity=severity or ("warn" if meta.get("action") else "info"),
                   title=meta.get("title", rule), detail=detail, **kwargs)


def _sample(items: list[str], limit: int = 5) -> list[str]:
    out = items[:limit]
    if len(items) > limit:
        out.append(f"… 외 {len(items) - limit}건")
    return out


def _column_rows(table, index: int):
    """한 열의 (행 번호, 행, 값) — 칸이 밀린 행은 어느 열의 값인지 알 수 없어 뺀다."""
    return [(i, row, table.value(i, index)) for i, row in enumerate(table.rows)
            if not (row.raw_width and row.raw_width != table.width)]


# ------------------------------------------------------------------ 구조 규칙
def check_structure(table) -> list[Finding]:
    out: list[Finding] = []
    if not table.rows or not table.columns:
        return [_finding("no-rows", "파일에서 표를 찾지 못했습니다.", "error")]

    if not table.encoding.startswith("utf"):
        out.append(_finding("cp949-encoding",
                            f"{table.encoding.upper()}로 읽었습니다(확신 {table.encoding_confidence:.2f}). "
                            f"UTF-8로 다시 저장하면 다른 도구에서도 안 깨집니다.",
                            "info"))
    if table.meta.get("bom"):
        out.append(_finding("bom-prefix", f"{table.meta['bom']}을(를) 떼고 읽었습니다. 파일 자체는 아직 BOM이 있습니다.", "info"))

    endings = table.meta.get("line_endings") or {}
    if endings.get("mixed"):
        out.append(_finding("line-ending-mixed",
                            f"줄바꿈이 {'+'.join(endings.get('kinds', []))}로 섞여 있습니다 "
                            f"(CRLF {endings.get('crlf', 0)} / LF {endings.get('lf', 0)}).", "warn"))

    if table.preamble:
        out.append(_finding("preamble-rows",
                            f"머리글 위 {len(table.preamble)}줄을 제목·단위 줄로 보고 뺐습니다: "
                            '{0}'.format(', '.join(_sample([r.get(0).strip() for r in table.preamble], 3))),
                            "info", rows=[r.ref for r in table.preamble]))
    if table.header_span >= 2:
        out.append(_finding("multi-row-header", f"머리글 {table.header_span}줄을 '상위>하위'로 합쳤습니다.", "info"))

    # 칸 수가 다른 행
    width = table.width
    ragged = [(i, row) for i, row in enumerate(table.rows) if row.kind == "data" and row.raw_width and row.raw_width != width]
    if ragged:
        out.append(_finding("ragged-row",
                            f"칸 수가 {width}개가 아닌 행이 {len(ragged)}개입니다. 쉼표가 따옴표 없이 들어갔을 수 있습니다.",
                            "error",
                            count=len(ragged), rows=[r.ref for _, r in ragged[:20]],
                            examples=_sample([f"{r.ref}: {r.raw_width}칸 — " + " | ".join(c.strip() for c in r.cells[:4])
                                              for _, r in ragged]),
                            fix={"kind": "quarantine_rows", "rows": [r.ref for _, r in ragged]}))

    if table.meta.get("stray_quotes"):
        out.append(_finding("stray-quote", f"따옴표 짝이 맞지 않는 칸이 {table.meta['stray_quotes']}곳 있습니다.", "warn",
                            count=int(table.meta["stray_quotes"]), fix={"kind": "strip_quotes"}))

    if table.sheet:
        merged = table.meta.get("merged") or []
        if merged:
            out.append(_finding("merged-cell-gap",
                                f"병합된 칸이 {len(merged)}곳입니다. 병합은 첫 칸에만 값이 있어 나머지 칸이 빈칸입니다.",
                                "warn", count=len(merged), examples=_sample(merged),
                                fix={"kind": "fill_down"}))
    if table.meta.get("formula_missing"):
        out.append(_finding("formula-missing",
                            f"수식 {table.meta['formula_missing']}칸에 계산값이 저장되어 있지 않습니다.", "warn",
                            count=int(table.meta["formula_missing"])))
    return out


def check_columns(table) -> list[Finding]:
    out: list[Finding] = []
    names = table.column_names
    dupes = sorted({re.sub(r"_\d+$", "", n) for n in names if re.search(r"_\d+$", n)})
    if dupes:
        out.append(_finding("duplicate-header",
                            f"같은 이름의 열이 있어 뒤엣것에 번호를 붙였습니다: {', '.join(dupes)}", "warn",
                            columns=dupes, fix={"kind": "rename_columns"}))

    unnamed = [c.name for c in table.columns if re.fullmatch(r"열\d+", c.name)]
    if unnamed:
        out.append(_finding("unnamed-column", f"이름이 없는 열 {len(unnamed)}개: {_sample(unnamed)}", "warn",
                            columns=unnamed, fix={"kind": "rename_columns"}))

    stats = table.stats()
    for stat in stats:
        if stat.non_empty == 0:
            out.append(_finding("empty-column", f"'{stat.name}' 열이 전부 비어 있습니다.", "warn",
                                columns=[stat.name], fix={"kind": "drop_columns", "column": stat.name}))
        elif len(stat.distinct) == 1 and stat.non_empty >= 3:
            out.append(_finding("constant-column", f"'{stat.name}' 열은 값이 하나뿐입니다: {stat.examples.get(stat.kind, '')}", "info",
                                columns=[stat.name]))
    return out


def check_rows(table) -> list[Finding]:
    out: list[Finding] = []
    rows = table.rows
    subtotal = [r for r in rows if r.kind == "subtotal"]
    trailing = [r for r in subtotal if rows.index(r) == len(rows) - 1]
    middle = [r for r in subtotal if r not in trailing]
    if middle:
        out.append(_finding("subtotal-row",
                            f"데이터 중간에 소계·합계 행이 {len(middle)}개 있습니다: "
                            '{0}'.format(', '.join(_sample([f'{r.ref} {r.label}' for r in middle]))),
                            "error", count=len(middle), rows=[r.ref for r in middle],
                            examples=_sample([f"{r.ref}: {r.label}" for r in middle]),
                            fix={"kind": "drop_rows", "rows": [r.ref for r in middle]}))
    if trailing:
        out.append(_finding("trailing-total",
                            f"맨 끝에 합계 행 {len(trailing)}개가 있습니다: " + ', '.join(_sample([f'{r.ref} {r.label}' for r in trailing])),
                            "info", count=len(trailing), rows=[r.ref for r in trailing],
                            fix={"kind": "drop_rows", "rows": [r.ref for r in trailing]}))
    sections = [r for r in rows if r.kind == "section"]
    if sections:
        out.append(_finding("section-row", f"구역 제목 행이 {len(sections)}개: " + ', '.join(_sample([f'{r.ref} {r.label}' for r in sections])),
                            "warn", count=len(sections), rows=[r.ref for r in sections],
                            fix={"kind": "drop_rows", "rows": [r.ref for r in sections]}))
    footnotes = [r for r in rows if r.kind == "footnote"]
    if footnotes:
        out.append(_finding("footnote-row", f"각주 행이 {len(footnotes)}개: " + ', '.join(_sample([f'{r.ref} {r.label}' for r in footnotes])),
                            "info", count=len(footnotes), rows=[r.ref for r in footnotes],
                            fix={"kind": "drop_rows", "rows": [r.ref for r in footnotes]}))
    blanks = [r for r in rows if r.kind == "blank"]
    if blanks:
        out.append(_finding("blank-row", f"빈 행이 {len(blanks)}개입니다.", "info", count=len(blanks),
                            rows=[r.ref for r in blanks[:20]], fix={"kind": "drop_rows", "rows": [r.ref for r in blanks]}))
    return out


def check_values(table) -> list[Finding]:
    out: list[Finding] = []
    stats = table.stats()
    for stat in stats:
        if stat.non_empty == 0:
            continue
        hints = header_hint(stat.name)
        name = stat.name

        if stat.kind == "mixed":
            out.append(_finding("mixed-type-column",
                                f"'{name}' 열에 {KIND_LABELS['text']} {stat.kinds.get('text', 0)}칸과 "
                                f"숫자 {sum(stat.kinds.get(k, 0) for k in ('int', 'float', 'currency', 'percent', 'quantity'))}칸이 섞여 있습니다.",
                                "warn", columns=[name], count=stat.non_empty,
                                examples=_sample([f"{k}: {v}칸" for k, v in sorted(stat.kinds.items(), key=lambda kv: -kv[1])])))

        if stat.kind == "text" and stat.non_empty >= 3:
            pattern = re.compile(r"\(\s*(\d{5,})\s*\)\s*$")
            hits = [row.get(stat.index) for row in table.rows
                    if pattern.search(row.get(stat.index)) and not (row.raw_width and row.raw_width != table.width)]
            if len(hits) >= max(2, int(stat.non_empty * 0.5)):
                out.append(_finding("id-in-text",
                                    f"'{name}' 열 {len(hits)}칸이 '이름 (코드)' 모양입니다(예: {hits[0][:30]}). "
                                    f"이름과 코드를 나누면 조인·정렬이 됩니다.",
                                    "warn", columns=[name], count=len(hits), examples=hits[:3]))

        if stat.kind != "mixed":
            numeric = sum(stat.kinds.get(k, 0) for k in ("int", "float", "currency", "percent", "quantity"))
            texts = [row.get(stat.index) for _, row, value in _column_rows(table, stat.index)
                     if value.kind == "text" and row.get(stat.index).strip()]
            if numeric and 0 < len(texts) <= max(3, int(stat.non_empty * 0.05)) and numeric / max(1, stat.non_empty - len(texts)) >= 0.95:
                out.append(_finding("text-in-numeric-column",
                                    f"'{name}' 열은 숫자 {numeric}칸인데 글자 {len(texts)}칸이 섞여 있습니다: "
                                    + ", ".join(f"'{t[:20]}'" for t in texts[:4])
                                    + ". 이 행만 합계에서 조용히 빠집니다.",
                                    "warn", columns=[name], count=len(texts),
                                    examples=[f"{t[:40]}" for t in texts[:5]]))

        # 앞자리 0 — 코드(0으로 시작)와 숫자가 섞였고, 숫자가 더 짧으면 0이 사라진 것이다
        code_widths = [len(str(value.value)) for _, _, value in _column_rows(table, stat.index)
                       if value.kind == "code" and isinstance(value.value, str)]
        int_widths = [len(str(abs(int(value.value)))) for _, _, value in _column_rows(table, stat.index)
                      if value.kind == "int" and isinstance(value.value, int)]
        if code_widths and int_widths and min(int_widths) < max(code_widths) and ("code" in hints or "id" in hints):
            width_ = max(code_widths)
            out.append(_finding("leading-zero-risk",
                                f"'{name}' 열에 0으로 시작하는 코드 {len(code_widths)}칸과 숫자 {len(int_widths)}칸이 섞여 있습니다"
                                f"(코드 {max(code_widths)}자리, 숫자 {min(int_widths)}~{max(int_widths)}자리). "
                                f"{width_}자리로 맞추면 사라진 0을 되살릴 수 있습니다.",
                                "error", columns=[name], count=len(int_widths),
                                examples=_sample(list(stat.examples.values())),
                                fix={"kind": "pad_leading_zeros", "column": name, "width": width_}))
        elif stat.flags.get("leading_zero"):
            out.append(_finding("leading-zero-kept",
                                f"'{name}' 열의 {stat.flags['leading_zero']}칸이 0으로 시작하는 코드입니다"
                                f"(예: {stat.examples.get('code', '')}). 숫자 열로 바꾸면 0이 사라집니다.",
                                "info", columns=[name], count=stat.flags["leading_zero"]))
        elif stat.kinds.get("int") and ("code" in hints or "id" in hints) and len(stat.widths) >= 2:
            widths = dict(sorted(stat.widths.items()))
            top_width = max(widths, key=lambda w: widths[w])
            cut = {w: n for w, n in widths.items() if w < top_width}
            if cut:
                out.append(_finding("leading-zero-risk",
                                    f"'{name}' 열은 코드로 보이는데 자릿수가 {min(widths)}~{max(widths)}로 섞여 있습니다"
                                    f"({', '.join(f'{w}자리 {n}칸' for w, n in sorted(widths.items()))}). "
                                    f"{top_width}자리로 맞추면 앞자리 0을 되살릴 수 있습니다.",
                                    "error", columns=[name], count=sum(cut.values()),
                                    examples=_sample(list(stat.examples.values())),
                                    fix={"kind": "pad_leading_zeros", "column": name, "width": top_width}))

        # 전화번호
        if stat.kinds.get("phone"):
            hyphen_variants = set()
            country = 0
            short = 0
            for _, row, value in _column_rows(table, stat.index):
                if value.kind != "phone":
                    continue
                raw = value.raw
                hyphen_variants.add(raw.count("-"))
                if raw.startswith("+82"):
                    country += 1
                if len(value.value) < 9:
                    short += 1
            if len(hyphen_variants) > 1 or country or short:
                out.append(_finding("phone-inconsistent",
                                    f"'{name}' 열 전화번호 표기가 섞였습니다(하이픈 {sorted(hyphen_variants)}종"
                                    f"{', +82 ' + str(country) + '건' if country else ''}"
                                    f"{', 9자리 미만 ' + str(short) + '건' if short else ''}).",
                                    "warn", columns=[name], count=stat.kinds["phone"],
                                    examples=_sample([row.get(stat.index) for _, row, v in _column_rows(table, stat.index)
                                                      if v.kind == "phone"]),
                                    fix={"kind": "format_phone", "column": name}))

        # 날짜
        if len(stat.date_patterns) >= 2:
            out.append(_finding("date-format-mixed",
                                f"'{name}' 열 날짜 표기가 {len(stat.date_patterns)}종입니다: "
                                + ", ".join(f"{p} {n}칸" for p, n in sorted(stat.date_patterns.items(), key=lambda kv: -kv[1])),
                                "warn", columns=[name], count=sum(stat.date_patterns.values()),
                                fix={"kind": "to_iso_date", "column": name}))
        if stat.flags.get("invalid_date"):
            out.append(_finding("date-invalid", f"'{name}' 열에 달력에 없는 날짜가 {stat.flags['invalid_date']}칸 있습니다.",
                                "warn", columns=[name], count=stat.flags["invalid_date"]))

        # 숫자 표기
        if stat.flags.get("thousands"):
            out.append(_finding("thousands-separator",
                                f"'{name}' 열 {stat.flags['thousands']}칸에 천 단위 쉼표가 있습니다. "
                                f"CSV에서는 따옴표로 감싸야 하고, 엑셀은 글자로 읽습니다.",
                                "warn", columns=[name], count=stat.flags["thousands"],
                                examples=_sample(list(stat.examples.values())),
                                fix={"kind": "to_number", "column": name}))
        if stat.flags.get("unit_in_cell") and stat.kind != "mixed":
            units = ", ".join(f"{u} {n}" for u, n in sorted(stat.units.items(), key=lambda kv: -kv[1])) or "%"
            out.append(_finding("unit-in-cell",
                                f"'{name}' 열 값 안에 단위가 붙어 있습니다({units}). 숫자만 남기면 합계·정렬이 됩니다.",
                                "warn" if stat.kind in ("quantity", "text") else "info",
                                columns=[name], count=stat.flags["unit_in_cell"],
                                fix={"kind": "to_number", "column": name}))
        if stat.kinds.get("percent"):
            out.append(_finding("percent-as-text",
                                f"'{name}' 열 {stat.kinds['percent']}칸이 '12.3%' 글자입니다(0.123이 아님).",
                                "info", columns=[name], count=stat.kinds["percent"],
                                fix={"kind": "to_number", "column": name}))
        if stat.flags.get("accounting"):
            out.append(_finding("accounting-negative",
                                f"'{name}' 열 {stat.flags['accounting']}칸이 (1,234) 괄호 음수입니다.",
                                "info", columns=[name], count=stat.flags["accounting"],
                                fix={"kind": "to_number", "column": name}))
        if stat.flags.get("fullwidth"):
            out.append(_finding("fullwidth-digit",
                                f"'{name}' 열 {stat.flags['fullwidth']}칸에 전각 숫자/기호가 있습니다.",
                                "warn", columns=[name], count=stat.flags["fullwidth"],
                                fix={"kind": "normalize", "column": name}))
        if stat.flags.get("pad"):
            out.append(_finding("whitespace-padding",
                                f"'{name}' 열 {stat.flags['pad']}칸에 앞뒤 공백·전각 공백이 있습니다.",
                                "warn", columns=[name], count=stat.flags["pad"],
                                fix={"kind": "normalize", "column": name}))

    # 중복 행
    seen: dict[tuple, list[str]] = {}
    for row in table.data_rows:
        key = tuple(value for _, value in [(i, row.get(i).strip()) for i in range(table.width)])
        seen.setdefault(key, []).append(row.ref)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if dupes:
        extra = sum(len(v) - 1 for v in dupes.values())
        out.append(_finding("duplicate-rows",
                            f"완전히 같은 행이 {len(dupes)}쌍({extra}행 더)입니다.",
                            "warn", count=extra, rows=[ref for v in dupes.values() for ref in v[1:]],
                            examples=_sample([" · ".join(v) for v in dupes.values()]),
                            fix={"kind": "dedupe_rows"}))
    return out


def check_key(table, key: str) -> list[Finding]:
    names = table.column_names
    if key not in names:
        raise ValueError(f"'{key}' 열이 없습니다. 있는 열: {', '.join(names)}")
    index = names.index(key)
    counts: dict[str, int] = {}
    for row in table.data_rows:
        value = row.get(index).strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    dupes = {k: n for k, n in counts.items() if n > 1}
    if not dupes:
        return []
    return [_finding("duplicate-key",
                     f"'{key}' 열에 같은 값이 여러 번 나옵니다: "
                     + ', '.join(_sample([f"{k} ×{n}" for k, n in sorted(dupes.items(), key=lambda kv: -kv[1])], 5)),
                     "error", columns=[key], count=sum(dupes.values()) - len(dupes))]


def check(table, key: str = "") -> list[Finding]:
    """모든 규칙을 돌려 심각한 것부터 정렬해 돌려준다."""
    findings = check_structure(table) + check_columns(table) + check_rows(table) + check_values(table)
    if key:
        findings.extend(check_key(table, key))
    rank = {name: i for i, name in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (rank.get(f.severity, 9), f.rule))
    return findings


def counts(findings: list[Finding]) -> dict[str, int]:
    out = {name: 0 for name in SEVERITIES}
    for finding in findings:
        out[finding.severity] = out.get(finding.severity, 0) + 1
    return out


def worst(findings: list[Finding]) -> str:
    counts_ = counts(findings)
    for name in SEVERITIES:
        if counts_.get(name):
            return name
    return "clean"
