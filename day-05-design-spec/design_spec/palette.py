"""색 — 무엇이 얼마나 쓰였나, 어디에 쓰였나, 무엇과 비슷한가.

역할(role) 추측 규칙 — 알파(투명도)가 섞인 색은 **합성한 뒤**로 비교합니다.
  · surface : 면적이 가장 넓은 칠 (배경·카드)
  · text    : 글자 노드가 가장 많은 색
  · primary : '버튼'이라는 이름이 붙은 노드 중 가장 큰 것의 칠
  · border  : 가장 많이 쓰인 선 색
  · muted   : text 색 중 대비가 가장 낮은 것

배경은 **조상의 칠을 아래에서 위로 합성**해 구합니다. 그라디언트·이미지가
글자 아래에 깔려 있으면 대비를 **판정하지 않습니다**(계산할 수 없으므로).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .color import Color, contrast, describe, distance
from .nodes import Design, Node

__all__ = [
    "ColorUse",
    "Palette",
    "analyse_palette",
    "background_of",
    "PAGE_WHITE",
    "NEAR_DUPLICATE",
    "MAX_PALETTE",
    "near_duplicate_pairs",
]

PAGE_WHITE = Color(1.0, 1.0, 1.0)
NEAR_DUPLICATE = 10.0
MAX_PALETTE = 12


@dataclass
class ColorUse:
    color: Color
    count: int = 0
    area: float = 0.0
    roles: Counter = field(default_factory=Counter)
    nodes: list[Node] = field(default_factory=list)
    contrast_worst: float | None = None
    contrast_pair: Color | None = None

    @property
    def key(self) -> str:
        return self.color.hex

    def role_label(self) -> str:
        if not self.roles:
            return "기타"
        return self.roles.most_common(1)[0][0]


@dataclass
class Palette:
    uses: list[ColorUse] = field(default_factory=list)
    near_duplicates: list[tuple[ColorUse, ColorUse, float]] = field(default_factory=list)
    roles: dict[str, Color] = field(default_factory=dict)
    styled_fills: int = 0
    hardcoded_fills: int = 0
    gradients: int = 0
    text_over_image: list[Node] = field(default_factory=list)

    @property
    def distinct(self) -> int:
        return len(self.uses)

    @property
    def token_coverage(self) -> float | None:
        total = self.styled_fills + self.hardcoded_fills
        if not total:
            return None
        return self.styled_fills / total

    def by_role(self, role: str) -> ColorUse | None:
        for use in self.uses:
            if use.role_label() == role:
                return use
        return None


def _page_background(design: Design) -> Color:
    for screen in design.screens:
        color = screen.opaque_fill()
        if color is not None:
            return color
    return PAGE_WHITE


def background_of(node: Node, page: Color = PAGE_WHITE) -> tuple[Color, str]:
    """글자 뒤에 실제로 깔린 색. 두 번째 값이 비어 있지 않으면 판정 불가 사유."""
    chain: list[Node] = []
    current = node.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    base = page
    unknown = ""
    for ancestor in reversed(chain):
        solid = ancestor.solid_fill()
        if solid is not None:
            base = solid.over(base)
        other = ancestor.non_solid_fill()
        if other is not None:
            unknown = f"{ancestor.name or ancestor.type} 의 {other.label()}"
    return base, unknown


def _collect_uses(design: Design, page: Color) -> tuple[list[ColorUse], Palette]:
    uses: dict[str, ColorUse] = {}
    palette = Palette()

    def touch(color: Color, node: Node, role: str, area: float) -> None:
        key = color.hex
        use = uses.get(key)
        if use is None:
            use = ColorUse(color=color)
            uses[key] = use
        use.count += 1
        use.area += area
        use.roles[role] += 1
        use.nodes.append(node)

    for node in design.visible_nodes:
        if not node.characters.strip():
            area = node.area
            solid = node.solid_fill()
            if solid is not None:
                touch(solid, node, "surface", area)
                if node.styles.get("fills"):
                    palette.styled_fills += 1
                else:
                    palette.hardcoded_fills += 1
            if node.non_solid_fill() is not None:
                palette.gradients += 1
        stroke = node.stroke_color()
        if stroke is not None:
            touch(stroke, node, "border", node.area * 0.01)
        if node.characters.strip():
            fill = node.solid_fill() or Color(0.0, 0.0, 0.0)
            touch(fill, node, "text", node.area)
            back, unknown = background_of(node, page)
            if unknown:
                palette.text_over_image.append(node)
            else:
                ratio = contrast(fill.over(back), back)
                key = fill.hex
                use = uses[key]
                if use.contrast_worst is None or ratio < use.contrast_worst:
                    use.contrast_worst = ratio
                    use.contrast_pair = back

    ordered = sorted(uses.values(), key=lambda use: (-use.area, -use.count, use.key))
    palette.uses = ordered
    _assign_roles(design, palette)
    palette.near_duplicates = near_duplicate_pairs(ordered)
    return ordered, palette


def _assign_roles(design: Design, palette: Palette) -> None:
    if not palette.uses:
        return
    surfaces = [use for use in palette.uses if use.roles.get("surface")]
    texts = [use for use in palette.uses if use.roles.get("text")]
    borders = [use for use in palette.uses if use.roles.get("border")]

    if surfaces:
        palette.roles["surface"] = max(surfaces, key=lambda use: use.area).color
    if texts:
        palette.roles["text"] = max(texts, key=lambda use: use.count).color
        muted = [use for use in texts if use.contrast_worst is not None]
        if len(muted) > 1:
            palette.roles["muted"] = min(muted, key=lambda use: use.contrast_worst or 21).color
    if borders:
        palette.roles["border"] = max(borders, key=lambda use: use.count).color

    buttons: list[Node] = []
    for node in design.visible_nodes:
        if node.characters.strip():
            continue
        name = node.name.lower()
        if any(hint in name for hint in ("button", "btn", "버튼", "cta")):
            if node.solid_fill() is not None:
                buttons.append(node)
    if buttons:
        biggest = max(buttons, key=lambda node: node.area)
        color = biggest.solid_fill()
        if color is not None:
            palette.roles["primary"] = color
    if "primary" not in palette.roles:
        saturated = [
            use for use in palette.uses
            if use.color.saturation > 0.45
            and 0.20 <= use.color.hsl[2] <= 0.75   # 거의 검정·거의 흰색은 포인트 색이 아니다
            and use.count >= 2
            and use.roles.get("surface")
        ]
        if saturated:
            palette.roles["primary"] = max(saturated, key=lambda use: use.area).color


def near_duplicate_pairs(uses: list[ColorUse], tolerance: float = NEAR_DUPLICATE):
    groups: list[tuple[ColorUse, ColorUse, float]] = []
    opaque = [use for use in uses if use.count >= 2 and use.color.a >= 0.999]
    for index, first in enumerate(opaque):
        for second in opaque[index + 1:]:
            gap = distance(first.color, second.color)
            if gap <= tolerance:
                groups.append((first, second, gap))
    groups.sort(key=lambda item: item[2])
    return groups


ROLE_PRIORITY = ("primary", "text", "muted", "surface", "border")


def role_label_for(palette: "Palette", color: Color) -> str:
    """한 색이 여러 역할에 걸릴 때(잉크가 글자이자 선일 때) 읽는 쪽이 기대하는 순서로 고른다."""
    for role in ROLE_PRIORITY:
        picked = palette.roles.get(role)
        if picked is not None and picked.hex == color.hex:
            return role
    for use in palette.uses:
        if use.color.hex == color.hex:
            return use.role_label()
    return "기타"


def analyse_palette(design: Design, page: Color | None = None) -> Palette:
    page_color = page or _page_background(design)
    _, palette = _collect_uses(design, page_color)
    return palette


def describe_use(use: ColorUse) -> str:
    return f"{describe(use.color)} ({use.color.hex})"
