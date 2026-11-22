"""속성 diff — 45개."""

from __future__ import annotations

import pytest

from conftest import plan_dict, resource_change
from plan_guard.differences import (
    AttrDiff,
    canonical,
    describe,
    diff_change,
    identity_of,
    key_values,
    match_lists,
    summary,
)
from plan_guard.plan import MASK, from_dict


def change_of(*args, **kwargs):
    return from_dict(plan_dict([resource_change(*args, **kwargs)])).changes[0]


def paths(change) -> dict[str, str]:
    return {d.path: d.kind for d in diff_change(change)}


# ------------------------------------------------------------------ 기본
def test_changed_scalar() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"acl": "private"}, {"acl": "public-read"})
    diffs = diff_change(change)
    assert len(diffs) == 1
    assert diffs[0].path == "acl"
    assert diffs[0].kind == "changed"
    assert diffs[0].before == "private"
    assert diffs[0].after == "public-read"


def test_added_attribute() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"bucket": "b"}, {"bucket": "b", "acl": "private"})
    assert paths(change) == {"acl": "added"}


def test_removed_attribute() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"bucket": "b", "acl": "private"}, {"bucket": "b"})
    assert paths(change) == {"acl": "removed"}


def test_no_change_yields_nothing() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"bucket": "b"}, {"bucket": "b"})
    assert diff_change(change) == []


def test_create_diff_marks_new_values() -> None:
    change = change_of("aws_instance.a", ["create"], None, {"instance_type": "t3.small"})
    diffs = diff_change(change)
    assert diffs[0].kind == "added"


def test_delete_diff_marks_removed_values() -> None:
    change = change_of("aws_instance.a", ["delete"], {"instance_type": "t3.small"}, None)
    assert diff_change(change)[0].kind == "removed"


def test_nested_dict_walked() -> None:
    before = {"tags": {"Team": "platform", "Env": "prod"}}
    after = {"tags": {"Team": "platform", "Env": "dev"}}
    change = change_of("aws_s3_bucket.a", ["update"], before, after)
    assert paths(change) == {"tags.Env": "changed"}


def test_keys_sorted_deterministically() -> None:
    before = {"b": 1, "a": 1}
    after = {"b": 2, "a": 2}
    change = change_of("aws_s3_bucket.a", ["update"], before, after)
    assert [d.path for d in diff_change(change)] == ["a", "b"]


# ------------------------------------------------------------------ 소음 제거
def test_empty_string_vs_missing_is_ignored() -> None:
    change = change_of("aws_security_group.a", ["update"], {"description": ""}, {})
    assert diff_change(change) == []


def test_empty_list_vs_missing_is_ignored() -> None:
    change = change_of("aws_security_group.a", ["update"], {}, {"security_groups": []})
    assert diff_change(change) == []


def test_missing_vs_real_value_is_kept() -> None:
    change = change_of("aws_security_group.a", ["update"], {}, {"description": "api"})
    assert paths(change) == {"description": "added"}


def test_false_value_is_not_treated_as_empty() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"force_destroy": False}, {})
    assert paths(change) == {"force_destroy": "removed"}


# ------------------------------------------------------------------ 목록
def test_match_lists_exact_items_regardless_of_order() -> None:
    before = [{"a": 1}, {"b": 2}]
    after = [{"b": 2}, {"a": 1}]
    pairs, only_b, only_a = match_lists(before, after)
    assert only_b == [] and only_a == []
    assert sorted(pairs) == [(0, 1), (1, 0)]


def test_match_lists_by_identity() -> None:
    before = [{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"]}]
    after = [{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}]
    pairs, _, _ = match_lists(before, after)
    assert pairs == [(0, 0)]


def test_match_lists_leftovers() -> None:
    pairs, only_b, only_a = match_lists([{"a": 1}], [{"b": 2}, {"c": 3}])
    assert len(pairs) == 1
    assert only_a == [1]


def test_security_group_rule_diff_uses_identity_path(sg_update) -> None:
    change = from_dict(plan_dict([sg_update])).changes[0]
    diffs = diff_change(change)
    assert len(diffs) == 1
    assert diffs[0].path == "ingress[tcp/22-22].cidr_blocks[0]"
    assert diffs[0].before == "10.0.0.0/8"
    assert diffs[0].after == "0.0.0.0/0"


def test_reordered_rules_produce_no_diff(sg_update) -> None:
    before = {"ingress": [{"from_port": 22, "to_port": 22, "protocol": "tcp"},
                          {"from_port": 443, "to_port": 443, "protocol": "tcp"}]}
    after = {"ingress": list(reversed(before["ingress"]))}
    change = change_of("aws_security_group.a", ["update"], before, after)
    assert diff_change(change) == []


def test_new_rule_block_is_added(sg_update) -> None:
    before = {"ingress": [{"from_port": 22, "to_port": 22, "protocol": "tcp"}]}
    after = {"ingress": before["ingress"] + [{"from_port": 3389, "to_port": 3389, "protocol": "tcp"}]}
    change = change_of("aws_security_group.a", ["update"], before, after)
    assert paths(change) == {"ingress[tcp/3389-3389]": "added"}


def test_identity_of_rule() -> None:
    assert identity_of({"from_port": 22, "to_port": 22, "protocol": "tcp"}) == "tcp/22-22"


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"name": "a"}, "name=a"),
        ({"key": "k"}, "key=k"),
        ({"id": "i-1"}, "id=i-1"),
        ({"other": 1}, None),
        ("string", None),
    ],
)
def test_identity_of_variants(item, expected) -> None:
    assert identity_of(item) == expected


def test_canonical_is_order_insensitive() -> None:
    assert canonical({"a": 1, "b": 2}) == canonical({"b": 2, "a": 1})


# ------------------------------------------------------------------ 재생성
def test_replace_turns_removed_into_unknown(db_replace) -> None:
    change = from_dict(plan_dict([db_replace])).changes[0]
    kinds = {d.path: d.kind for d in diff_change(change)}
    assert kinds["storage_encrypted"] == "changed"
    assert kinds["id"] == "unknown"


def test_no_duplicate_paths(db_replace) -> None:
    change = from_dict(plan_dict([db_replace])).changes[0]
    keys = [(d.path, d.kind) for d in diff_change(change)]
    assert len(keys) == len(set(keys))


def test_unknown_from_after_unknown() -> None:
    change = change_of(
        "aws_instance.a", ["create"], None, {"id": None},
        after_unknown={"id": True},
    )
    assert any(d.path == "id" and d.kind == "unknown" for d in diff_change(change))


def test_unknown_can_be_skipped() -> None:
    change = change_of(
        "aws_instance.a", ["create"], None, {"id": None},
        after_unknown={"id": True},
    )
    assert all(d.kind != "unknown" for d in diff_change(change, include_unknown=False))


# ------------------------------------------------------------------ 민감값
def test_sensitive_flag_on_changed_value() -> None:
    change = change_of(
        "aws_db_instance.a", ["update"],
        {"password": "old"}, {"password": "new"},
        before_sensitive={"password": True}, after_sensitive={"password": True},
    )
    diff = diff_change(change)[0]
    assert diff.sensitive is True
    assert MASK in diff.line()
    assert "old" not in diff.line() and "new" not in diff.line()


def test_sensitive_detected_when_only_after_flagged() -> None:
    change = change_of(
        "aws_db_instance.a", ["update"], {"password": "old"}, {"password": "new"},
        after_sensitive={"password": True},
    )
    assert diff_change(change)[0].sensitive is True


# ------------------------------------------------------------------ 표시
def test_summary_counts() -> None:
    diffs = [AttrDiff("a", "changed", 1, 2), AttrDiff("b", "added", None, 3), AttrDiff("c", "unknown")]
    assert summary(diffs) == {"changed": 1, "added": 1, "removed": 0, "unknown": 1}


def test_describe_shows_arrow() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"acl": "private"}, {"acl": "public-read"})
    lines = describe(change)
    assert "acl: private → public-read" in lines[0]


def test_describe_truncates() -> None:
    before = {f"k{i}": 1 for i in range(20)}
    after = {f"k{i}": 2 for i in range(20)}
    change = change_of("aws_s3_bucket.a", ["update"], before, after)
    lines = describe(change, max_items=4)
    assert len(lines) == 5
    assert "16개" in lines[-1]


def test_describe_aggregates_many_unknowns() -> None:
    after = {"id": None, "arn": None, "address": None, "endpoint": None, "zone": None, "name": "x"}
    change = change_of(
        "aws_db_instance.main", ["delete", "create"], {"name": "x"}, after,
        after_unknown={k: True for k in ("id", "arn", "address", "endpoint", "zone")},
    )
    lines = describe(change)
    assert lines[0] == "- (재생성·생성이라 속성 5개는 적용 후에 정해집니다)"


def test_describe_create_shows_key_values() -> None:
    change = change_of("aws_instance.a", ["create"], None, {"ami": "ami-1", "instance_type": "t3.small"})
    lines = describe(change)
    assert "instance_type=t3.small" in lines[0]


def test_describe_delete_shows_prior_values() -> None:
    change = change_of("aws_instance.a", ["delete"], {"instance_type": "t3.small"}, None)
    assert "t3.small" in describe(change)[0]


def test_describe_noop() -> None:
    change = change_of("aws_s3_bucket.a", ["update"], {"a": 1}, {"a": 1})
    assert describe(change) == ["(속성 변화 없음)"]


def test_key_values_masks_sensitive() -> None:
    change = change_of(
        "aws_db_instance.a", ["create"], None, {"identifier": "db", "password": "x"},
        after_sensitive={"password": True},
    )
    pairs = dict(key_values(change, "after"))
    assert pairs["identifier"] == "db"
    assert pairs["password"] == MASK


def test_attr_diff_line_labels() -> None:
    assert AttrDiff("a", "added", None, 1).line() == "a = 1"
    assert "사라짐" in AttrDiff("a", "removed", 1, None).line()
    assert "적용 후 결정" in AttrDiff("a", "unknown").line()
