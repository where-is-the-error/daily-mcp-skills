"""글자 — 크기 단계·줄 높이·글꼴·굵기.

판정에 쓰는 것
  · 크기 단계가 몇 개인지, 한 번만 쓰인 크기(일회용)가 있는지
  · 이웃한 두 단계가 너무 가까운지(14 → 15 같은 1px 차이)
  · 여러 줄로 흐를 수 있는 글자(20자 이상)의 줄 높이가 좁은지
  · 11px 미만의 작은 글자

`lineHeightPx` 가 없으면(오토) 줄 높이를 **계산하지 않습니다** — 추측하지 않습니다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .nodes import Design, Node

__all__ = ["TypeReport", "analyse_type", "MIN_SIZE", "MIN_LINE_RATIO", "MULTILINE_CHARS"]

MIN_SIZE = 11.0
MIN_LINE_RATIO = 1.15
MULTILINE_CHARS = 20
CLOSE_STEP_RATIO = 1.12
MAX_SIZES = 5


@dataclass
class SizedText:
    node: Node
    size: float
    ratio: float | None
    chars: int


@dataclass
class TypeReport:
    sizes: list[tuple[float, int]] = field(default_factory=list)
    families: list[tuple[str, int]] = field(default_factory=list)
    weights: list[tuple[int, int]] = field(default_factory=list)
    texts: list[SizedText] = field(default_factory=list)
    no_size: int = 0
    no_line_height: int = 0

    @property
    def distinct(self) -> int:
        return len(self.sizes)

    @property
    def one_offs(self) -> list[float]:
        if len(self.sizes) < 3:
            return []
        return [size for size, count in self.sizes if count == 1]

    @property
    def steps(self) -> list[tuple[float, float, float]]:
        ordered = sorted(size for size, _ in self.sizes)
        steps = []
        for lower, upper in zip(ordered, ordered[1:]):
            if lower <= 0:
                continue
            steps.append((lower, upper, upper / lower))
        return steps

    @property
    def close_steps(self) -> list[tuple[float, float, float]]:
        return [step for step in self.steps if step[2] < CLOSE_STEP_RATIO]

    def smallest(self) -> float | None:
        return min((size for size, _ in self.sizes), default=None)

    def largest(self) -> float | None:
        return max((size for size, _ in self.sizes), default=None)


def analyse_type(design: Design) -> TypeReport:
    size_counts: Counter = Counter()
    family_counts: Counter = Counter()
    weight_counts: Counter = Counter()
    texts: list[SizedText] = []
    no_size = 0
    no_line_height = 0

    for node in design.visible_nodes:
        style = node.text
        if not node.characters.strip():
            continue
        if style is None:
            no_size += 1   # 스타일이 아예 없는 글자 — 크기를 모른다
            continue
        if style.family:
            family_counts[style.family] += 1
        if style.weight:
            weight_counts[style.weight] += 1
        if style.size is None:
            no_size += 1
            continue
        size_counts[round(style.size, 2)] += 1
        ratio = style.line_ratio
        if ratio is None:
            no_line_height += 1
        texts.append(
            SizedText(
                node=node,
                size=round(style.size, 2),
                ratio=None if ratio is None else round(ratio, 3),
                chars=len(node.characters.strip()),
            )
        )

    return TypeReport(
        sizes=sorted(size_counts.items(), key=lambda item: (-item[1], -item[0])),
        families=sorted(family_counts.items(), key=lambda item: (-item[1], item[0])),
        weights=sorted(weight_counts.items(), key=lambda item: (-item[1], item[0])),
        texts=texts,
        no_size=no_size,
        no_line_height=no_line_height,
    )
