"""간격·반경 — 기준 단위 잡기와 스케일 밖 값."""

from __future__ import annotations

import pytest

from conftest import document, node, screen
from design_spec.nodes import load_design
from design_spec.spacing import analyse_radii, analyse_spacing, pick_base

ON = [(0.0, 0.0, 100.0, 100.0)]


def spacing_design(*, gaps=(), paddings=(), radii=(), sizes=()):
    children = []
    for index, gap in enumerate(gaps):
        children.append(
            node(f"2:{index}", f"Gap{index}", at=(0, index * 10, 100, 10), layout="VERTICAL", gap=gap)
        )
    for index, padding in enumerate(paddings):
        children.append(
            node(
                f"3:{index}",
                f"Pad{index}",
                at=(0, index * 10, 100, 10),
                layout="VERTICAL",
                padding=(padding, padding, padding, padding),
            )
        )
    for index, radius in enumerate(radii):
        size = sizes[index] if index < len(sizes) else (100, 40)
        children.append(
            node(
                f"4:{index}",
                f"Radius{index}",
                "RECTANGLE",
                at=(0, index * 10, size[0], size[1]),
                radius=radius,
            )
        )
    return load_design(document(screen(*children)))


# -------------------------------------------------------------- 기준 단위
@pytest.mark.parametrize(
    "values,expected",
    [
        ([4, 8, 12, 16, 24], 4.0),
        ([8, 16, 24, 32], 8.0),
        ([8, 16, 24], 8.0),
        ([12, 24, 36], 12.0),
        ([16, 16, 16], 8.0),
        ([5, 10, 15], 5.0),
        ([6, 12, 18], 6.0),
        ([3, 6, 9], 3.0),
    ],
)
def test_pick_base(values, expected) -> None:
    base, share = pick_base([float(value) for value in values])
    assert base == expected
    assert share == pytest.approx(1.0)


def test_pick_base_prefers_a_real_unit_over_two() -> None:
    # 2 도 모두 나눠떨어지지만 기준 단위는 8 이다
    assert pick_base([8.0, 16.0, 24.0])[0] == 8.0


def test_pick_base_reports_when_nothing_fits() -> None:
    base, share = pick_base([7.0, 11.0, 13.0, 17.0])
    assert base is None
    assert share < 0.6


def test_pick_base_ignores_noise_but_keeps_the_scale() -> None:
    base, share = pick_base([8.0, 12.0, 13.0, 16.0, 24.0, 10.0])
    assert base == 4.0
    assert 0.6 <= share < 1.0


def test_pick_base_with_no_values() -> None:
    assert pick_base([]) == (None, 0.0)


# -------------------------------------------------------------- 보고
def test_off_scale_values_are_listed() -> None:
    report = analyse_spacing(spacing_design(gaps=[8, 13, 16], paddings=[10]))
    assert report.base == 4.0
    assert [value for value, _ in report.off_scale] == [10.0, 13.0]


def test_clean_spacing_has_no_off_scale() -> None:
    report = analyse_spacing(spacing_design(gaps=[8, 12, 16, 24], paddings=[16, 20]))
    assert report.base == 4.0
    assert report.off_scale == []


def test_padding_is_counted_in_spacing() -> None:
    report = analyse_spacing(spacing_design(paddings=[24, 24]))
    assert report.padding_values == [(24.0, 8)]  # 네 방향 × 두 노드
    assert report.total == 8


def test_gap_values_are_separate_from_padding() -> None:
    report = analyse_spacing(spacing_design(gaps=[12], paddings=[20]))
    assert report.gap_values == [(12.0, 1)]
    assert report.padding_values == [(20.0, 4)]
    assert report.distinct == 2


def test_distinct_counts_all_values() -> None:
    report = analyse_spacing(spacing_design(gaps=[8, 12, 16], paddings=[20, 24]))
    assert report.distinct == 5


def test_dominant_is_the_most_common_value() -> None:
    report = analyse_spacing(spacing_design(gaps=[16, 16, 8]))
    assert report.dominant == 16.0


def test_base_can_be_forced() -> None:
    report = analyse_spacing(spacing_design(gaps=[8, 16]), base=8)
    assert report.base == 8.0


def test_no_spacing_at_all() -> None:
    report = analyse_spacing(spacing_design())
    assert report.base is None
    assert report.values == []
    assert report.dominant is None


def test_absolute_position_nodes_contribute_nothing() -> None:
    design = load_design(document(screen(node("2:1", "Free", at=(0, 0, 10, 10)))))
    assert analyse_spacing(design).total == 0


# -------------------------------------------------------------- 반경
def test_radii_counts_and_pill() -> None:
    report = analyse_radii(spacing_design(radii=[8, 8, 24, 0], sizes=[(100, 40), (100, 40), (100, 48), (10, 10)]))
    assert dict(report.values)[8.0] == 2
    assert report.pill == 1
    assert report.square == 1
    assert report.distinct == 2


def test_radius_equal_to_half_height_is_a_pill() -> None:
    report = analyse_radii(spacing_design(radii=[20], sizes=[(100, 40)]))
    assert report.pill == 1


def test_radius_just_below_half_is_not_a_pill() -> None:
    report = analyse_radii(spacing_design(radii=[19.0], sizes=[(100, 40)]))
    assert report.pill == 0


def test_nodes_without_radius_are_ignored() -> None:
    design = load_design(document(screen(node("2:1", "Square", at=(0, 0, 10, 10)))))
    report = analyse_radii(design)
    assert report.distinct == 0
    assert report.square == 0
