"""규칙 17종 — 무엇을 위반으로 볼지, 얼마나 무거운지, 어떻게 고치는지.

등급은 셋입니다: **치명**(화면을 못 쓰게 함) · **심각**(읽기 어렵거나 손이 아픔) ·
**보통**(일관성이 깨져서 나중에 비싸짐). 점수는 **규칙 종류**마다 한 번만 깎습니다 —
같은 규칙이 12번 나와도 "고칠 곳 하나(패턴)"라는 신호이기 때문입니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .color import Color, ColorError, contrast, describe, suggest_text_color
from .nodes import Design, Node
from .palette import Palette, background_of
from .spacing import RadiiReport, SpacingReport
from .typography import MIN_LINE_RATIO, MIN_SIZE, MULTILINE_CHARS, TypeReport

__all__ = [
    "Rule",
    "Finding",
    "RULES",
    "RULES_BY_ID",
    "SEVERITY_ORDER",
    "SEVERITY_WEIGHT",
    "Analysis",
    "analyse",
    "DEFAULT_MIN_TOUCH",
]

SEVERITY_ORDER = ("치명", "심각", "보통")
SEVERITY_WEIGHT = {"치명": 25, "심각": 12, "보통": 4}
DEFAULT_MIN_TOUCH = 44.0


@dataclass
class Analysis:
    design: Design
    palette: Palette
    spacing: SpacingReport
    radii: RadiiReport
    typography: TypeReport
    page: Color
    min_touch: float = DEFAULT_MIN_TOUCH
    unjudged: list[str] = field(default_factory=list)


@dataclass
class Finding:
    rule: str
    severity: str
    ref: str
    where: str
    detail: str
    evidence: str = ""
    fix: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "ref": self.ref,
            "where": self.where,
            "detail": self.detail,
            "evidence": self.evidence,
            "fix": self.fix,
        }


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    basis: str
    what: str
    check: Callable[[Analysis], list[Finding]]

    def label(self) -> str:
        return f"{self.title} — {self.basis}"


def _ratio_text(ratio: float) -> str:
    return f"{ratio:.2f}:1"


def _where(node: Node) -> str:
    path = node.path[-3:] if node.path else [node.type]
    return " > ".join(path)


def _box_size(node: Node) -> str:
    return node.describe_size()


# ------------------------------------------------------------------ 1 대비
def check_contrast(analysis: Analysis) -> list[Finding]:
    findings: list[Finding] = []
    for node in analysis.design.texts:
        background, unknown = background_of(node, analysis.page)
        if unknown:
            continue  # 그라디언트·이미지 위 글자 — 판정하지 않는다
        fill = node.solid_fill()
        if fill is None:
            fill = Color(0.0, 0.0, 0.0)
        effective = fill.over(background)
        ratio = contrast(effective, background)
        size = node.text.size if node.text else None
        bold = node.text.bold if node.text else False
        large = bool(size and (size >= 24 or (size >= 18.66 and bold)))
        required = 3.0 if large else 4.5
        if ratio >= required:
            continue
        suggestion = suggest_text_color(fill, background, required)
        fix = (
            f"{suggestion.hex} 로 바꾸면 {_ratio_text(contrast(suggestion.over(background), background))}"
            if suggestion is not None
            else "배경을 밝게/어둡게 바꾸거나 글자를 굵게"
        )
        findings.append(
            Finding(
                rule="contrast-text",
                severity="치명",
                ref=node.ref,
                where=_where(node),
                detail=f"글자 대비 {_ratio_text(ratio)} (필요 {required:g}:1)",
                evidence=f"{fill.hex} on {background.hex} · {size or '?'}px{' bold' if bold else ''}",
                fix=fix,
            )
        )
    return findings


# ------------------------------------------------------------- 2 터치 크기
def check_touch(analysis: Analysis) -> list[Finding]:
    findings: list[Finding] = []
    limit = analysis.min_touch
    for node in analysis.design.visible_nodes:
        if not node.is_interactive or node.box is None:
            continue
        if node.characters.strip():
            continue  # 글자는 라벨이지 누르는 상자가 아니다
        width, height = node.box[2], node.box[3]
        if width <= 0 or height <= 0:
            continue
        if width >= limit - 0.5 and height >= limit - 0.5:
            continue
        findings.append(
            Finding(
                rule="touch-target",
                severity="치명",
                ref=node.ref,
                where=_where(node),
                detail=f"누를 수 있는 요소가 {width:g}×{height:g} — 최소 {limit:g}×{limit:g}",
                evidence=f'이름에 "{_hint(node.name)}" 가 들어가 누를 것으로 봤습니다',
                fix=f"상자를 {limit:g}×{limit:g} 이상으로 (보이는 크기는 그대로, 누르는 영역만 넓혀도 됨)",
            )
        )
    return findings


def _hint(name: str) -> str:
    lowered = name.lower()
    for hint in ("button", "btn", "버튼", "icon", "아이콘", "tab", "탭", "chip", "link", "링크"):
        if hint in lowered:
            return hint
    return name


# --------------------------------------------------------------- 3 글자 겹침
def _overlap(first: tuple, second: tuple) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def check_collision(analysis: Analysis) -> list[Finding]:
    findings: list[Finding] = []
    for container in analysis.design.visible_nodes:
        if not container.children:
            continue
        texts = [child for child in container.children if child.characters.strip() and child.box]
        for index, first in enumerate(texts):
            for second in texts[index + 1:]:
                assert first.box is not None and second.box is not None
                shared = _overlap(first.box, second.box)
                smaller = min(first.area, second.area)
                if smaller <= 0 or shared / smaller < 0.25:
                    continue
                findings.append(
                    Finding(
                        rule="layout-collision",
                        severity="치명",
                        ref=first.ref,
                        where=_where(first),
                        detail=(
                            f'글자 "{_clip(first.characters)}" 와 "{_clip(second.characters)}" 가 '
                            f"{shared / smaller:.0%} 겹칩니다"
                        ),
                        evidence=f"{first.ref} {_box_size(first)} · {second.ref} {_box_size(second)}",
                        fix="한쪽을 옮기거나 폭을 줄이세요. 겹친 글자는 둘 다 읽을 수 없습니다",
                    )
                )
                break
    return findings


def _clip(text: str, limit: int = 16) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------------------- 4 넘침
def check_overflow(analysis: Analysis) -> list[Finding]:
    findings: list[Finding] = []
    for parent in analysis.design.visible_nodes:
        if parent.box is None or not parent.children:
            continue
        if parent.type.upper() in {"DOCUMENT", "CANVAS"}:
            continue
        left, top, width, height = parent.box
        right, bottom = left + width, top + height
        worst: tuple[Node, float, str] | None = None
        for child in parent.children:
            if child.box is None or not child.visible:
                continue
            c_left, c_top, c_width, c_height = child.box
            over = max(
                left - c_left,
                top - c_top,
                (c_left + c_width) - right,
                (c_top + c_height) - bottom,
            )
            if over <= 1.0:
                continue
            side = (
                "오른쪽" if (c_left + c_width) - right >= over
                else "아래" if (c_top + c_height) - bottom >= over
                else "왼쪽" if left - c_left >= over
                else "위"
            )
            if worst is None or over > worst[1]:
                worst = (child, over, side)
        if worst is None:
            continue
        child, over, side = worst
        clipped = parent.layout.clips
        findings.append(
            Finding(
                rule="layout-overflow",
                severity="심각" if child.characters.strip() or clipped else "보통",
                ref=child.ref,
                where=_where(child),
                detail=(
                    f'부모 "{_clip(parent.name, 20)}" 밖으로 {side} {over:g}px 나갑니다'
                    + (" (부모가 잘라내도록 설정됨)" if clipped else "")
                ),
                evidence=f'부모 {_box_size(parent)} · 자식 {_box_size(child)}',
                fix="부모 크기를 늘리거나 자식의 폭·위치를 부모 안으로",
            )
        )
    return findings


# --------------------------------------------------------------- 5 작은 글자
def check_small_text(analysis: Analysis) -> list[Finding]:
    findings = []
    for sized in analysis.typography.texts:
        if sized.size >= MIN_SIZE:
            continue
        findings.append(
            Finding(
                rule="type-too-small",
                severity="심각",
                ref=sized.node.ref,
                where=_where(sized.node),
                detail=f"{sized.size:g}px — 최소 {MIN_SIZE:g}px",
                evidence=f'"{_clip(sized.node.characters)}"',
                fix=f"{MIN_SIZE:g}px 이상으로. 11px 아래는 고해상도 폰에서도 읽기 어렵습니다",
            )
        )
    return findings


# --------------------------------------------------------------- 6 좁은 줄
def check_line_height(analysis: Analysis) -> list[Finding]:
    findings = []
    for sized in analysis.typography.texts:
        if sized.ratio is None or sized.chars < MULTILINE_CHARS:
            continue
        if sized.ratio >= MIN_LINE_RATIO:
            continue
        style = sized.node.text
        size = style.size if style and style.size else sized.size
        findings.append(
            Finding(
                rule="type-line-cramped",
                severity="심각",
                ref=sized.node.ref,
                where=_where(sized.node),
                detail=f"줄 높이 {style.line_height:g}px / 글자 {size:g}px = {sized.ratio:.2f}",
                evidence=f'"{_clip(sized.node.characters, 24)}" ({sized.chars}자 — 여러 줄로 흐를 수 있음)',
                fix=f"줄 높이를 {size * 1.5:.0f}px 근처로 (비율 {MIN_LINE_RATIO:g} 이상)",
            )
        )
    return findings


# --------------------------------------------------------------- 7 간격
def check_spacing_scale(analysis: Analysis) -> list[Finding]:
    report = analysis.spacing
    if report.base is None or not report.off_scale:
        return []
    findings = []
    for value, count in report.off_scale[:6]:
        node = _node_with_gap(analysis.design, value)
        findings.append(
            Finding(
                rule="spacing-off-scale",
                severity="보통",
                ref=node.ref if node else "",
                where=_where(node) if node else "",
                detail=f"{value:g}px — 기준 {report.base:g}px 의 배수가 아님 ({count}곳)",
                evidence=f"간격 값 {report.total}개 중 {report.base_share:.0%} 가 {report.base:g}의 배수",
                fix=f"가까운 {round(value / report.base) * report.base:g}px 로",
            )
        )
    return findings


def _node_with_gap(design: Design, value: float) -> Node | None:
    for node in design.visible_nodes:
        if node.layout.auto and node.layout.gap is not None and abs(node.layout.gap - value) < 1e-6:
            return node
    for node in design.visible_nodes:
        if node.layout.auto and any(abs(item - value) < 1e-6 for item in node.layout.padding):
            return node
    return None


def check_spacing_count(analysis: Analysis) -> list[Finding]:
    report = analysis.spacing
    if report.distinct <= 8:
        return []
    node = _node_with_gap(analysis.design, report.dominant) if report.dominant is not None else None
    return [
        Finding(
            rule="spacing-too-many",
            severity="보통",
            ref=node.ref if node else "",
            where=_where(node) if node else "",
            detail=f"간격 값이 {report.distinct}종류 — 8종 이하 권장",
            evidence="값: " + ", ".join(f"{value:g}" for value, _ in report.values[:10]),
            fix="4·8·12·16·24 처럼 다섯 단계로 줄이세요",
        )
    ]


# --------------------------------------------------------------- 8 색
def check_near_duplicates(analysis: Analysis) -> list[Finding]:
    findings = []
    for first, second, gap in analysis.palette.near_duplicates[:5]:
        findings.append(
            Finding(
                rule="palette-near-duplicate",
                severity="보통",
                ref=first.nodes[0].ref if first.nodes else "",
                where=_where(first.nodes[0]) if first.nodes else "",
                detail=(
                    f"{first.color.hex} 와 {second.color.hex} 는 거리 {gap:.1f} — 눈으로 구분되지 않음"
                ),
                evidence=(
                    f"{describe(first.color)} ×{first.count} · {describe(second.color)} ×{second.count}"
                ),
                fix="한쪽으로 합치고, 진짜 두 색이 필요하면 밝기를 확실히 벌리세요",
            )
        )
    return findings


def check_palette_width(analysis: Analysis) -> list[Finding]:
    palette = analysis.palette
    if palette.distinct <= 12:
        return []
    return [
        Finding(
            rule="palette-too-wide",
            severity="보통",
            ref="",
            where=analysis.design.title,
            detail=f"색이 {palette.distinct}종 — 12종 이하 권장",
            evidence=", ".join(use.color.hex for use in palette.uses[:14]),
            fix="역할(surface·text·primary·border)마다 한 색으로 정리하세요",
        )
    ]


def check_hardcoded_colors(analysis: Analysis) -> list[Finding]:
    palette = analysis.palette
    coverage = palette.token_coverage
    total = palette.styled_fills + palette.hardcoded_fills
    if coverage is None or total < 10 or coverage >= 0.7:
        return []
    hardcoded = next((use for use in palette.uses if not use.nodes[0].styles.get("fills")), None)
    return [
        Finding(
            rule="color-hardcoded",
            severity="보통",
            ref=hardcoded.nodes[0].ref if hardcoded and hardcoded.nodes else "",
            where=_where(hardcoded.nodes[0]) if hardcoded and hardcoded.nodes else "",
            detail=f"칠한 노드 {total}개 중 스타일(토큰)을 쓰는 것 {palette.styled_fills}개 — {coverage:.0%}",
            evidence="색을 직접 넣으면 나중에 한 곳만 바뀌어 색이 갈라집니다",
            fix="Figma 색 스타일(또는 변수)을 만들고 칠을 그것으로 바꾸세요",
        )
    ]


# --------------------------------------------------------------- 9 반경
def check_radii(analysis: Analysis) -> list[Finding]:
    report: RadiiReport = analysis.radii
    if report.distinct <= 3:
        return []
    return [
        Finding(
            rule="radius-too-many",
            severity="보통",
            ref="",
            where=analysis.design.title,
            detail=f"모서리 반경이 {report.distinct}종류 — 3종 이하 권장",
            evidence=", ".join(f"{value:g}" for value, _ in sorted(report.values)),
            fix="작은 것(4~8)·중간(12~16)·알약형 셋으로 줄이세요",
        )
    ]


# --------------------------------------------------------------- 10 글자 단계
def check_type_scale(analysis: Analysis) -> list[Finding]:
    report: TypeReport = analysis.typography
    if report.distinct <= 5:
        return []
    return [
        Finding(
            rule="type-too-many-sizes",
            severity="보통",
            ref="",
            where=analysis.design.title,
            detail=f"글자 크기가 {report.distinct}단계 — 5단계 이하 권장",
            evidence=", ".join(f"{size:g}" for size, _ in sorted(report.sizes, reverse=True)),
            fix="본문·보조·제목·큰제목 정도로 줄이고 나머지는 굵기로 구분하세요",
        )
    ]


def check_type_one_off(analysis: Analysis) -> list[Finding]:
    report: TypeReport = analysis.typography
    findings = []
    for size in report.one_offs[:4]:
        node = next((sized.node for sized in report.texts if sized.size == size), None)
        if node is None:  # pragma: no cover - 방어
            continue
        others = [candidate for candidate, _ in report.sizes if candidate != size]
        nearest = min(others, key=lambda candidate: abs(candidate - size)) if others else None
        findings.append(
            Finding(
                rule="type-one-off",
                severity="보통",
                ref=node.ref,
                where=_where(node),
                detail=f"{size:g}px 는 이 화면에서 한 번만 쓰였습니다",
                evidence=f'"{_clip(node.characters)}"',
                fix=f"가까운 단계 {nearest:g}px 로" if nearest is not None else "단계를 하나 정해 쓰세요",
            )
        )
    return findings


def check_type_families(analysis: Analysis) -> list[Finding]:
    report: TypeReport = analysis.typography
    if len(report.families) <= 1:
        return []
    return [
        Finding(
            rule="type-many-families",
            severity="보통",
            ref="",
            where=analysis.design.title,
            detail=f"글꼴이 {len(report.families)}종",
            evidence=", ".join(f"{family} ×{count}" for family, count in report.families[:5]),
            fix="한 종류로 통일하고 굵기·크기로 위계를 만드세요",
        )
    ]


# --------------------------------------------------------------- 11 정렬
def check_misaligned(analysis: Analysis) -> list[Finding]:
    findings = []
    for container in analysis.design.visible_nodes:
        layout = container.layout
        if not layout.auto or len(container.children) < 2:
            continue
        # 크기가 같은(±1px) 형제끼리만 비교한다 — 아이콘과 글자는 원래 높이가 다르다
        groups: dict[tuple[int, int], list[Node]] = {}
        for child in container.children:
            if child.box is None or not child.visible:
                continue
            key = (round(child.box[2]), round(child.box[3]))
            groups.setdefault(key, []).append(child)
        axis = 0 if layout.mode.upper() == "VERTICAL" else 1
        for key, members in groups.items():
            if len(members) < 2:
                continue
            values = [member.box[axis] for member in members if member.box is not None]
            spread = max(values) - min(values)
            if spread <= 0.5 or spread > 3.0:
                continue
            offender = members[values.index(max(values))]
            findings.append(
                Finding(
                    rule="layout-misaligned",
                    severity="보통",
                    ref=offender.ref,
                    where=_where(offender),
                    detail=(
                        f"같은 크기({key[0]}×{key[1]}) 형제 {len(members)}개가 "
                        f"{'가로' if axis == 0 else '세로'} 위치 {spread:g}px 어긋남"
                    ),
                    evidence=f'"{_clip(container.name, 20)}" 안',
                    fix="auto-layout 에 맡기세요 — 1px 어긋남은 눌러도 모르고, 나중에 제일 먼저 보입니다",
                )
            )
            break
    return findings


# --------------------------------------------------------------- 12 이름
DEFAULT_NAME = re.compile(
    r"^(frame|rectangle|group|ellipse|vector|image|line|text|폴리곤|star|slice)\s*\d*$",
    re.I,
)


def check_naming(analysis: Analysis) -> list[Finding]:
    offenders = []
    for node in analysis.design.visible_nodes:
        name = node.name.strip()
        if not name or DEFAULT_NAME.match(name):
            offenders.append(node)
    if len(offenders) < 3:
        return []
    return [
        Finding(
            rule="naming-default",
            severity="보통",
            ref=offenders[0].ref,
            where=_where(offenders[0]),
            detail=f'이름이 기본값("Frame 12" 같은)인 노드 {len(offenders)}개',
            evidence=", ".join(f'"{node.name or "(빈 이름)"}"' for node in offenders[:4]),
            fix="역할로 이름을 붙이세요 (Button/Primary, Card/Product). 이름이 곧 컴포넌트 후보입니다",
        )
    ]


RULES: tuple[Rule, ...] = (
    Rule("contrast-text", "글자 대비 부족", "치명", "WCAG 2.2 1.4.3",
         "글자와 바로 뒤 배경의 대비가 4.5:1(큰 글자 3:1) 미만", check_contrast),
    Rule("touch-target", "누르는 영역이 작음", "치명", "Apple HIG 44pt · Material 48dp",
         "버튼·아이콘 등 누를 요소가 44×44 미만", check_touch),
    Rule("layout-collision", "글자끼리 겹침", "치명", "레이아웃",
         "같은 부모의 두 글자가 25% 이상 겹침", check_collision),
    Rule("layout-overflow", "부모 밖으로 넘침", "심각", "레이아웃",
         "자식이 부모 상자를 1px 넘게 벗어남", check_overflow),
    Rule("type-too-small", "너무 작은 글자", "심각", "최소 11px",
         "글자 크기가 11px 미만", check_small_text),
    Rule("type-line-cramped", "줄 높이가 좁음", "심각", "줄 높이 ≥ 1.15",
         "20자 이상 글자의 줄 높이/크기 비가 1.15 미만", check_line_height),
    Rule("spacing-off-scale", "간격이 스케일 밖", "보통", "기준 단위의 배수",
         "간격·여백이 기준 단위(2·4·8…)의 배수가 아님", check_spacing_scale),
    Rule("spacing-too-many", "간격 값이 너무 많음", "보통", "≤ 8종",
         "서로 다른 간격 값이 8종류를 넘음", check_spacing_count),
    Rule("palette-near-duplicate", "거의 같은 색 두 개", "보통", "색 거리 ≤ 10",
         "눈으로 구분 안 되는 두 색이 따로 쓰임", check_near_duplicates),
    Rule("palette-too-wide", "색이 너무 많음", "보통", "≤ 12종",
         "한 파일에서 색이 12종류를 넘음", check_palette_width),
    Rule("color-hardcoded", "색 토큰 미사용", "보통", "토큰 커버리지 ≥ 70%",
         "칠한 노드 대부분이 색 스타일 없이 직접 칠해짐", check_hardcoded_colors),
    Rule("radius-too-many", "반경이 너무 많음", "보통", "≤ 3종",
         "모서리 반경이 3종류를 넘음", check_radii),
    Rule("type-too-many-sizes", "글자 크기가 너무 많음", "보통", "≤ 5단계",
         "글자 크기가 5단계를 넘음", check_type_scale),
    Rule("type-one-off", "한 번만 쓰인 크기", "보통", "단계로 묶기",
         "한 화면에서 한 번만 쓰인 글자 크기", check_type_one_off),
    Rule("type-many-families", "글꼴이 여러 종", "보통", "1종",
         "서로 다른 글꼴이 2종 이상", check_type_families),
    Rule("layout-misaligned", "1~3px 어긋남", "보통", "auto-layout 정렬",
         "auto-layout 안에서 같은 축의 위치가 1~3px 다름", check_misaligned),
    Rule("naming-default", "기본 이름 그대로", "보통", "역할 이름",
         '"Frame 12" 같은 기본 이름이 3개 이상', check_naming),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}


def analyse(
    design: Design,
    palette: Palette,
    spacing: SpacingReport,
    radii: RadiiReport,
    typography: TypeReport,
    page: Color,
    min_touch: float = DEFAULT_MIN_TOUCH,
) -> Analysis:
    return Analysis(
        design=design,
        palette=palette,
        spacing=spacing,
        radii=radii,
        typography=typography,
        page=page,
        min_touch=min_touch,
    )


def run_rules(analysis: Analysis, rule_ids: list[str] | None = None) -> list[Finding]:
    chosen = [RULES_BY_ID[rule] for rule in rule_ids if rule in RULES_BY_ID] if rule_ids else list(RULES)
    findings: list[Finding] = []
    for rule in chosen:
        try:
            findings.extend(rule.check(analysis))
        except ColorError:  # pragma: no cover - 방어
            continue
    return findings
