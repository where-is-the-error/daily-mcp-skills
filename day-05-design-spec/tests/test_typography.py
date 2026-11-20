"""글자 — 단계 · 일회용 크기 · 줄 높이."""

from __future__ import annotations

import pytest

from conftest import document, screen, text
from design_spec.nodes import load_design
from design_spec.typography import analyse_type


def type_design(*rows):
    """rows: (글자, 크기, 굵기, 줄높이, 이름)"""
    children = [
        text(
            f"2:{index}",
            chars,
            name=name,
            at=(0, index * 30, 200, 24),
            size=size,
            weight=weight,
            line_height=line_height,
        )
        for index, (chars, size, weight, line_height, name) in enumerate(rows)
    ]
    return load_design(document(screen(*children)))


def test_sizes_are_counted() -> None:
    report = analyse_type(
        type_design(
            ("제목", 20, 700, 28, "Title"),
            ("본문", 14, 400, 20, "Body"),
            ("본문2", 14, 400, 20, "Body2"),
        )
    )
    assert dict(report.sizes) == {20.0: 1, 14.0: 2}
    assert report.largest() == 20.0
    assert report.smallest() == 14.0


def test_one_off_sizes_are_found() -> None:
    report = analyse_type(
        type_design(
            ("가", 20, 700, 28, "A"),
            ("나", 16, 400, 24, "B"),
            ("다", 16, 400, 24, "C"),
            ("라", 16, 400, 24, "D"),
            ("마", 15, 400, 22, "E"),
        )
    )
    assert sorted(report.one_offs) == [15.0, 20.0]


def test_one_off_needs_at_least_three_sizes() -> None:
    report = analyse_type(type_design(("가", 20, 700, 28, "A"), ("나", 15, 400, 22, "B")))
    assert report.one_offs == []


def test_close_steps_are_flagged() -> None:
    report = analyse_type(
        type_design(
            ("가", 15, 400, 22, "A"),
            ("나", 16, 400, 24, "B"),
            ("다", 20, 700, 28, "C"),
        )
    )
    assert [(lower, upper) for lower, upper, _ in report.close_steps] == [(15.0, 16.0)]


def test_wide_steps_are_not_flagged() -> None:
    report = analyse_type(
        type_design(("가", 12, 400, 18, "A"), ("나", 20, 700, 28, "B"))
    )
    assert report.close_steps == []


def test_line_ratio_is_computed() -> None:
    report = analyse_type(type_design(("가", 14, 400, 21, "A")))
    assert report.texts[0].ratio == pytest.approx(1.5)


def test_missing_line_height_is_counted_not_guessed() -> None:
    report = analyse_type(type_design(("가", 14, 400, None, "A")))
    assert report.no_line_height == 1
    assert report.texts[0].ratio is None


def test_characters_count_is_kept_for_the_cramped_rule() -> None:
    report = analyse_type(type_design(("짧은 글", 13, 400, 14, "A")))
    assert report.texts[0].chars == 4


def test_families_and_weights() -> None:
    report = analyse_type(
        type_design(("가", 14, 400, 20, "A"), ("나", 16, 700, 24, "B"), ("다", 16, 700, 24, "C"))
    )
    assert report.families == [("Pretendard", 3)]
    assert dict(report.weights) == {400: 1, 700: 2}


def test_text_without_style_is_counted_not_crashing() -> None:
    design = load_design(document(screen({"id": "2:1", "name": "Raw", "type": "TEXT", "characters": "글자"})))
    report = analyse_type(design)
    assert report.no_size == 1
    assert report.sizes == []


def test_empty_text_nodes_are_ignored() -> None:
    design = load_design(document(screen(text("2:1", "   ", size=14))))
    assert analyse_type(design).sizes == []
