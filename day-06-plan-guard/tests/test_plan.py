"""plan 로딩·모델 — 45개."""

from __future__ import annotations

import json

import pytest

from conftest import FIXED, PROPOSAL, plan_dict, plan_json, resource_change
from plan_guard.plan import (
    MASK,
    UNKNOWN,
    Change,
    Plan,
    PlanError,
    format_path,
    from_dict,
    is_sensitive_at,
    load_plan,
    mask,
    overlay_unknown,
    sensitive_paths,
    short,
)


# ------------------------------------------------------------------ 로딩
def test_loads_example_proposal() -> None:
    plan = load_plan(str(PROPOSAL))
    assert plan.terraform_version == "1.9.8"
    assert plan.format_version == "1.2"
    assert len(plan.changes) == 6


def test_loads_example_fixed() -> None:
    plan = load_plan(str(FIXED))
    assert plan.by_kind()["replace"] == 0
    assert plan.by_kind()["delete"] == 0


def test_loads_from_json_string() -> None:
    text = plan_json([resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})])
    plan = load_plan(text)
    assert len(plan.changes) == 1
    assert plan.changes[0].kind == "create"


def test_loads_fragment_without_format_version() -> None:
    data = {"resource_changes": [resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})]}
    plan = from_dict(data)
    assert plan.format_version == "1.0"


def test_missing_file_message_is_korean() -> None:
    with pytest.raises(PlanError) as exc:
        load_plan("/nope/plan.json")
    assert "찾을 수 없습니다" in str(exc.value)
    assert "terraform show -json" in str(exc.value)


def test_not_json() -> None:
    with pytest.raises(PlanError) as exc:
        load_plan("{ this is not json")
    assert "JSON" in str(exc.value)


def test_not_a_plan() -> None:
    with pytest.raises(PlanError) as exc:
        load_plan('{"hello": 1}')
    assert "terraform plan JSON" in str(exc.value)


def test_unsupported_format_version() -> None:
    with pytest.raises(PlanError) as exc:
        from_dict({"format_version": "0.1", "resource_changes": []})
    assert "지원하지 않는" in str(exc.value)


def test_empty_source() -> None:
    with pytest.raises(PlanError):
        load_plan("   ")


def test_resource_changes_not_list() -> None:
    with pytest.raises(PlanError):
        from_dict({"format_version": "1.2", "resource_changes": {}})


def test_items_without_actions_are_skipped() -> None:
    good = resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})
    bad = {"address": "aws_s3_bucket.b", "change": {"actions": []}}
    plan = from_dict(plan_dict([good, bad]))
    assert [c.address for c in plan.changes] == ["aws_s3_bucket.a"]


def test_top_level_not_object() -> None:
    with pytest.raises(PlanError):
        from_dict([])


def test_base_dir_resolution(tmp_path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(plan_json([resource_change("aws_s3_bucket.a", ["create"], None, {})]), encoding="utf-8")
    plan = load_plan("plan.json", base_dir=tmp_path)
    assert len(plan.changes) == 1
    assert plan.source.endswith("plan.json")


def test_errored_flag_kept() -> None:
    plan = from_dict(plan_dict([], errored=True, complete=False))
    assert plan.errored is True
    assert plan.complete is False


# ------------------------------------------------------------------ Change
@pytest.mark.parametrize(
    "actions,expected",
    [
        (["create"], "create"),
        (["update"], "update"),
        (["delete"], "delete"),
        (["delete", "create"], "replace"),
        (["create", "delete"], "replace"),
        (["no-op"], "noop"),
        (["read"], "read"),
    ],
)
def test_kind_detection(actions, expected) -> None:
    change = Change("a.b", "managed", "a", "b", "p", tuple(actions))
    assert change.kind == expected


def test_kind_label_korean() -> None:
    change = Change("a.b", "managed", "a", "b", "p", ("delete", "create"))
    assert change.kind_label == "재생성"


def test_create_before_destroy_order() -> None:
    change = Change("a.b", "managed", "a", "b", "p", ("create", "delete"))
    assert change.create_before_destroy is True
    other = Change("a.b", "managed", "a", "b", "p", ("delete", "create"))
    assert other.create_before_destroy is False


def test_destructive_only_on_delete() -> None:
    assert Change("a.b", "m", "a", "b", "p", ("delete",)).destructive is True
    assert Change("a.b", "m", "a", "b", "p", ("create", "delete")).destructive is True
    assert Change("a.b", "m", "a", "b", "p", ("create",)).destructive is False
    assert Change("a.b", "m", "a", "b", "p", ("update",)).destructive is False


@pytest.mark.parametrize("kind,expected", [("create", True), ("update", True), ("replace", True), ("delete", False)])
def test_writes(kind, expected) -> None:
    actions = {"create": ["create"], "update": ["update"], "replace": ["delete", "create"], "delete": ["delete"]}[kind]
    assert Change("a.b", "m", "a", "b", "p", tuple(actions)).writes is expected


def test_ref_is_document_order() -> None:
    plan = from_dict(plan_dict([
        resource_change("aws_s3_bucket.a", ["create"], None, {}),
        resource_change("aws_s3_bucket.b", ["delete"], {}, None),
    ]))
    assert [c.ref for c in plan.changes] == ["r1", "r2"]


def test_reason_label_translated() -> None:
    change = Change("a.b", "m", "a", "b", "p", ("delete",), action_reason="delete_because_no_resource_config")
    assert change.reason_label == "설정에서 빠짐"


def test_reason_label_unknown_passthrough() -> None:
    change = Change("a.b", "m", "a", "b", "p", ("delete",), action_reason="something_new")
    assert change.reason_label == "something_new"


def test_module_address() -> None:
    change = Change("module.net.aws_vpc.main", "m", "aws_vpc", "main", "p", ("create",))
    assert change.module_address == "module.net"


def test_module_address_empty_at_root() -> None:
    change = Change("aws_vpc.main", "m", "aws_vpc", "main", "p", ("create",))
    assert change.module_address == ""


# ------------------------------------------------------------------ 마스킹
def test_mask_whole_value() -> None:
    assert mask("hunter2", True) == MASK


def test_mask_nested_dict() -> None:
    value = {"user": "acme", "password": "hunter2", "nested": {"key": "abc"}}
    sensitive = {"password": True, "nested": {"key": True}}
    masked = mask(value, sensitive)
    assert masked["user"] == "acme"
    assert masked["password"] == MASK
    assert masked["nested"]["key"] == MASK


def test_mask_list_positions() -> None:
    value = ["a", "b", "c"]
    assert mask(value, [False, True, False]) == ["a", MASK, "c"]


def test_mask_keeps_missing_positions() -> None:
    assert mask(["a", "b"], [False]) == ["a", "b"]


def test_is_sensitive_at() -> None:
    sensitive = {"password": True, "nested": {"token": True}, "list": [{"x": True}]}
    assert is_sensitive_at(sensitive, ("password",)) is True
    assert is_sensitive_at(sensitive, ("nested", "token")) is True
    assert is_sensitive_at(sensitive, ("list", 0, "x")) is True
    assert is_sensitive_at(sensitive, ("nested",)) is False
    assert is_sensitive_at(sensitive, ("missing",)) is False
    assert is_sensitive_at(sensitive, ("list", 3)) is False


def test_sensitive_paths_lists_leaves() -> None:
    paths = sensitive_paths({"password": True, "nested": {"token": True}})
    assert ("password",) in paths
    assert ("nested", "token") in paths


def test_sensitive_paths_list_index() -> None:
    paths = sensitive_paths([{"x": True}])
    assert paths == [(0, "x")]


def test_overlay_unknown() -> None:
    assert overlay_unknown({"a": None, "b": 1}, {"a": True}) == {"a": UNKNOWN, "b": 1}


def test_overlay_unknown_nested() -> None:
    value = {"tags": {"a": "b"}, "id": None}
    assert overlay_unknown(value, {"id": True})["id"] == UNKNOWN


def test_change_before_masked(db_replace) -> None:
    change = from_dict(plan_dict([db_replace])).changes[0]
    assert change.before_masked()["password"] == MASK
    assert change.before_masked()["identifier"] == "acme-prod-db"


def test_change_after_with_unknown(db_replace) -> None:
    change = from_dict(plan_dict([db_replace])).changes[0]
    assert change.after_with_unknown()["id"] == UNKNOWN


# ------------------------------------------------------------------ 표기
def test_format_path() -> None:
    assert format_path(("ingress", 0, "cidr_blocks", 1)) == "ingress[0].cidr_blocks[1]"


def test_short_values() -> None:
    assert short(None) == "(없음)"
    assert short(True) == "true"
    assert short(3) == "3"
    assert short("abcdef", 3) == "ab…"
    assert short([]) == "[]"
    assert short({}) == "{}"


def test_short_list_and_dict() -> None:
    assert short(["a", "b"]) == "[a, b]"
    assert short({"a": 1}) == "{a=1}"


def test_short_long_list_counts() -> None:
    assert "4개" in short(["a", "b", "c", "d"])


def test_plan_counts_skip_noop() -> None:
    plan = from_dict(plan_dict([
        resource_change("aws_s3_bucket.a", ["create"], None, {}),
        resource_change("aws_s3_bucket.b", ["no-op"], {}, {}),
    ]))
    assert len(plan.real_changes()) == 1
    assert plan.types() == {"aws_s3_bucket": 1}


def test_plan_destructive_and_find() -> None:
    plan = load_plan(str(PROPOSAL))
    addresses = {c.address for c in plan.destructive()}
    assert "aws_instance.worker" in addresses
    assert plan.find("aws_db_instance")[0].address == "aws_db_instance.main"


def test_plan_provider_short() -> None:
    plan = load_plan(str(PROPOSAL))
    assert plan.provider_short() == {"aws": 6}


def test_plan_to_dict_roundtrip() -> None:
    plan = load_plan(str(PROPOSAL))
    data = plan.to_dict()
    assert data["changes"][0]["ref"] == "r1"
    assert len(data["changes"]) == 6
