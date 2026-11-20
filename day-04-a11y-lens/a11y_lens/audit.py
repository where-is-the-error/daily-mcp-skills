"""검사·집계·보고 — 한 페이지, 사이트 전체, 고친 뒤 확인까지.

세 가지가 이 모듈의 전부다.

1. `audit_page`  : 한 문서의 위반을 WCAG 조항과 함께, 원본 줄 번호로
2. `audit_site`  : 폴더 전체. 같은 템플릿에서 반복되는 위반은 **하나로 묶어** 센다
3. `verify`      : 고치기 전 기준선(baseline)과 지금을 비교 — 없어진 것/남은 것/새로 생긴 것
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import rules as rules_mod
from .htmltree import Document, norm, parse, parse_file
from .rules import IMPACT_LABEL, IMPACT_ORDER, IMPACT_WEIGHT, Rule, Violation, audit_document

__all__ = [
    "PageAudit",
    "SiteAudit",
    "load_document",
    "audit_page",
    "audit_site",
    "render_page",
    "render_site",
    "render_plan",
    "page_payload",
    "score_of",
    "grade_of",
    "LIMITS",
]

LIMITS = (
    "색 대비·터치 타깃 크기·포커스 순서·키보드 함정은 계산하지 않습니다 "
    "(레이아웃과 렌더링이 필요합니다). JS 로 그리는 내용은 정적 HTML 에 없으면 보이지 않습니다."
)


# ---------------------------------------------------------------- 불러오기
def load_document(source: str, base_dir: str | Path | None = None) -> Document:
    """경로·`file://`·원본 HTML 문자열 어느 쪽이든 문서로 만든다."""
    text = source.strip()
    if not text:
        raise ValueError("빈 입력입니다 — HTML 문자열이나 파일 경로를 주세요.")
    if text.startswith("file://"):
        return parse_file(Path(text[7:]))
    looks_like_html = text.startswith("<") or ("\n<" in text and "<" in text)
    if not looks_like_html:
        path = Path(text)
        if not path.is_absolute() and base_dir is not None:
            candidate = Path(base_dir) / text
            if candidate.exists():
                path = candidate
        if path.exists() and path.is_file():
            return parse_file(path)
        raise FileNotFoundError(f"파일을 찾지 못했습니다: {source}")
    return parse(text)


# ---------------------------------------------------------------- 점수
def score_of(violations: list[Violation]) -> tuple[int, str]:
    """100점에서 규칙마다 한 번씩 감점한다.

    같은 규칙이 12번 나와도 감점은 한 번 — 반복은 "고칠 곳 하나"라는 신호이고,
    점수는 "얼마나 여러 종류가 잘못됐는가"를 말해야 한다. (규칙 안에서 여러 번인 것은 개수로 보여 준다)
    """
    seen: set[str] = set()
    penalty = 0
    for violation in violations:
        if violation.rule.id in seen:
            continue
        seen.add(violation.rule.id)
        penalty += IMPACT_WEIGHT.get(violation.rule.impact, 4)
    score = max(0, 100 - penalty)
    return score, grade_of(score)


def grade_of(score: int) -> str:
    if score >= 90:
        return "양호"
    if score >= 70:
        return "주의"
    if score >= 40:
        return "위험"
    return "심각"


@dataclass
class PageAudit:
    path: str = ""
    title: str = ""
    lang: str = ""
    elements: int = 0
    violations: list[Violation] = field(default_factory=list)
    hidden_counts: dict[str, int] = field(default_factory=dict)
    score: int = 100
    grade: str = "양호"
    notes: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        result = {"critical": 0, "serious": 0, "moderate": 0}
        for violation in self.violations:
            result[violation.impact] = result.get(violation.impact, 0) + 1
        return result

    def rules_hit(self) -> list[str]:
        seen: list[str] = []
        for violation in self.violations:
            if violation.rule.id not in seen:
                seen.append(violation.rule.id)
        return seen

    def by_rule(self) -> dict[str, list[Violation]]:
        grouped: dict[str, list[Violation]] = {}
        for violation in self.violations:
            grouped.setdefault(violation.rule.id, []).append(violation)
        return grouped

    @property
    def worst(self) -> str:
        return min((v.rule.impact for v in self.violations), key=lambda i: IMPACT_ORDER.get(i, 9), default="none")

    def to_dict(self) -> dict:
        return page_payload(self)


def audit_page(
    source: str,
    rule_ids: list[str] | None = None,
    max_per_rule: int = 30,
    base_dir: str | Path | None = None,
) -> PageAudit:
    doc = load_document(source, base_dir=base_dir)
    selected = set(rule_ids or [])
    unknown = sorted(selected - {rule.id for rule in rules_mod.RULES})
    if unknown:
        raise ValueError(f"모르는 규칙: {', '.join(unknown)}")
    title = ""
    for node in doc.elements():
        if node.tag == "title":
            title = norm("".join(c.text for c in node.children if c.is_text))
            break
    html = doc.first("html")
    violations, hidden = audit_document(doc, rules=selected, max_per_rule=max_per_rule, file=doc.path)
    score, grade = score_of(violations)
    audit = PageAudit(
        path=doc.path or "(inline html)",
        title=title,
        lang=norm(html.get("lang")) if html is not None else "",
        elements=len(doc.elements()),
        violations=violations,
        hidden_counts=hidden,
        score=score,
        grade=grade,
    )
    if not doc.elements():
        audit.notes.append("요소를 하나도 찾지 못했습니다 — HTML 이 맞는지 확인해 주세요.")
    return audit


# ---------------------------------------------------------------- 사이트
@dataclass
class Group:
    fingerprint: str
    rule: Rule
    impact: str
    count: int
    pages: list[str]
    sample: Violation

    def __post_init__(self) -> None:
        pass


@dataclass
class SiteAudit:
    root: str
    pages: list[PageAudit] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def total_violations(self) -> int:
        return sum(len(page.violations) for page in self.pages)

    def counts(self) -> dict[str, int]:
        result = {"critical": 0, "serious": 0, "moderate": 0}
        for page in self.pages:
            for key, value in page.counts().items():
                result[key] = result.get(key, 0) + value
        return result

    def scores(self) -> list[int]:
        return [page.score for page in self.pages]

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "pages": [page_payload(page) for page in self.pages],
            "groups": [
                {
                    "fingerprint": group.fingerprint,
                    "rule": group.rule.id,
                    "impact": group.impact,
                    "count": group.count,
                    "pages": group.pages,
                    "selector": group.sample.selector,
                    "line": group.sample.line,
                    "snippet": group.sample.snippet,
                    "message": group.sample.message,
                }
                for group in self.groups
            ],
            "skipped": self.skipped,
        }


def audit_site(
    directory: str | Path,
    pattern: str = "**/*.html",
    max_pages: int = 50,
    rule_ids: list[str] | None = None,
) -> SiteAudit:
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"폴더가 아닙니다: {directory}")
    files = sorted(p for p in root.glob(pattern) if p.is_file())
    if not files:
        files = sorted(p for p in root.glob("**/*.htm") if p.is_file())
    site = SiteAudit(root=str(root))
    for index, path in enumerate(files):
        if index >= max_pages:
            site.skipped.append(f"{len(files) - max_pages}쪽은 max_pages 때문에 건너뜀")
            break
        relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        try:
            doc = parse_file(path)
        except Exception as exc:  # pragma: no cover - 깨진 파일은 건너뛰고 알린다
            site.skipped.append(f"{relative}: {exc}")
            continue
        violations, hidden = audit_document(doc, rules=set(rule_ids or []), file=relative)
        score, grade = score_of(violations)
        title = ""
        for node in doc.elements():
            if node.tag == "title":
                title = norm("".join(c.text for c in node.children if c.is_text))
                break
        html = doc.first("html")
        site.pages.append(
            PageAudit(
                path=relative,
                title=title,
                lang=norm(html.get("lang")) if html is not None else "",
                elements=len(doc.elements()),
                violations=violations,
                hidden_counts=hidden,
                score=score,
                grade=grade,
            )
        )
    buckets: dict[str, Group] = {}
    for page in site.pages:
        for violation in page.violations:
            group = buckets.get(violation.fingerprint)
            if group is None:
                buckets[violation.fingerprint] = Group(
                    fingerprint=violation.fingerprint,
                    rule=violation.rule,
                    impact=violation.impact,
                    count=1,
                    pages=[page.path],
                    sample=violation,
                )
                continue
            group.count += 1
            if page.path not in group.pages:
                group.pages.append(page.path)
            if IMPACT_ORDER.get(violation.impact, 9) < IMPACT_ORDER.get(group.impact, 9):
                group.impact = violation.impact
    site.groups = sorted(
        buckets.values(),
        key=lambda g: (IMPACT_ORDER.get(g.impact, 9), -len(g.pages), -g.count, g.rule.id),
    )
    return site


# ---------------------------------------------------------------- 출력
def _label(impact: str) -> str:
    return IMPACT_LABEL.get(impact, impact)


def _where(item: Violation) -> str:
    bits = [f"`{item.selector}`"]
    if item.file:
        bits.append(f"{item.file}{':' + str(item.line) if item.line else ''}")
    elif item.line:
        bits.append(f"L{item.line}")
    return " · ".join(bits)


def render_page(audit: PageAudit, show_fix: bool = True, max_per_rule: int = 0) -> str:
    counts = audit.counts()
    lines = [f"## a11y-lens · {audit.path}"]
    meta = []
    if audit.title:
        meta.append(f'제목 "{audit.title}"')
    if audit.lang:
        meta.append(f"lang={audit.lang}")
    meta.append(f"요소 {audit.elements}개")
    lines.append("- " + " · ".join(meta))
    lines.append(
        f"- 점수 **{audit.score}/100** ({audit.grade}) · 위반 **{len(audit.violations)}건**"
        f" (치명 {counts['critical']} · 심각 {counts['serious']} · 보통 {counts['moderate']})"
    )
    if not audit.violations:
        lines.append("")
        lines.append("정적으로 판정 가능한 위반은 없습니다.")
        lines.append(f"\n> {LIMITS}")
        return "\n".join(lines)

    current = None
    index = 0
    shown_per_rule: dict[str, int] = {}
    for violation in audit.violations:
        if violation.impact != current:
            current = violation.impact
            lines.append("")
            lines.append(f"### {_label(current)}")
        shown_per_rule[violation.rule.id] = shown_per_rule.get(violation.rule.id, 0) + 1
        if max_per_rule and shown_per_rule[violation.rule.id] > max_per_rule:
            continue
        index += 1
        lines.append(f"{index}. **{violation.rule.id}** {violation.rule.title} — WCAG {violation.rule.wcag} ({violation.rule.level})")
        lines.append(f"   - 위치: {_where(violation)}")
        if violation.snippet:
            lines.append(f"   - 마크업: `{violation.snippet}`")
        lines.append(f"   - 내용: {violation.message}")
        lines.append(f"   - 왜: {violation.rule.why}")
        if show_fix:
            lines.append(f"   - 고치기: `{violation.rule.fix}`")
    if max_per_rule:
        hidden = {rule: count - max_per_rule for rule, count in shown_per_rule.items() if count > max_per_rule}
        if hidden:
            summary = ", ".join(f"{rule} {count}건" for rule, count in sorted(hidden.items()))
            lines.append("")
            lines.append(f"… 생략된 반복: {summary} (같은 규칙은 하나만 고치면 함께 사라지는 경우가 많습니다)")
    lines.append("")
    lines.append(f"> {LIMITS}")
    return "\n".join(lines)


def render_site(site: SiteAudit, max_groups: int = 15) -> str:
    counts = site.counts()
    scores = site.scores()
    lines = [f"## a11y-lens · 사이트 검사 — {site.root}"]
    lines.append(
        f"- 페이지 **{len(site.pages)}쪽** · 위반 **{site.total_violations()}건**"
        f" (치명 {counts['critical']} · 심각 {counts['serious']} · 보통 {counts['moderate']})"
    )
    if scores:
        lines.append(
            f"- 점수: 최저 **{min(scores)}** · 평균 **{sum(scores) // len(scores)}** · 90점 이상 {sum(1 for s in scores if s >= 90)}쪽"
        )
    lines.append("")
    lines.append("| 위반 패턴 | 건수 | 쪽 수 | 대표 위치 |")
    lines.append("|---|---|---|---|")
    for group in site.groups[:max_groups]:
        where = f"{group.sample.file or group.pages[0]}:{group.sample.line}" if group.sample.line else (group.sample.file or group.pages[0])
        lines.append(
            f"| {_label(group.impact)} · `{group.rule.id}` {group.rule.title} | {group.count} | {len(group.pages)} | `{group.sample.selector}` · {where} |"
        )
    if len(site.groups) > max_groups:
        lines.append(f"| … 패턴 {len(site.groups) - max_groups}개 더 | | | |")
    lines.append("")
    lines.append("### 쪽별 점수 (낮은 순)")
    for page in sorted(site.pages, key=lambda p: (p.score, p.path))[:10]:
        lines.append(f"- **{page.score}** {page.grade} · `{page.path}` · 위반 {len(page.violations)}건")
    if site.skipped:
        lines.append("")
        lines.append("### 건너뜀")
        for item in site.skipped:
            lines.append(f"- {item}")
    lines.append("")
    lines.append(f"> {LIMITS}")
    return "\n".join(lines)


def render_plan(audit: PageAudit, max_steps: int = 8) -> str:
    """고치는 순서 — 치명 → 심각 → 보통, 같은 등급이면 여러 번 나온 것부터."""
    grouped = audit.by_rule()
    ordered = sorted(
        grouped.items(),
        key=lambda item: (IMPACT_ORDER.get(item[1][0].impact, 9), -len(item[1]), item[0]),
    )
    lines = [f"## 고치기 순서 · {audit.path}"]
    lines.append(
        f"- 위반 {len(audit.violations)}건 / 규칙 {len(grouped)}종 · 지금 점수 **{audit.score}/100** ({audit.grade})"
    )
    lines.append("")
    for step, (rule_id, items) in enumerate(ordered[:max_steps], start=1):
        rule = items[0].rule
        places = ", ".join(f"L{item.line}" for item in items[:5] if item.line)
        more = f" 외 {len(items) - 5}곳" if len(items) > 5 else ""
        lines.append(f"**{step}. {rule.title}** — `{rule_id}` · WCAG {rule.wcag} ({rule.level}) · {len(items)}건")
        lines.append(f"   - 위치: {places}{more}")
        lines.append(f"   - 바꿀 모양: `{rule.fix}`")
        lines.append(f"   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로")
    if len(ordered) > max_steps:
        lines.append("")
        lines.append(f"… 규칙 {len(ordered) - max_steps}종 더 (audit_page 로 전체 목록)")
    lines.append("")
    lines.append("고친 뒤에는 `verify_fixes` 로 **없어진 것/남은 것/새로 생긴 것**을 확인하세요.")
    return "\n".join(lines)


# ---------------------------------------------------------------- 직렬화
def page_payload(audit: PageAudit) -> dict:
    return {
        "path": audit.path,
        "title": audit.title,
        "lang": audit.lang,
        "elements": audit.elements,
        "score": audit.score,
        "grade": audit.grade,
        "counts": audit.counts(),
        "violations": [
            {
                "rule": violation.rule.id,
                "title": violation.rule.title,
                "wcag": violation.rule.wcag,
                "level": violation.rule.level,
                "impact": violation.impact,
                "selector": violation.selector,
                "file": violation.file,
                "line": violation.line,
                "snippet": violation.snippet,
                "message": violation.message,
                "fingerprint": violation.fingerprint,
            }
            for violation in audit.violations
        ],
    }


def payload_json(audit: PageAudit | SiteAudit) -> str:
    return json.dumps(audit.to_dict(), ensure_ascii=False, indent=2)
