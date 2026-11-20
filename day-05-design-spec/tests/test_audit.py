"""검사 보고 — 점수 · 등급 · 정렬 · 자르기 · 고치기 순서."""

from __future__ import annotations

import json

import pytest

from conftest import document, node, screen, text
from design_spec.audit import (
    GRADE_BANDS,
    audit_design,
    load_and_audit,
    payload_json,
    render,
    render_plan,
)
from design_spec.nodes import load_design


def test_demo_before_scores_zero(audit_before) -> None:
    assert audit_before.score == 0
    assert audit_before.grade == "심각"
    assert len(audit_before.findings) >= 12


def test_demo_after_is_clean(audit_after) -> None:
    assert audit_after.findings == []
    assert audit_after.score == 100
    assert audit_after.grade == "양호"


def test_demo_after_improves_on_before(audit_before, audit_after) -> None:
    assert audit_after.score > audit_before.score
    assert audit_after.analysis.palette.distinct <= audit_before.analysis.palette.distinct
    assert audit_after.analysis.typography.distinct < audit_before.analysis.typography.distinct


def test_score_drops_by_severity_weight_once_per_rule() -> None:
    design = load_design(
        document(
            screen(
                text("2:1", "가", color="#9AA0A6", at=(0, 0, 100, 20)),
                text("2:2", "나", color="#9AA0A6", at=(0, 30, 100, 20)),
                text("2:3", "다", color="#9AA0A6", at=(0, 60, 100, 20)),
            )
        )
    )
    audit = audit_design(design)
    contrast = [finding for finding in audit.findings if finding.rule == "contrast-text"]
    assert len(contrast) == 3            # 위반은 3건
    assert audit.penalty == 25           # 감점은 한 번
    assert audit.score == 75


def test_score_is_capped_at_zero() -> None:
    audit = load_and_audit("examples/demo/before.json")
    assert audit.score == 0


@pytest.mark.parametrize("score,grade", [(100, "양호"), (90, "양호"), (89, "주의"), (70, "주의"), (69, "위험"), (40, "위험"), (39, "심각"), (0, "심각")])
def test_grade_bands(score, grade) -> None:
    from design_spec.audit import _grade

    assert _grade(score) == grade


def test_findings_are_sorted_by_severity(audit_before) -> None:
    order = [finding.severity for finding in audit_before.sorted_findings()]
    ranks = {"치명": 0, "심각": 1, "보통": 2}
    assert order == sorted(order, key=lambda severity: ranks[severity])


def test_render_has_the_summary_and_sections(audit_before) -> None:
    text_out = render(audit_before)
    assert "# design-spec" in text_out
    assert "점수 **0/100**" in text_out
    assert "## 위반" in text_out
    assert "고치기:" in text_out


def test_render_respects_max_per_rule(audit_before) -> None:
    short = render(audit_before, max_per_rule=1)
    long = render(audit_before, max_per_rule=5)
    assert len(short) < len(long)
    assert "곳 더" in short


def test_render_says_when_clean(audit_after) -> None:
    assert "위반 없음" in render(audit_after)


def test_render_lists_unjudged_items(before_design) -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Hero",
                    at=(0, 0, 100, 100),
                    fills=[{"type": "IMAGE", "imageRef": "x"}],
                    children=[text("2:2", "배너", at=(0, 0, 50, 20))],
                )
            )
        )
    )
    assert "판정하지 않은 것" in render(audit_design(design))


def test_json_payload_is_machine_readable(audit_before) -> None:
    data = json.loads(payload_json(audit_before))
    assert data["score"] == 0
    assert data["grade"] == "심각"
    assert {"contrast-text", "touch-target"} <= {item["rule"] for item in data["violations"]}
    assert data["stats"]["nodes"] > 20
    assert data["palette"] and "hex" in data["palette"][0]


def test_json_payload_has_unjudged_section(audit_before) -> None:
    assert isinstance(json.loads(payload_json(audit_before))["not_judged"], list)


def test_rule_filter_limits_findings(audit_before) -> None:
    design = audit_before.design
    filtered = audit_design(design, rule_ids=["contrast-text"])
    assert {finding.rule for finding in filtered.findings} == {"contrast-text"}


def test_unknown_rule_id_is_ignored() -> None:
    audit = audit_design(load_design(document(screen())), rule_ids=["없는규칙"])
    assert audit.findings == []


def test_plan_orders_by_severity_first(audit_before) -> None:
    plan = render_plan(audit_before)
    first = next(line for line in plan.splitlines() if line.startswith("1. **"))
    assert "치명" in first


def test_plan_says_when_nothing_to_do(audit_after) -> None:
    assert render_plan(audit_after).startswith("✅")


def test_plan_respects_max_steps(audit_before) -> None:
    plan = render_plan(audit_before, max_steps=2)
    assert plan.count("바꿀 것") == 2


def test_stats_report_the_numbers(audit_before) -> None:
    stats = audit_before.stats()
    assert stats["screens"] == 1
    assert stats["colors"] == 10
    assert stats["type_sizes"] == 6
    assert stats["spacing_base"] == 4.0


def test_min_touch_changes_the_score() -> None:
    audit = load_and_audit("examples/demo/before.json", min_touch=24)
    touch = [finding for finding in audit.findings if finding.rule == "touch-target"]
    assert touch == []
