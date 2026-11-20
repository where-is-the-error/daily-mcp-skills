"""한 번 훑어 접는 트리 — 노드 → 읽을 수 있는 텍스트.

세 가지를 합니다(모두 Figma-Context-MCP 의 'extractor' 설계에서 가져온 생각):

1. **한 번만 훑는다** — 깊이·필터·모드가 달라도 트리는 한 번 순회한다.
2. **스타일 세기** — 같은 시각 속성(칠·선·반경·그림자·글자)이 두 노드 이상에서
   쓰이면 표(`s1`, `s2`…)로 올리고 노드에는 참조만 남긴다. 한 번만 쓰는 스타일은
   올리지 않는다(간접 참조 비용 > 이득).
3. **같은 모양 접기** — 자식까지 같은 부분 트리가 두 번 이상 나오면 두 번째부터는
   `↺ e12` 로 첫 번째를 가리키고 자식을 다시 찍지 않는다.

`ref=eN` 은 **문서 순서로 고정**입니다. depth·mode·max_nodes 를 바꿔도 같은 파일이면
같은 노드에 같은 번호가 붙으므로, "아까 그 버튼(e14)만 다시 보여 줘"가 성립합니다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .nodes import Design, Node

__all__ = ["Entry", "TreeView", "build", "style_signature", "MODES"]

MODES = ("all", "layout", "text", "visual")


def style_signature(node: Node) -> tuple:
    """노드의 '겉모습'만 모은 서명 — 레이아웃(위치·간격)은 뺀다."""
    text = node.text
    return (
        tuple(fill.label() for fill in node.fills if fill.kind != "none"),
        tuple(fill.label() for fill in node.strokes if fill.kind != "none"),
        node.stroke_weight,
        None if node.radius in (None, 0) else round(node.radius, 2),
        tuple(effect.label() for effect in node.effects),
        None if node.opacity >= 0.999 else round(node.opacity, 2),
        None
        if text is None
        else (
            text.family,
            None if text.size is None else round(text.size, 2),
            text.weight,
            None if text.line_height is None else round(text.line_height, 2),
            None if text.letter_spacing is None else round(text.letter_spacing, 2),
        ),
    )


EMPTY_SIGNATURE = ((), (), None, None, (), None, None)


def _structure(node: Node) -> tuple:
    """같은 모양인지 판단하는 서명 — 글자 내용은 뺀다(카드 12장은 글자만 다르다)."""
    name = "" if node.is_text else node.name
    return (
        node.type,
        name,
        style_signature(node),
        tuple(_structure(child) for child in node.children if child.visible),
    )


def has_text(node: Node) -> bool:
    if node.characters.strip():
        return True
    return any(has_text(child) for child in node.children)


@dataclass
class Entry:
    node: Node
    depth: int
    style_ref: str = ""
    repeat_of: str = ""
    printed: bool = True

    @property
    def ref(self) -> str:
        return self.node.ref


@dataclass
class TreeView:
    design: Design
    entries: list[Entry] = field(default_factory=list)
    styles: dict[str, tuple[tuple, int]] = field(default_factory=dict)
    total_nodes: int = 0
    hidden: int = 0
    mode: str = "all"
    cut_depth: int = 0
    cut_nodes: int = 0

    def by_ref(self, ref: str) -> Entry | None:
        wanted = ref.strip().lower()
        for entry in self.entries:
            if entry.ref.lower() == wanted:
                return entry
        return None

    def matches(self, needle: str = "", pattern=None) -> list[Entry]:
        hits: list[Entry] = []
        for entry in self.entries:
            haystack = f"{entry.node.name} {entry.node.characters} {entry.node.type}"
            if pattern is not None:
                if pattern.search(haystack):
                    hits.append(entry)
            elif needle and needle.lower() in haystack.lower():
                hits.append(entry)
        return hits

    # -------------------------------------------------------------- 출력
    def render(self, max_nodes: int = 200) -> str:
        printed = [entry for entry in self.entries if entry.printed]
        lines: list[str] = []
        header = (
            f'document "{self.design.title}" · 화면 {len(self.design.screens)}개 · '
            f"노드 {self.total_nodes}개 · 텍스트 {len(self.design.texts)}개"
        )
        if self.hidden:
            header += f" · 숨김 {self.hidden}개 제외"
        header += f" · 모드 {self.mode}"
        lines.append(header)

        for entry in printed[: max(0, max_nodes)]:
            lines.append(self._line(entry))
        if len(printed) > max_nodes:
            lines.append(
                f"  … {len(printed) - max_nodes}개 더 (max_nodes 를 늘리거나 ref= 로 좁히세요)"
            )
        if self.cut_depth:
            lines.append(f"  … 깊이 제한으로 {self.cut_depth}곳에서 멈췄습니다 (depth=0 이면 무제한)")
        if self.styles and self.mode in ("all", "visual"):
            lines.append("")
            lines.append("## 반복 스타일 (두 노드 이상에서 쓰임 — 숫자가 쓰인 횟수)")
            for name, (signature, count) in self.styles.items():
                lines.append(f"{name} ×{count} · {_signature_label(signature)}")
        return "\n".join(lines)

    def _line(self, entry: Entry) -> str:
        node = entry.node
        indent = "  " * min(entry.depth, 14)
        head = f'{indent}{node.type.lower() or "node"} "{_short(node.name, 34)}"'
        bits: list[str] = []
        if self.mode in ("all", "layout", "text"):
            if node.box is not None:
                bits.append(f"{node.box[2]:g}×{node.box[3]:g}")
            if self.mode == "layout":
                if node.box is not None:
                    bits.append(f"@{node.box[0]:g},{node.box[1]:g}")
                if node.layout.auto:
                    arrow = "→" if node.layout.mode == "HORIZONTAL" else "↓"
                    bits.append(f"{arrow} gap {_num(node.layout.gap)}")
                if any(node.layout.padding):
                    bits.append("pad " + "/".join(_num(value) for value in node.layout.padding))
        if self.mode in ("all", "visual") and not entry.style_ref:
            bits.extend(_visual_bits(node))
        if self.mode in ("all", "visual") and node.text is not None and node.text.label():
            bits.insert(0, node.text.label())
        if self.mode in ("all", "text") and node.characters:
            bits.append(f"“{_short(node.characters.strip(), 40)}”")
        line = head + (" " + " · ".join(bits) if bits else "")
        if entry.style_ref and self.mode in ("all", "visual"):
            line += f" · {entry.style_ref}"
        line += f" · ref={entry.ref}"
        if entry.repeat_of:
            line += f" ↺ {entry.repeat_of} (같은 모양)"
        return line


def _num(value: float | None) -> str:
    return "?" if value is None else f"{value:g}"


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _visual_bits(node: Node) -> list[str]:
    bits: list[str] = []
    fill = node.solid_fill()
    if fill is not None:
        bits.append(f"fill {fill.css()}")
    for other in node.fills:
        if not other.solid:
            bits.append(f"fill {other.label()}")
    color = node.stroke_color()
    if color is not None:
        weight = f"{node.stroke_weight:g}" if node.stroke_weight else "1"
        bits.append(f"stroke {color.css()} {weight}")
    if node.radius:
        bits.append(f"r{node.radius:g}")
    for effect in node.effects:
        bits.append(effect.label())
    if node.opacity < 0.999:
        bits.append(f"opacity {node.opacity:.2f}")
    return bits


def _signature_label(signature: tuple) -> str:
    fills, strokes, weight, radius, effects, opacity, text = signature
    bits: list[str] = []
    if fills:
        bits.append("fill " + " + ".join(fills))
    if strokes:
        bits.append("stroke " + " + ".join(strokes) + (f" {weight:g}" if weight else ""))
    if radius is not None:
        bits.append(f"r{radius:g}")
    for effect in effects:
        bits.append(effect)
    if opacity is not None:
        bits.append(f"opacity {opacity:.2f}")
    if text is not None:
        family, size, text_weight, line_height, spacing = text
        parts = []
        if size is not None:
            parts.append(f"{size:g}px")
        if text_weight is not None:
            parts.append(str(text_weight))
        if family:
            parts.append(family)
        if line_height is not None:
            parts.append(f"lh {line_height:g}")
        if spacing is not None:
            parts.append(f"ls {spacing:g}")
        if parts:
            bits.append("글자 " + "/".join(parts))
    return " · ".join(bits) or "겉모습 없음"


# ---------------------------------------------------------------- 순회
def build(
    design: Design,
    mode: str = "all",
    depth: int = 0,
    max_nodes: int = 200,
    root_ref: str = "",
    hoist_styles: bool = True,
) -> TreeView:
    mode = (mode or "all").lower()
    if mode not in MODES:
        mode = "all"

    view = TreeView(design=design, mode=mode)
    view.total_nodes = len(design.nodes)
    view.hidden = design.hidden_count

    visible = [node for node in design.nodes if node.visible and node.opacity > 0]

    # 1) 같은 모양 세기
    counts: Counter = Counter()
    first_seen: dict[tuple, str] = {}
    for node in visible:
        key = _structure(node)
        counts[key] += 1
        first_seen.setdefault(key, node.ref)

    # 2) 스타일 세기 (두 번 이상 쓰인 것만 이름을 준다)
    style_counts: Counter = Counter()
    for node in visible:
        signature = style_signature(node)
        if signature != EMPTY_SIGNATURE:
            style_counts[signature] += 1
    style_names: dict[tuple, str] = {}
    if hoist_styles:
        ordered = sorted(
            ((signature, count) for signature, count in style_counts.items() if count >= 2),
            key=lambda item: (-item[1], repr(item[0])),
        )
        for index, (signature, count) in enumerate(ordered, start=1):
            name = f"s{index}"
            view.styles[name] = (signature, count)
            style_names[signature] = name

    # 3) 순회
    start = design.root
    if root_ref:
        found = None
        for node in design.nodes:
            if node.ref.lower() == root_ref.strip().lower():
                found = node
                break
        if found is None:
            raise ValueError(f"ref={root_ref} 를 찾지 못했습니다")
        start = found

    def visit(node: Node, level: int) -> None:
        if not node.visible or node.opacity <= 0:
            return
        if mode == "text" and not has_text(node):
            return
        key = _structure(node)
        repeat_of = ""
        if counts[key] >= 2 and node.children:
            first = first_seen[key]
            if first != node.ref:
                repeat_of = first
        entry = Entry(node=node, depth=level, repeat_of=repeat_of)
        entry.style_ref = style_names.get(style_signature(node), "")
        view.entries.append(entry)
        if repeat_of:
            view.cut_nodes += 1
            return
        if depth and level + 1 >= depth:
            if node.children:
                view.cut_depth += 1
            return
        for child in node.children:
            visit(child, level + 1)

    visit(start, 0)
    return view
