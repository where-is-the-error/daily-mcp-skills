"""plan 두 개 비교 · 공유용 마스킹 — 26개."""

from __future__ import annotations

import copy
import json

import pytest

from conftest import FIXED, PROPOSAL, plan_dict, resource_change
from plan_guard.compare import compare
from plan_guard.plan import MASK, from_dict, load_plan
from plan_guard.redact import redact_document, to_json


def plan_of(*changes):
    return from_dict(plan_dict(list(changes)))


# ------------------------------------------------------------------ compare
def test_counts_and_verdict_change() -> None:
    result = compare(load_plan(str(PROPOSAL)), load_plan(str(FIXED)))
    assert result.counts_before()["치명"] == 4
    assert result.counts_after()["치명"] == 0
    text = result.render()
    assert "보류" in text and "통과" in text
    assert "치명 4 → 0" in text


def test_fixed_listed() -> None:
    result = compare(load_plan(str(PROPOSAL)), load_plan(str(FIXED)))
    addresses = {d.address for d in result.fixed}
    assert "aws_db_instance.main" in addresses
    assert "aws_instance.worker" in addresses


def test_render_marks_fixed_section() -> None:
    text = compare(load_plan(str(PROPOSAL)), load_plan(str(FIXED))).render()
    assert "약해진 것" in text
    assert "aws_db_instance.main: 재생성 → 수정" in text


def test_worse_direction() -> None:
    a = plan_of(resource_change("aws_instance.a", ["update"], {"x": 1}, {"x": 2}))
    b = plan_of(resource_change("aws_instance.a", ["delete"], {"x": 1}, None))
    result = compare(a, b)
    assert result.worse and result.worse[0].address == "aws_instance.a"
    assert "강해진 것" in result.render()


def test_same_kind_is_not_listed() -> None:
    a = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    b = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    result = compare(a, b)
    assert result.changed == []


def test_added_and_removed_addresses() -> None:
    a = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    b = plan_of(resource_change("aws_instance.b", ["create"], None, {}))
    result = compare(a, b)
    assert result.added == ["aws_instance.b"]
    assert result.removed == ["aws_instance.a"]
    text = result.render()
    assert "빠진 리소스" in text and "새로 생긴 리소스" in text


def test_identical_plans_message() -> None:
    a = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    text = compare(a, a).render()
    assert "리소스 변경이 같습니다" in text


def test_remaining_risk_listed() -> None:
    a = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    b = plan_of(resource_change("aws_db_instance.d", ["delete"], {"identifier": "d"}, None))
    text = compare(a, b).render()
    assert "남은 위험" in text
    assert "데이터" in text


def test_render_warns_about_different_state() -> None:
    a = plan_of(resource_change("aws_instance.a", ["create"], None, {}))
    assert "같은 state" in compare(a, a).render()


def test_direction_labels() -> None:
    from plan_guard.compare import AddressDelta

    assert AddressDelta("a", "replace", "update").direction == "약해짐"
    assert AddressDelta("a", "update", "replace").direction == "강해짐"
    assert AddressDelta("a", "update", "update").direction == "같음"


def test_destructive_counts_shown() -> None:
    text = compare(load_plan(str(PROPOSAL)), load_plan(str(FIXED))).render()
    assert "사라지는 리소스: 2 → 0" in text


# ------------------------------------------------------------------ redact
def test_redact_masks_change_values() -> None:
    data = plan_dict([resource_change("aws_db_instance.d", ["update"],
                                      {"password": "hunter2", "identifier": "db"},
                                      {"password": "newpass", "identifier": "db"},
                                      before_sensitive={"password": True},
                                      after_sensitive={"password": True})])
    redacted, count = redact_document(data)
    change = redacted["resource_changes"][0]["change"]
    assert change["before"]["password"] == MASK
    assert change["after"]["password"] == MASK
    assert change["before"]["identifier"] == "db"
    assert count == 2


def test_redact_does_not_touch_original() -> None:
    data = plan_dict([resource_change("aws_db_instance.d", ["update"],
                                      {"password": "hunter2"}, {"password": "new"},
                                      before_sensitive={"password": True}, after_sensitive={"password": True})])
    snapshot = copy.deepcopy(data)
    redact_document(data)
    assert data == snapshot


def test_redact_planned_values() -> None:
    data = plan_dict([])
    data["planned_values"] = {
        "root_module": {
            "resources": [
                {"address": "aws_db_instance.d", "values": {"password": "hunter2", "identifier": "db"},
                 "sensitive_values": {"password": True}},
            ]
        }
    }
    redacted, count = redact_document(data)
    resource = redacted["planned_values"]["root_module"]["resources"][0]
    assert resource["values"]["password"] == MASK
    assert resource["values"]["identifier"] == "db"
    assert count == 1


def test_redact_nested_child_modules() -> None:
    data = plan_dict([])
    data["planned_values"] = {
        "root_module": {
            "resources": [],
            "child_modules": [
                {"address": "module.db",
                 "resources": [{"values": {"password": "x"}, "sensitive_values": {"password": True}}]},
            ],
        }
    }
    redacted, count = redact_document(data)
    assert count == 1
    assert redacted["_redacted"]["masked_values"] == 1


def test_redact_prior_state() -> None:
    data = plan_dict([])
    data["prior_state"] = {"values": {"root_module": {"resources": [
        {"values": {"password": "x"}, "sensitive_values": {"password": True}},
    ]}}}
    _, count = redact_document(data)
    assert count == 1


def test_redact_without_sensitive_keys() -> None:
    data = plan_dict([resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})])
    redacted, count = redact_document(data)
    assert count == 0
    assert redacted["resource_changes"][0]["change"]["after"]["bucket"] == "b"


def test_redact_adds_note() -> None:
    redacted, _ = redact_document(plan_dict([]))
    assert redacted["_redacted"]["mask"] == MASK
    assert "가린 사본" in redacted["_redacted"]["note"]


def test_redact_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        redact_document([])


def test_redact_example_plan_masks_password() -> None:
    data = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    redacted, count = redact_document(data)
    text = to_json(redacted)
    assert "correcthorsebatterystaple" not in text
    assert count >= 1


def test_to_json_is_readable() -> None:
    text = to_json({"a": 1})
    assert "\n" in text


def test_stdlib_sensitive_flag_not_confused() -> None:
    data = plan_dict([resource_change("aws_s3_bucket.a", ["update"], {"tags": {"a": "b"}}, {"tags": {"a": "c"}},
                                      before_sensitive={"tags": {}}, after_sensitive={"tags": {}})])
    redacted, count = redact_document(data)
    assert count == 0
    assert redacted["resource_changes"][0]["change"]["after"]["tags"] == {"a": "c"}
