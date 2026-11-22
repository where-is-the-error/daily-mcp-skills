"""되돌리기 계획 — 18개."""

from __future__ import annotations

import pytest

from conftest import FIXED, PROPOSAL, plan_dict, resource_change
from plan_guard import rollback
from plan_guard.plan import MASK, from_dict, load_plan


def plan_of(*changes):
    return from_dict(plan_dict(list(changes)))


def text_of(*changes) -> str:
    return "\n".join(rollback.steps(plan_of(*changes)))


def test_describes_state_backup_first() -> None:
    text = text_of(resource_change("aws_instance.a", ["create"], None, {"id": None}))
    assert "terraform state pull" in text
    assert "apply 전에" in text


def test_no_destructive_says_nothing_to_revert() -> None:
    text = text_of(resource_change("aws_instance.a", ["create"], None, {"id": None}))
    assert "되돌릴 것이 없습니다" in text


def test_db_replace_gets_snapshot_command() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"identifier": "acme-prod-db", "skip_final_snapshot": True},
                             {"identifier": "acme-prod-db"})
    text = text_of(change)
    assert "aws rds create-db-snapshot" in text
    assert "--db-instance-identifier acme-prod-db" in text


def test_instance_gets_ami_hint() -> None:
    change = resource_change("aws_instance.worker", ["delete"], {"id": "i-123"}, None)
    assert "aws ec2 create-image --instance-id i-123" in text_of(change)


def test_bucket_gets_copy_hint() -> None:
    change = resource_change("aws_s3_bucket.assets", ["delete"], {"bucket": "acme-prod-assets"}, None)
    assert "s3://acme-prod-assets" in text_of(change)


def test_unknown_type_gets_generic_hint() -> None:
    change = resource_change("aws_cloudwatch_log_group.g", ["delete"], {"name": "g"}, None)
    assert "provider CLI" in text_of(change)


def test_prior_values_listed() -> None:
    change = resource_change("aws_instance.worker", ["delete"],
                             {"instance_type": "t3.small", "ami": "ami-1"}, None)
    assert "이전 값" in text_of(change)
    assert "t3.small" in text_of(change)


def test_revert_lines_for_changed_attribute() -> None:
    change = resource_change("aws_db_instance.main", ["update"],
                             {"storage_encrypted": True}, {"storage_encrypted": False})
    # 삭제가 아니면 되돌리기 대상이 아니다
    assert "되돌릴 것이 없습니다" in text_of(change)


def test_revert_lines_for_replace() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"identifier": "db", "storage_encrypted": False},
                             {"identifier": "db", "storage_encrypted": True})
    text = text_of(change)
    assert "storage_encrypted = false" in text


def test_removed_attribute_is_not_a_revert_line() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"identifier": "db", "multi_az": False}, {"identifier": "db"})
    assert "multi_az" not in text_of(change).split("### 3")[1]


def test_sensitive_value_masked_in_rollback() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"identifier": "db", "password": "hunter2"},
                             {"identifier": "db", "password": "new"},
                             before_sensitive={"password": True}, after_sensitive={"password": True})
    text = text_of(change)
    assert "hunter2" not in text


def test_identifier_falls_back_to_address() -> None:
    change = resource_change("aws_instance.worker", ["delete"], {"id": "arn:aws:ec2:..."}, None)
    assert "aws_instance.worker" in text_of(change)


def test_summary_line_with_stateful() -> None:
    plan = plan_of(resource_change("aws_db_instance.main", ["delete", "create"], {"identifier": "db"}, {"identifier": "db"}))
    line = rollback.summary_line(plan)
    assert "2개" in line or "1개" in line
    assert "데이터 1개" in line


def test_summary_line_empty() -> None:
    plan = plan_of(resource_change("aws_instance.a", ["create"], None, {"id": None}))
    assert "되돌릴 것 없음" in rollback.summary_line(plan)


def test_example_rollback_mentions_snapshot_and_ami() -> None:
    text = "\n".join(rollback.steps(load_plan(str(PROPOSAL))))
    assert "create-db-snapshot" in text
    assert "create-image" in text


def test_fixed_plan_has_nothing_to_back_up() -> None:
    text = "\n".join(rollback.steps(load_plan(str(FIXED))))
    assert "되돌릴 것이 없습니다" in text


def test_disclaimer_present() -> None:
    change = resource_change("aws_db_instance.main", ["delete"], {"identifier": "db"}, None)
    assert "제안입니다" in text_of(change)


def test_deterministic_output() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"], {"identifier": "db"}, {"identifier": "db"})
    assert text_of(change) == text_of(change)
