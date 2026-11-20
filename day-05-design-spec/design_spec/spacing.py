"""간격·반경 — '4의 배수'인지, 몇 종류를 쓰는지.

디자인 파일에서 간격은 auto-layout 의 `itemSpacing` 과 `padding*`,
반경은 `cornerRadius` 에만 있습니다. 값을 0 으로 채우지 않고, **있는 값만** 셉니다.
기준 단위(base unit)는 데이터에서 고릅니다 — 2·3·4·5·6·8·10·12 중에서
가장 많은 값을 나눠떨어뜨리는 수, 동률이면 큰 쪽. (모든 값이 4의 배수면 4.)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .nodes import Design, Node

__all__ = ["SpacingReport", "RadiiReport", "analyse_spacing", "analyse_radii", "BASE_CANDIDATES"]

BASE_CANDIDATES = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0)
TOLERANCE = 0.01


def _is_multiple(value: float, base: float) -> bool:
    if base <= 0:
        return False
    ratio = value / base
    return abs(ratio - round(ratio)) <= TOLERANCE / base


@dataclass
class SpacingReport:
    base: float | None
    base_share: float
    values: list[tuple[float, int]] = field(default_factory=list)      # 간격+여백 전부
    gap_values: list[tuple[float, int]] = field(default_factory=list)
    off_scale: list[tuple[float, int]] = field(default_factory=list)
    dominant: float | None = None
    total: int = 0
    padding_values: list[tuple[float, int]] = field(default_factory=list)

    @property
    def distinct(self) -> int:
        return len(self.values)

    def share_of(self, value: float) -> int:
        for candidate, count in self.values:
            if abs(candidate - value) < 1e-9:
                return count
        return 0


@dataclass
class RadiiReport:
    values: list[tuple[float, int]] = field(default_factory=list)
    pill: int = 0          # 반경이 높이의 절반 이상 = 알약형
    square: int = 0        # 반경 0

    @property
    def distinct(self) -> int:
        return len(self.values)


def _collect(design: Design) -> tuple[list[tuple[float, Node]], list[tuple[float, Node]]]:
    gaps: list[tuple[float, Node]] = []
    paddings: list[tuple[float, Node]] = []
    for node in design.visible_nodes:
        layout = node.layout
        if not layout.auto:
            continue
        if layout.gap is not None and layout.gap > 0:
            gaps.append((layout.gap, node))
        for value in layout.padding:
            if value > 0:
                paddings.append((value, node))
    return gaps, paddings


def pick_base(values: list[float]) -> tuple[float | None, float]:
    """기준 단위와 '설명되는 비율'. 설명이 60% 미만이면 기준이 없다고 말한다.

    2·3 은 **다른 후보가 모두 60%에 못 미칠 때만** 쓴다. 값이 8·16·24 뿐이면
    2 도 전부 나눠떨어지지만, 그때 기준 단위는 8 이지 2 가 아니다.
    """
    if not values:
        return None, 0.0
    shares = {
        candidate: sum(1 for value in values if _is_multiple(value, candidate)) / len(values)
        for candidate in BASE_CANDIDATES
    }
    def rank(candidate: float) -> tuple[float, float]:
        # 전부 나눠떨어지면 큰 쪽(진짜 단위), 아니면 작은 쪽(그 단위의 배수가 섞인 것)
        return (shares[candidate], candidate if shares[candidate] >= 0.999 else -candidate)

    for group in ((4.0, 5.0, 6.0, 8.0, 10.0, 12.0), (2.0, 3.0)):
        best = max(group, key=rank)
        if shares[best] >= 0.6:
            return best, shares[best]
    return None, max(shares.values())


def analyse_spacing(design: Design, base: float | None = None) -> SpacingReport:
    gaps, paddings = _collect(design)
    all_values = [value for value, _ in gaps] + [value for value, _ in paddings]
    # 기준 단위는 **간격(gap)에서** 잡는다 — 여백은 간격 리듬을 따라오는 값이라
    # 여백까지 넣고 세면 값이 많은 쪽(카드 안 여백 24 등)이 기준을 흔든다.
    rhythm = [value for value, _ in gaps] or all_values
    if base is None:
        picked, share = pick_base(rhythm)
    else:
        picked = float(base)
        share = (
            sum(1 for value in rhythm if _is_multiple(value, picked)) / len(rhythm) if rhythm else 0.0
        )

    gap_counts = Counter(round(value, 2) for value, _ in gaps)
    pad_counts = Counter(round(value, 2) for value, _ in paddings)
    total_counts = gap_counts + pad_counts
    ordered = sorted(total_counts.items(), key=lambda item: (-item[1], item[0]))
    off = (
        [(value, count) for value, count in ordered if not _is_multiple(value, picked or 0)]
        if picked
        else []
    )
    dominant = ordered[0][0] if ordered else None
    return SpacingReport(
        base=picked,
        base_share=share,
        values=ordered,
        gap_values=sorted(gap_counts.items(), key=lambda item: (-item[1], item[0])),
        off_scale=off,
        dominant=dominant,
        total=len(all_values),
        padding_values=sorted(pad_counts.items(), key=lambda item: (-item[1], item[0])),
    )


def analyse_radii(design: Design) -> RadiiReport:
    counts: Counter = Counter()
    pill = 0
    square = 0
    for node in design.visible_nodes:
        radius = node.radius
        if radius is None:
            continue
        if radius <= 0:
            square += 1
            continue
        counts[round(radius, 2)] += 1
        size = node.size
        if size and radius >= min(size) / 2 - 0.5:
            pill += 1
    return RadiiReport(
        values=sorted(counts.items(), key=lambda item: (-item[1], item[0])),
        pill=pill,
        square=square,
    )
