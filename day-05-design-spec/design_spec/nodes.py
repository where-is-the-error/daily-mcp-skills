"""디자인 파일 읽기 — Figma REST 응답 모양(또는 그와 같은 모양)을 노드 트리로.

받는 것
  · `{"name":…, "document": {…}}`            Figma `GET /v1/files/:key`
  · `{"nodes": {"1:2": {"document": {…}}}}`  Figma `GET /v1/files/:key/nodes`
  · `{"document": {…}}` · 노드 하나 · 노드 배열

없는 값은 없다고 둡니다(0 으로 채우지 않습니다). 좌표·크기가 아예 없으면
자식들의 상자를 합쳐 추정하고, 추정했다는 사실을 `box_estimated` 에 남깁니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .color import Color, ColorError, parse_color

__all__ = [
    "Fill",
    "Effect",
    "TextStyle",
    "Layout",
    "Node",
    "Design",
    "load_design",
    "DesignError",
]

CONTAINER_TYPES = {
    "DOCUMENT", "CANVAS", "FRAME", "GROUP", "SECTION", "COMPONENT",
    "COMPONENT_SET", "INSTANCE", "BOOLEAN_OPERATION", "SLICE",
}
SCREEN_TYPES = {"FRAME", "COMPONENT", "SECTION", "GROUP"}
INTERACTIVE_HINT = (
    "button", "btn", "버튼", "icon", "아이콘", "tab", "탭", "chip", "link", "링크",
    "checkbox", "radio", "toggle", "switch", "input", "field", "입력",
)


class DesignError(ValueError):
    """디자인 파일로 읽을 수 없음."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("px", "").strip())
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class Fill:
    """칠하기 한 겹. `color` 가 None 이면 단색이 아니다(그라디언트·이미지·비디오)."""

    kind: str = "solid"          # solid | gradient | image | video | unknown | none
    color: Color | None = None
    opacity: float = 1.0
    style_ref: str = ""

    @property
    def solid(self) -> bool:
        return self.kind == "solid" and self.color is not None

    def effective(self) -> Color | None:
        if self.color is None:
            return None
        return self.color.with_alpha(self.color.a * self.opacity)

    def label(self) -> str:
        if self.solid:
            color = self.effective()
            return color.css() if color is not None else "#?"
        return {"gradient": "그라디언트", "image": "이미지", "video": "비디오"}.get(
            self.kind, "단색 아님"
        )


@dataclass(frozen=True)
class Effect:
    kind: str
    radius: float | None = None
    offset: tuple[float, float] = (0.0, 0.0)
    color: Color | None = None

    def label(self) -> str:
        if self.kind == "drop_shadow" and self.color is not None:
            spread = self.radius or 0.0
            return f"그림자 0 {int(self.offset[1])}px {int(spread)}px {self.color.css()}"
        return {"drop_shadow": "그림자", "inner_shadow": "안쪽 그림자",
                "layer_blur": "블러", "background_blur": "배경 블러"}.get(self.kind, self.kind)


@dataclass(frozen=True)
class TextStyle:
    family: str = ""
    size: float | None = None
    weight: int | None = None
    line_height: float | None = None
    letter_spacing: float | None = None
    style_ref: str = ""

    def label(self) -> str:
        bits = []
        if self.size is not None:
            bits.append(f"{self.size:g}px")
        if self.weight is not None:
            bits.append(str(self.weight))
        if self.line_height is not None:
            bits.append(f"lh {self.line_height:g}")
        return "/".join(bits)

    @property
    def line_ratio(self) -> float | None:
        if self.line_height is None or not self.size:
            return None
        return self.line_height / self.size

    @property
    def bold(self) -> bool:
        return (self.weight or 400) >= 700


@dataclass(frozen=True)
class Layout:
    mode: str = "NONE"                    # NONE | HORIZONTAL | VERTICAL
    gap: float | None = None
    padding: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # 좌 상 우 하
    clips: bool = False

    @property
    def auto(self) -> bool:
        return self.mode.upper() in {"HORIZONTAL", "VERTICAL"}

    def gaps(self) -> list[float]:
        return [] if self.gap is None else [self.gap]


@dataclass
class Node:
    id: str
    name: str
    type: str
    parent: "Node | None" = None
    box: tuple[float, float, float, float] | None = None   # x, y, w, h
    box_estimated: bool = False
    fills: list[Fill] = field(default_factory=list)
    strokes: list[Fill] = field(default_factory=list)
    stroke_weight: float | None = None
    radius: float | None = None
    effects: list[Effect] = field(default_factory=list)
    opacity: float = 1.0
    visible: bool = True
    characters: str = ""
    text: TextStyle | None = None
    layout: Layout = field(default_factory=Layout)
    styles: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    ref: str = ""
    repeat_of: str = ""

    # ------------------------------------------------------------ 성질
    @property
    def path(self) -> list[str]:
        chain: list[str] = []
        node: Node | None = self
        while node is not None and node.type.upper() not in {"DOCUMENT", "CANVAS"}:
            if node.name:
                chain.append(node.name)
            node = node.parent
        return list(reversed(chain))

    @property
    def breadcrumb(self) -> str:
        return " > ".join(self.path)

    @property
    def is_text(self) -> bool:
        return self.type.upper() == "TEXT" or bool(self.characters)

    @property
    def is_container(self) -> bool:
        return self.type.upper() in CONTAINER_TYPES and not self.is_text

    @property
    def area(self) -> float:
        if self.box is None:
            return 0.0
        return max(0.0, self.box[2]) * max(0.0, self.box[3])

    @property
    def size(self) -> tuple[float, float] | None:
        if self.box is None:
            return None
        return (self.box[2], self.box[3])

    def solid_fill(self) -> Color | None:
        """가장 위에 있는 불투명에 가까운 단색 (여러 겹이면 위에서부터 합성)."""
        stack = [fill for fill in self.fills if fill.solid]
        if not stack:
            return None
        result: Color | None = None
        # fills 는 아래→위 순서. 뒤에서부터 얹는다.
        for fill in stack:
            color = fill.effective()
            if color is None:
                continue
            result = color if result is None else color.over(result)
        return result

    def opaque_fill(self) -> Color | None:
        color = self.solid_fill()
        return color if color is not None and color.a >= 0.999 else None

    def non_solid_fill(self) -> Fill | None:
        for fill in self.fills:
            if not fill.solid:
                return fill
        return None

    def stroke_color(self) -> Color | None:
        for fill in self.strokes:
            color = fill.effective()
            if color is not None:
                return color
        return None

    @property
    def has_named_style(self) -> bool:
        return any(value for value in self.styles.values())

    @property
    def is_interactive(self) -> bool:
        name = self.name.lower()
        if any(hint in name for hint in INTERACTIVE_HINT):
            return True
        return False

    def walk(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def describe_size(self) -> str:
        if self.box is None:
            return "크기 없음"
        return f"{self.box[2]:g}×{self.box[3]:g}"


@dataclass
class Design:
    title: str
    root: Node
    source: str = ""
    page: str = ""

    @property
    def nodes(self) -> list[Node]:
        return [node for node in self.root.walk()]

    @property
    def visible_nodes(self) -> list[Node]:
        return [node for node in self.nodes if node.visible and node.opacity > 0]

    @property
    def screens(self) -> list[Node]:
        """화면(최상위 프레임) 목록 — DOCUMENT/CANVAS 아래 첫 세대."""
        result: list[Node] = []
        for node in self.root.walk():
            parent_type = node.parent.type.upper() if node.parent is not None else ""
            if parent_type in {"DOCUMENT", "CANVAS"} and node.type.upper() != "CANVAS":
                if node.type.upper() in SCREEN_TYPES or node.children:
                    result.append(node)
        if result:
            return result
        if self.root.type.upper() in {"DOCUMENT", "CANVAS"}:
            return [node for node in self.root.children if node.visible] or [self.root]
        return [self.root] if self.root.children else []

    @property
    def texts(self) -> list[Node]:
        return [node for node in self.visible_nodes if node.is_text and node.characters.strip()]

    @property
    def hidden_count(self) -> int:
        return sum(1 for node in self.nodes if not node.visible or node.opacity <= 0)


# --------------------------------------------------------------------- 파싱
def _parse_fill(raw: Any, style_ref: str = "") -> Fill:
    if not isinstance(raw, dict):
        return Fill(kind="unknown")
    kind_raw = str(raw.get("type", "")).upper()
    if raw.get("visible") is False:
        return Fill(kind="none", style_ref=style_ref)
    opacity = _number(raw.get("opacity"))
    opacity = 1.0 if opacity is None else opacity
    if kind_raw in ("GRADIENT_LINEAR", "GRADIENT_RADIAL", "GRADIENT_ANGULAR", "GRADIENT_DIAMOND"):
        return Fill(kind="gradient", opacity=opacity, style_ref=style_ref)
    if kind_raw in ("IMAGE", "VIDEO"):
        return Fill(kind=kind_raw.lower(), opacity=opacity, style_ref=style_ref)
    if kind_raw and kind_raw != "SOLID":
        return Fill(kind="unknown", opacity=opacity, style_ref=style_ref)
    color_raw = raw.get("color", raw.get("hex"))
    if color_raw is None:
        return Fill(kind="none", opacity=opacity, style_ref=style_ref)
    try:
        color = parse_color(color_raw)
    except ColorError:
        return Fill(kind="unknown", opacity=opacity, style_ref=style_ref)
    return Fill(kind="solid", color=color, opacity=opacity, style_ref=style_ref)


def _parse_paint_list(raw: Any, style_ref: str = "") -> list[Fill]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [fill for fill in (_parse_fill(item, style_ref) for item in raw) if fill.kind != "none"]


def _parse_effects(raw: Any) -> list[Effect]:
    if not isinstance(raw, list):
        return []
    result: list[Effect] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("visible") is False:
            continue
        kind_raw = str(item.get("type", "")).upper()
        if kind_raw == "DROP_SHADOW":
            kind = "drop_shadow"
        elif kind_raw == "INNER_SHADOW":
            kind = "inner_shadow"
        elif kind_raw in ("LAYER_BLUR", "BACKGROUND_BLUR"):
            kind = "layer_blur" if kind_raw == "LAYER_BLUR" else "background_blur"
        else:
            continue
        offset = item.get("offset") or {}
        color = None
        if isinstance(item.get("color"), dict | str):
            try:
                color = parse_color(item["color"])
            except ColorError:
                color = None
        result.append(
            Effect(
                kind=kind,
                radius=_number(item.get("radius")),
                offset=(_number(offset.get("x")) or 0.0, _number(offset.get("y")) or 0.0),
                color=color,
            )
        )
    return result


def _parse_box(raw: dict) -> tuple[float, float, float, float] | None:
    box = raw.get("absoluteBoundingBox") or raw.get("absoluteRenderBounds")
    if isinstance(box, dict):
        x, y = _number(box.get("x")), _number(box.get("y"))
        w, h = _number(box.get("width")), _number(box.get("height"))
        if None not in (w, h):
            return (x or 0.0, y or 0.0, w or 0.0, h or 0.0)
    size = raw.get("size")
    if isinstance(size, dict):
        w, h = _number(size.get("x") or size.get("width")), _number(size.get("y") or size.get("height"))
        if None not in (w, h):
            return (_number(raw.get("x")) or 0.0, _number(raw.get("y")) or 0.0, w or 0.0, h or 0.0)
    x, y = _number(raw.get("x")), _number(raw.get("y"))
    w, h = _number(raw.get("width")), _number(raw.get("height"))
    if w is not None and h is not None:
        return (x or 0.0, y or 0.0, w, h)
    return None


def _parse_layout(raw: dict) -> Layout:
    mode = str(raw.get("layoutMode", "NONE") or "NONE").upper()
    padding = (
        _number(raw.get("paddingLeft")) or 0.0,
        _number(raw.get("paddingTop")) or 0.0,
        _number(raw.get("paddingRight")) or 0.0,
        _number(raw.get("paddingBottom")) or 0.0,
    )
    return Layout(
        mode=mode,
        gap=_number(raw.get("itemSpacing")),
        padding=padding,
        clips=bool(raw.get("clipsContent", False)),
    )


def _parse_text_style(raw: dict, styles: dict[str, str]) -> TextStyle | None:
    style = raw.get("style")
    if not isinstance(style, dict):
        return None
    return TextStyle(
        family=str(style.get("fontFamily", "") or ""),
        size=_number(style.get("fontSize")),
        weight=int(_number(style.get("fontWeight")) or 0) or None,
        line_height=_number(style.get("lineHeightPx")),
        letter_spacing=_number(style.get("letterSpacing")),
        style_ref=str(styles.get("text", "") or ""),
    )


def _styles(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    styles = raw.get("styles")
    if isinstance(styles, dict):
        for key, value in styles.items():
            if value:
                out[str(key)] = str(value)
    for key in ("fillStyleId", "strokeStyleId", "textStyleId", "effectStyleId"):
        value = raw.get(key)
        if value:
            out[key.replace("StyleId", "").replace("fill", "fills").replace("stroke", "strokes")] = str(value)
    return out


def _parse_node(raw: Any, parent: Node | None, counter: list[int]) -> Node:
    if not isinstance(raw, dict):
        raise DesignError("노드가 객체가 아닙니다")
    counter[0] += 1
    node_id = str(raw.get("id") or f"n{counter[0]}")
    node_type = str(raw.get("type", "") or ("TEXT" if raw.get("characters") else "NODE")).upper()
    styles = _styles(raw)
    fill_style = styles.get("fills", "")
    stroke_style = styles.get("strokes", "")
    opacity = _number(raw.get("opacity"))
    node = Node(
        id=node_id,
        name=str(raw.get("name", "") or ""),
        type=node_type,
        parent=parent,
        box=_parse_box(raw),
        fills=_parse_paint_list(raw.get("fills"), fill_style),
        strokes=_parse_paint_list(raw.get("strokes"), stroke_style),
        stroke_weight=_number(raw.get("strokeWeight")),
        radius=_number(raw.get("cornerRadius")),
        effects=_parse_effects(raw.get("effects")),
        opacity=1.0 if opacity is None else max(0.0, min(1.0, opacity)),
        visible=raw.get("visible", True) is not False,
        characters=str(raw.get("characters", "") or ""),
        text=_parse_text_style(raw, styles),
        layout=_parse_layout(raw),
        styles=styles,
    )
    if node.radius is None and isinstance(raw.get("rectangleCornerRadii"), list):
        radii = [_number(value) for value in raw["rectangleCornerRadii"] if _number(value) is not None]
        if radii:
            node.radius = max(radii)
    children_raw = raw.get("children")
    if isinstance(children_raw, list):
        for child_raw in children_raw:
            node.children.append(_parse_node(child_raw, node, counter))
    if node.box is None and node.children and node_type not in {"DOCUMENT", "CANVAS"}:
        boxes = [child.box for child in node.children if child.box is not None]
        if boxes:
            left = min(box[0] for box in boxes)
            top = min(box[1] for box in boxes)
            right = max(box[0] + box[2] for box in boxes)
            bottom = max(box[1] + box[3] for box in boxes)
            node.box = (left, top, right - left, bottom - top)
            node.box_estimated = True
    return node


def _find_document(raw: Any) -> tuple[dict, str]:
    if isinstance(raw, list):
        if not raw:
            raise DesignError("빈 노드 목록입니다")
        return {"type": "DOCUMENT", "name": "", "children": raw}, ""
    if not isinstance(raw, dict):
        raise DesignError("디자인 파일이 객체가 아닙니다")
    if isinstance(raw.get("document"), dict):
        document = raw["document"]
        title = str(raw.get("name") or document.get("name") or "")
        return document, title
    if isinstance(raw.get("nodes"), dict):
        # GET /v1/files/:key/nodes — 화면 하나만 골라 받은 응답
        documents = []
        for entry in raw["nodes"].values():
            if isinstance(entry, dict) and isinstance(entry.get("document"), dict):
                documents.append(entry["document"])
        if not documents:
            raise DesignError("nodes 안에 document 가 없습니다")
        return {"type": "DOCUMENT", "name": "", "children": documents}, ""
    if "children" in raw or "type" in raw:
        return raw, str(raw.get("name", "") or "")
    raise DesignError("Figma 파일 모양이 아닙니다 (document·nodes·children 중 하나가 필요합니다)")


def load_design(source: Any, base_dir: Path | None = None) -> Design:
    """경로 · JSON 문자열 · 이미 만든 dict 를 Design 으로."""
    label = ""
    if isinstance(source, Design):
        return source
    if isinstance(source, (dict, list)):
        raw = source
    elif isinstance(source, Path):
        label = str(source)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DesignError(f"JSON 이 아닙니다: {exc.msg} (줄 {exc.lineno})") from exc
    elif isinstance(source, str):
        text = source.strip()
        if text.startswith("{") or text.startswith("["):
            label = "inline"
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DesignError(f"JSON 이 아닙니다: {exc.msg} (줄 {exc.lineno})") from exc
        else:
            path = Path(text)
            if not path.is_absolute() and base_dir is not None and not path.exists():
                path = base_dir / text
            if not path.exists():
                raise DesignError(f"파일이 없습니다: {text}")
            label = str(path)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise DesignError(f"JSON 이 아닙니다: {exc.msg} (줄 {exc.lineno})") from exc
    else:
        raise DesignError(f"읽을 수 없는 형식: {type(source).__name__}")

    document, title = _find_document(raw)
    counter = [0]
    root = _parse_node(document, None, counter)
    page = str(document.get("name", "") or "")
    design = Design(title=title or page or "Untitled", root=root, source=label, page=page)
    for index, node in enumerate(design.nodes, start=1):
        node.ref = f"e{index}"
    return design
