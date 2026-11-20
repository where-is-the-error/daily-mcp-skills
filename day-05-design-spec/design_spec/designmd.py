"""DESIGN.md 만들기 — Stitch `design-md` 스킬의 다섯 칸 구조 그대로.

    # Design System: …
    ## 1. Visual Theme & Atmosphere
    ## 2. Color Palette & Roles
    ## 3. Typography Rules
    ## 4. Component Stylings   (Buttons / Cards / Inputs)
    ## 5. Layout Principles

칸은 원본 스킬에서, 값은 이 파일에서 계산해서 채웁니다. 사람이 쓴 브랜드 이름은
알 수 없으므로 색 이름은 **색상·채도·밝기**로만 짓고, 그 사실을 문서 첫머리에 밝힙니다.
"""

from __future__ import annotations

from collections import Counter

from .audit import Audit
from .color import Color, contrast, describe
from .nodes import Node
from .palette import background_of, role_label_for

__all__ = ["build_design_md"]


def _fmt(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "?"
    return f"{value:g}{suffix}"


def _atmosphere(audit: Audit) -> list[str]:
    design = audit.design
    analysis = audit.analysis
    screens = max(1, len(design.screens))
    per_screen = len(design.visible_nodes) / screens
    if per_screen >= 90:
        density = "빽빽한(Dense)"
    elif per_screen >= 40:
        density = "균형 잡힌(Balanced)"
    else:
        density = "여유 있는(Airy)"

    radii = analysis.radii
    total_radius = sum(count for _, count in radii.values) + radii.square
    if total_radius and radii.pill / total_radius >= 0.35:
        shape = "알약형(Pill-shaped) — 둥근 버튼과 칩이 눈에 띕니다"
    elif radii.values and radii.values[0][0] >= 12:
        shape = f"부드러운 곡선(Soft) — 가장 흔한 반경 {_fmt(radii.values[0][0], 'px')}"
    elif radii.values:
        shape = f"각진 편(Sharp) — 가장 흔한 반경 {_fmt(radii.values[0][0], 'px')}"
    else:
        shape = "반경 없음(직각)"

    shadows = sum(1 for node in design.visible_nodes for effect in node.effects if effect.kind == "drop_shadow")
    depth = (
        f"은은한 그림자(Whisper-soft) — {shadows}곳"
        if shadows
        else "그림자 없음(Flat) — 경계는 선과 색으로만"
    )

    primary = analysis.palette.roles.get("primary")
    accent = (
        f"포인트 색은 {describe(primary)} {primary.hex}"
        if primary is not None
        else "포인트 색을 특정하지 못했습니다(버튼 이름이 붙은 노드가 없음)"
    )

    strokes: list[str] = [
        f"**{density} · {shape.split(' —')[0]} · {depth.split(' —')[0]}.** "
        f"화면 {len(design.screens)}개에 노드 {len(design.visible_nodes)}개(화면당 약 {per_screen:.0f}개), "
        f"글자 {len(design.texts)}개.",
        "",
        f"- 밀도: {density} — 화면당 노드 {per_screen:.0f}개를 기준으로 판단했습니다.",
        f"- 모양: {shape}.",
        f"- 깊이: {depth}.",
        f"- 색: {accent}.",
    ]
    return strokes


def _palette_lines(audit: Audit) -> list[str]:
    palette = audit.analysis.palette
    if not palette.uses:
        return ["(칠한 색을 찾지 못했습니다)"]
    role_korean = {
        "surface": "배경·카드",
        "text": "본문 글자",
        "muted": "보조 글자",
        "primary": "주요 동작",
        "border": "선·구분",
    }
    lines = ["| 이름 | 값 | 역할 | 쓰인 곳 | 최악 대비 |", "|---|---|---|---|---|"]
    for use in palette.uses[:14]:
        role = role_label_for(palette, use.color)
        label = role_korean.get(role, role)
        worst = "—" if use.contrast_worst is None else f"{use.contrast_worst:.2f}:1"
        lines.append(
            f"| {describe(use.color)} | `{use.color.hex}` | {label} | {use.count}곳 | {worst} |"
        )
    lines.append("")
    lines.append(
        "> 이름은 브랜드 이름이 아니라 **색상·채도·밝기**로 지은 것입니다. "
        "역할은 면적·빈도·이름(Button 등)으로 추정했습니다."
    )
    if palette.near_duplicates:
        lines.append("")
        pairs = ", ".join(
            f"`{first.color.hex}` ↔ `{second.color.hex}`" for first, second, _ in palette.near_duplicates[:3]
        )
        lines.append(f"> 거의 같은 색: {pairs} — 한쪽으로 합치는 것을 검토하세요.")
    return lines


def _type_lines(audit: Audit) -> list[str]:
    report = audit.analysis.typography
    if not report.sizes:
        return ["(글자 크기를 찾지 못했습니다)"]
    ordered = sorted(report.sizes, key=lambda item: -item[0])
    labels = ["제목", "부제목", "본문", "보조", "캡션"]
    lines = [f"- 글꼴: {', '.join(family or '(이름 없음)' for family, _ in report.families) or '?'}"]
    weights = ", ".join(f"{weight}" for weight, _ in report.weights) or "?"
    lines.append(f"- 굵기: {weights}")
    lines.append("")
    lines.append("| 단계 | 크기 | 쓰인 곳 | 역할(추정) |")
    lines.append("|---|---|---|---|")
    for index, (size, count) in enumerate(ordered):
        lines.append(f"| {index + 1} | {size:g}px | {count}곳 | {labels[index] if index < len(labels) else '기타'} |")
    ratios = [sized.ratio for sized in report.texts if sized.ratio is not None]
    if ratios:
        average = sum(ratios) / len(ratios)
        lines.append("")
        lines.append(
            f"- 줄 높이: 평균 {average:.2f}배 (가장 좁은 {min(ratios):.2f}배 · 가장 넓은 {max(ratios):.2f}배)"
        )
    else:
        lines.append("")
        lines.append("- 줄 높이: 파일에 값이 없어(자동) 판정하지 않았습니다.")
    return lines


def _find(design, hints: tuple[str, ...]) -> list[Node]:
    found = []
    for node in design.visible_nodes:
        name = node.name.lower()
        if any(hint in name for hint in hints) and node.box is not None:
            found.append(node)
    return found


def _contrast_note(node: Node, page: Color) -> str:
    fill = node.solid_fill()
    if fill is None:
        return ""
    background, unknown = background_of(node, page)
    if unknown:
        return "대비 판정 불가(배경이 이미지)"
    return f"대비 {contrast(fill.over(background), background):.2f}:1"


def _component_lines(audit: Audit) -> list[str]:
    design = audit.design
    page = audit.analysis.page
    lines: list[str] = []

    buttons = _find(design, ("button", "btn", "버튼", "cta"))
    lines.append("* **Buttons:**")
    if buttons:
        heights = Counter(round(node.box[3]) for node in buttons if node.box)
        radii = Counter(round(node.radius) for node in buttons if node.radius is not None)
        main = max(buttons, key=lambda node: node.area)
        fill = main.solid_fill()
        lines.append(
            f"  가장 흔한 높이 {heights.most_common(1)[0][0]}px · 반경 "
            f"{radii.most_common(1)[0][0] if radii else 0}px · "
            f"{len(buttons)}개. 대표 버튼 \"{main.name}\" {main.describe_size()}, "
            f"칠 {fill.hex if fill else '없음'}, 글자 {_contrast_note(main, page) or '—'}."
        )
    else:
        lines.append("  이 파일에서 버튼으로 이름 붙은 노드를 찾지 못했습니다.")

    cards = [node for node in design.visible_nodes if node.children and node.radius and not node.layout.auto]
    lines.append("* **Cards/Containers:**")
    if cards:
        radius = Counter(round(node.radius) for node in cards if node.radius)
        fills = Counter(node.solid_fill().hex for node in cards if node.solid_fill())
        border = sum(1 for node in cards if node.stroke_color())
        shaded = sum(1 for node in cards if node.effects)
        lines.append(
            f"  반경 {radius.most_common(1)[0][0]}px · 칠 {fills.most_common(1)[0][0] if fills else '없음'} · "
            f"선 {border}개 · 그림자 {shaded}개 ({len(cards)}개 컨테이너 기준)."
        )
    else:
        lines.append("  반경이 있는 카드형 컨테이너를 찾지 못했습니다.")

    inputs = _find(design, ("input", "field", "textfield", "검색", "search", "입력"))
    lines.append("* **Inputs/Forms:**")
    if inputs:
        main = max(inputs, key=lambda node: node.area)
        stroke = main.stroke_color()
        lines.append(
            f"  대표 입력 \"{main.name}\" {main.describe_size()} · 반경 {_fmt(main.radius, 'px')} · "
            f"선 {stroke.hex if stroke else '없음'} · "
            f"칠 {main.solid_fill().hex if main.solid_fill() else '없음'}."
        )
    else:
        lines.append("  입력 필드로 이름 붙은 노드를 찾지 못했습니다.")
    return lines


def _layout_lines(audit: Audit) -> list[str]:
    analysis = audit.analysis
    spacing = analysis.spacing
    design = audit.design
    lines: list[str] = []
    if spacing.base:
        lines.append(
            f"- 기준 단위 **{spacing.base:g}px** — 간격 값 {spacing.total}개 중 "
            f"{spacing.base_share:.0%}가 이 값의 배수입니다."
        )
    else:
        lines.append("- 기준 단위를 찾지 못했습니다 (auto-layout 간격 값이 없거나 제각각).")
    if spacing.values:
        histogram = ", ".join(f"{value:g}×{count}" for value, count in spacing.values[:8])
        lines.append(f"- 자주 쓰는 간격: {histogram}")
    if spacing.padding_values:
        paddings = ", ".join(f"{value:g}×{count}" for value, count in spacing.padding_values[:6])
        lines.append(f"- 여백(padding): {paddings}")
    auto = sum(1 for node in design.visible_nodes if node.layout.auto)
    containers = sum(1 for node in design.visible_nodes if node.children)
    if containers:
        lines.append(f"- auto-layout 사용: 컨테이너 {containers}개 중 {auto}개 ({auto / containers:.0%})")
    sizes = []
    for screen in design.screens:
        if screen.box is not None:
            sizes.append(f"{screen.box[2]:g}×{screen.box[3]:g}")
    if sizes:
        lines.append(f"- 화면 크기: {', '.join(sizes[:6])}")
    return lines


def build_design_md(audit: Audit) -> str:
    design = audit.design
    stats = audit.stats()
    head = [
        f"# Design System: {design.title}",
        "",
        f"**Source:** `{audit.path_label}`  ·  **Screens:** {stats['screens']}  ·  "
        f"**Nodes:** {stats['nodes']}  ·  **Score:** {audit.score}/100 ({audit.grade})",
        "",
        "> 이 문서는 `design-spec` 이 디자인 파일에서 **자동으로 뽑은** 것입니다. "
        "색 이름과 역할은 계산으로 추정했으니, 브랜드 이름과 의도는 사람이 고쳐 주세요.",
        "",
        "## 1. Visual Theme & Atmosphere",
        "",
        *_atmosphere(audit),
        "",
        "## 2. Color Palette & Roles",
        "",
        *_palette_lines(audit),
        "",
        "## 3. Typography Rules",
        "",
        *_type_lines(audit),
        "",
        "## 4. Component Stylings",
        "",
        *_component_lines(audit),
        "",
        "## 5. Layout Principles",
        "",
        *_layout_lines(audit),
        "",
    ]
    notes = audit.not_judged()
    if notes:
        head += ["> 판정하지 않은 것: " + " / ".join(notes), ""]
    return "\n".join(head)
