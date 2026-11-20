"""테스트 도우미 — 작은 디자인 파일을 손으로 만들기 위한 최소한의 도구."""

from __future__ import annotations

from pathlib import Path

import pytest

from design_spec import load_design

ROOT = Path(__file__).resolve().parent.parent


def box(x: float, y: float, width: float, height: float) -> dict:
    return {"x": x, "y": y, "width": width, "height": height}


def solid(hex_value: str, opacity: float | None = None) -> dict:
    """CSS 16진수를 Figma 의 0~1 실수 색으로."""
    text = hex_value.lstrip("#")
    r, g, b = (int(text[i: i + 2], 16) / 255 for i in (0, 2, 4))
    paint = {"type": "SOLID", "color": {"r": r, "g": g, "b": b, "a": 1}}
    if opacity is not None:
        paint["opacity"] = opacity
    return paint


def node(
    node_id: str,
    name: str,
    node_type: str = "FRAME",
    *,
    at: tuple[float, float, float, float] | None = None,
    children: list[dict] | None = None,
    fill: str | None = None,
    stroke: str | None = None,
    stroke_weight: float | None = 1,
    radius: float | None = None,
    chars: str | None = None,
    size: float | None = None,
    weight: int | None = 400,
    line_height: float | None = None,
    layout: str | None = None,
    gap: float | None = None,
    padding: tuple[float, float, float, float] | None = None,
    styles: dict | None = None,
    clip: bool = False,
    visible: bool | None = None,
    opacity: float | None = None,
    effects: list[dict] | None = None,
    **extra,
) -> dict:
    data: dict = {"id": node_id, "name": name, "type": node_type}
    if at is not None:
        data["absoluteBoundingBox"] = box(*at)
    if fill is not None:
        data["fills"] = [solid(fill)]
    if stroke is not None:
        data["strokes"] = [solid(stroke)]
        data["strokeWeight"] = stroke_weight
    if radius is not None:
        data["cornerRadius"] = radius
    if chars is not None:
        data["characters"] = chars
    if size is not None or line_height is not None:
        data["style"] = {
            "fontFamily": "Pretendard",
            "fontSize": size,
            "fontWeight": weight,
            "lineHeightPx": line_height,
        }
    if layout is not None:
        data["layoutMode"] = layout
    if gap is not None:
        data["itemSpacing"] = gap
    if padding is not None:
        left, top, right, bottom = padding
        data.update(
            paddingLeft=left, paddingTop=top, paddingRight=right, paddingBottom=bottom
        )
    if styles is not None:
        data["styles"] = styles
    if clip:
        data["clipsContent"] = True
    if visible is not None:
        data["visible"] = visible
    if opacity is not None:
        data["opacity"] = opacity
    if effects is not None:
        data["effects"] = effects
    if children:
        data["children"] = children
    data.update(extra)
    return data


def text(
    node_id: str,
    chars: str,
    *,
    name: str | None = None,
    at: tuple[float, float, float, float] = (0, 0, 100, 20),
    color: str = "#111827",
    size: float = 14,
    weight: int = 400,
    line_height: float | None = None,
    styles: dict | None = None,
    **extra,
) -> dict:
    return node(
        node_id,
        name or chars,
        "TEXT",
        at=at,
        chars=chars,
        fill=color,
        size=size,
        weight=weight,
        line_height=line_height,
        styles=styles,
        **extra,
    )


def document(*screens: dict, name: str = "테스트 화면") -> dict:
    return {
        "name": name,
        "document": {
            "id": "0:0",
            "name": "Page 1",
            "type": "DOCUMENT",
            "children": [
                {"id": "1:0", "name": "Page 1", "type": "CANVAS", "children": list(screens)}
            ],
        },
    }


def screen(*children: dict, box_at=(0, 0, 390, 844), name: str = "Screen", fill="#FFFFFF") -> dict:
    return node("1:1", name, "FRAME", at=box_at, fill=fill, children=list(children))


@pytest.fixture
def before_file() -> Path:
    return ROOT / "examples" / "demo" / "before.json"


@pytest.fixture
def after_file() -> Path:
    return ROOT / "examples" / "demo" / "after.json"


@pytest.fixture
def before_design(before_file):
    return load_design(before_file)


@pytest.fixture
def after_design(after_file):
    return load_design(after_file)


@pytest.fixture
def simple_design():
    """버튼 하나 + 글자 하나 — 규칙 하나씩 확인할 때 쓰는 최소 화면."""
    return load_design(
        document(
            screen(
                text("2:1", "저장", at=(16, 16, 60, 20), color="#111827", size=14),
                node("2:2", "Button/Save", "FRAME", at=(16, 44, 120, 48), fill="#0057FF", radius=8),
            )
        )
    )


@pytest.fixture
def audit_before(before_design):
    from design_spec.audit import audit_design

    return audit_design(before_design)


@pytest.fixture
def audit_after(after_design):
    from design_spec.audit import audit_design

    return audit_design(after_design)
