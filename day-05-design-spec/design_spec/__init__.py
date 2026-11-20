"""design-spec — Figma 응답 모양의 디자인 파일에서 색·간격·글자를 세고 DESIGN.md 를 뽑는다.

1일 1스킬 Day 05. 원본 두 개:
  · GLips/Figma-Context-MCP (MIT) — 한 번 훑는 extractor, 스타일 세어 올리기, 같은 모양 접기
  · google-labs-code/stitch-skills 의 `design-md` (Apache-2.0) — DESIGN.md 의 다섯 칸 구조

코드는 원본에서 한 줄도 가져오지 않았습니다. 설계와 문서 구조만 참고했습니다.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .audit import Audit, audit_design, load_and_audit
from .color import Color, contrast, describe, parse_color
from .designmd import build_design_md
from .nodes import Design, DesignError, Node, load_design
from .palette import Palette, analyse_palette, background_of
from .rules import RULES, Finding
from .spacing import analyse_radii, analyse_spacing
from .typography import analyse_type
from .walk import build

__all__ = [
    "__version__",
    "Audit",
    "audit_design",
    "load_and_audit",
    "Color",
    "parse_color",
    "contrast",
    "describe",
    "build_design_md",
    "Design",
    "DesignError",
    "Node",
    "load_design",
    "Palette",
    "analyse_palette",
    "background_of",
    "RULES",
    "Finding",
    "analyse_spacing",
    "analyse_radii",
    "analyse_type",
    "build",
]
