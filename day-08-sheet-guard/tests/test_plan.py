"""정리 계획 — 순서·확신도·사람이 볼 것."""

from __future__ import annotations

from conftest import make
from sheet_guard.plan import ORDER, build_plan
from sheet_guard.rules import check


def plan_for(text: str, only: tuple[str, ...] = ()):
    table = make(text)
    return table, build_plan(table, check(table), only=only)


def test_plan_actions_are_ordered() -> None:
    table, plan = plan_for('시도,값\n 서울,"1,000"\n경기,"2,000"\n')
    orders = [ORDER[action.kind] for action in plan.actions]
    assert orders == sorted(orders)


def test_drop_actions_merge() -> None:
    text = "시도,값\n서울,1\n소계,3\n\n※ 단위\n경기,2\n"
    table, plan = plan_for(text)
    drops = [a for a in plan.actions if a.kind == "drop_rows"]
    assert len(drops) == 1
    assert len(drops[0].params["rows"]) >= 3
    assert {"subtotal-row", "blank-row", "footnote-row"} <= set(drops[0].reason)


def test_quarantine_action_for_ragged() -> None:
    table, plan = plan_for("a,b,c\n1,2,3\n4,5,6,7\n")
    actions = [a for a in plan.actions if a.kind == "quarantine_rows"]
    assert actions and actions[0].params["rows"] == ["r3"]


def test_to_number_note_mentions_unit_column() -> None:
    table, plan = plan_for("면적,값\n12.5㎡,1\n3.2㎡,2\n")
    action = [a for a in plan.actions if a.kind == "to_number"][0]
    assert "면적_단위" in action.note


def test_pad_leading_zeros_is_low_confidence() -> None:
    table, plan = plan_for("우편번호,값\n1234,1\n04530,2\n04531,3\n")
    action = [a for a in plan.actions if a.kind == "pad_leading_zeros"][0]
    assert action.confidence < 0.7
    assert action.needs_review is True
    assert action.params["width"] == 5


def test_only_filter() -> None:
    table, plan = plan_for(
        '시도,값\n 서울,"1,000"\n 소계,"3,000"\n경기,"2,000"\n',
        only=("subtotal-row",),
    )
    assert {a.kind for a in plan.actions} == {"drop_rows"}


def test_review_holds_unfixable_error() -> None:
    text = "이름,값\n서울,1\n부산,x\n대구,y\n광주,z\n"
    table, plan = plan_for(text)
    rules = {f.rule for f in plan.review}
    assert "mixed-type-column" in rules


def test_plan_changes_count() -> None:
    table, plan = plan_for('시도,값\n 서울,"1,000"\n경기,"2,000"\n')
    assert plan.changes >= 2


def test_plan_dict_shape() -> None:
    table, plan = plan_for("시도,값\n 서울,1\n")
    data = plan.as_dict()
    assert data["actions"] and "affects" in data
    assert set(data["actions"][0]) >= {"id", "kind", "label", "params", "reason"}


def test_no_actions_when_clean() -> None:
    table, plan = plan_for("이름,나이\n김,31\n이,28\n")
    assert plan.actions == []


def test_action_ids_are_sequential() -> None:
    table, plan = plan_for('시도,값\n 서울,"1,000"\n 소계,"3,000"\n')
    assert [a.id for a in plan.actions] == [f"a{i + 1}" for i in range(len(plan.actions))]


def test_example_plan_covers_structure_and_values(raw_table) -> None:
    plan = build_plan(raw_table, check(raw_table))
    kinds = {a.kind for a in plan.actions}
    assert {"drop_rows", "quarantine_rows", "to_number", "to_iso_date", "dedupe_rows"} <= kinds
