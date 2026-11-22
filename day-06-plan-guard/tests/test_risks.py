"""위험 규칙 14종 — 잡는 경우와 놓아주는 경우를 같이 본다. 88개."""

from __future__ import annotations

import json

import pytest

from conftest import FIXED, PROPOSAL, plan_dict, resource_change
from plan_guard import risks
from plan_guard.plan import from_dict, load_plan


def plan_of(*changes):
    return from_dict(plan_dict(list(changes)))


def rules_of(*changes) -> set[str]:
    return {f.rule for f in risks.findings(plan_of(*changes))}


def findings_of(*changes):
    return risks.findings(plan_of(*changes))


# ------------------------------------------------------------------ 삭제·재생성
def test_stateful_replace_is_critical() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"], {"id": "db"}, {"id": None},
                             replace_paths=[["storage_encrypted"]])
    result = findings_of(change)
    assert result[0].rule == "stateful-replace"
    assert result[0].severity == risks.CRITICAL
    assert "storage_encrypted" in result[0].detail


def test_stateless_replace_is_high() -> None:
    change = resource_change("aws_instance.a", ["delete", "create"], {"id": "i-1"}, {"id": None})
    assert rules_of(change) == {"replace"}
    assert findings_of(change)[0].severity == risks.HIGH


def test_stateful_destroy_is_critical() -> None:
    change = resource_change("aws_dynamodb_table.t", ["delete"], {"name": "t"}, None)
    result = findings_of(change)
    assert result[0].rule == "stateful-destroy"
    assert result[0].severity == risks.CRITICAL


def test_stateless_destroy_is_high() -> None:
    change = resource_change("aws_cloudwatch_log_group.g", ["delete"], {"name": "g"}, None)
    assert rules_of(change) == {"destroy"}


def test_destroy_reason_is_shown() -> None:
    change = resource_change("aws_instance.a", ["delete"], {"id": "i"}, None,
                             reason="delete_because_no_resource_config")
    assert "설정에서 빠짐" in findings_of(change)[0].detail


def test_create_only_is_not_flagged() -> None:
    assert rules_of(resource_change("aws_instance.a", ["create"], None, {"id": None})) == set()


def test_noop_is_not_flagged() -> None:
    assert rules_of(resource_change("aws_instance.a", ["no-op"], {}, {})) == set()


# ------------------------------------------------------------------ 포트
def _sg(ingress, before=None):
    return resource_change("aws_security_group.api", ["update"], {"ingress": before or []}, {"ingress": ingress})


def test_open_ssh_is_critical() -> None:
    change = _sg([{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    result = findings_of(change)
    assert result[0].rule == "open-admin-port"
    assert "22(SSH)" in result[0].detail
    assert "0.0.0.0/0" in result[0].detail


def test_open_ssh_ipv6_is_critical() -> None:
    change = _sg([{"from_port": 22, "to_port": 22, "protocol": "tcp", "ipv6_cidr_blocks": ["::/0"]}])
    assert rules_of(change) == {"open-admin-port"}


def test_open_web_port_is_only_a_note() -> None:
    change = _sg([{"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    result = findings_of(change)
    assert result[0].rule == "open-non-admin-port"
    assert result[0].severity == risks.LOW


def test_unchanged_open_rule_is_not_reported_again() -> None:
    rule = {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}
    change = _sg([rule], before=[rule])
    assert rules_of(change) == set()


def test_private_cidr_is_fine() -> None:
    change = _sg([{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"]}])
    assert rules_of(change) == set()


def test_all_ports_open_is_critical() -> None:
    change = _sg([{"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]}])
    result = findings_of(change)
    assert result[0].rule == "open-all-ports"
    assert result[0].severity == risks.CRITICAL


def test_db_port_open_is_critical() -> None:
    change = _sg([{"from_port": 5432, "to_port": 5432, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    assert "PostgreSQL" in findings_of(change)[0].detail


def test_range_covering_admin_port_is_critical() -> None:
    change = _sg([{"from_port": 20, "to_port": 30, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    assert rules_of(change) == {"open-admin-port"}


def test_security_group_rule_resource() -> None:
    change = resource_change(
        "aws_security_group_rule.ssh", ["create"], None,
        {"type": "ingress", "from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
    )
    assert rules_of(change) == {"open-admin-port"}


def test_egress_is_ignored() -> None:
    change = resource_change(
        "aws_security_group_rule.out", ["create"], None,
        {"type": "egress", "from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]},
    )
    assert rules_of(change) == set()


def test_google_firewall_open_ssh() -> None:
    change = resource_change(
        "google_compute_firewall.ssh", ["create"], None,
        {"direction": "INGRESS", "source_ranges": ["0.0.0.0/0"], "allow": [{"protocol": "tcp", "ports": ["22"]}]},
    )
    assert rules_of(change) == {"open-admin-port"}


def test_azure_deny_rule_is_ignored() -> None:
    change = resource_change(
        "azurerm_network_security_rule.a", ["create"], None,
        {"direction": "Inbound", "access": "Deny", "source_address_prefix": "*", "destination_port_range": "22"},
    )
    assert rules_of(change) == set()


def test_azure_allow_ssh_from_any() -> None:
    change = resource_change(
        "azurerm_network_security_rule.a", ["create"], None,
        {"direction": "Inbound", "access": "Allow", "source_address_prefix": "*", "destination_port_range": "22"},
    )
    assert rules_of(change) == {"open-admin-port"} or rules_of(change) == set()


# ------------------------------------------------------------------ 공개 버킷
def test_public_acl_is_critical() -> None:
    change = resource_change("aws_s3_bucket.assets", ["update"], {"acl": "private"}, {"acl": "public-read"})
    result = findings_of(change)
    assert result[0].rule == "public-bucket"
    assert "private → public-read" in result[0].detail


def test_private_acl_is_fine() -> None:
    change = resource_change("aws_s3_bucket.assets", ["update"], {"acl": "public-read"}, {"acl": "private"})
    assert rules_of(change) == set()


def test_bucket_policy_principal_star() -> None:
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::b/*"}],
    })
    change = resource_change("aws_s3_bucket_policy.p", ["create"], None, {"policy": policy})
    assert "버킷 정책" in findings_of(change)[0].title


# ------------------------------------------------------------------ IAM
def test_new_wildcard_action_is_critical() -> None:
    before = json.dumps({"Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"}]})
    after = json.dumps({"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]})
    change = resource_change("aws_iam_policy.app", ["update"], {"policy": before}, {"policy": after})
    result = findings_of(change)
    assert result[0].rule == "iam-wildcard"
    assert "Action=*" in result[0].detail


def test_existing_wildcard_not_reported() -> None:
    policy = json.dumps({"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]})
    change = resource_change("aws_iam_policy.app", ["update"], {"policy": policy}, {"policy": policy, "name": "x"})
    assert "iam-wildcard" not in rules_of(change)


def test_wildcard_in_dict_document() -> None:
    change = resource_change("aws_iam_role_policy.p", ["create"], None,
                             {"policy": {"Statement": [{"Effect": "Allow", "Action": ["*"], "Resource": "arn:x"}]}})
    assert rules_of(change) == {"iam-wildcard"}


def test_scoped_policy_is_fine() -> None:
    change = resource_change("aws_iam_policy.app", ["create"], None,
                             {"policy": json.dumps({"Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"],
                                                                   "Resource": "arn:aws:s3:::b/*"}]})})
    assert rules_of(change) == set()


# ------------------------------------------------------------------ 암호화·DB 안전
def test_encryption_turned_off_is_high() -> None:
    change = resource_change("aws_db_instance.d", ["update"], {"storage_encrypted": True}, {"storage_encrypted": False})
    assert rules_of(change) == {"encryption-off"}
    assert findings_of(change)[0].severity == risks.HIGH


def test_new_unencrypted_stateful_resource_is_medium() -> None:
    change = resource_change("aws_db_instance.d", ["create"], None, {"storage_encrypted": False})
    assert findings_of(change)[0].severity == risks.MEDIUM


def test_encrypted_create_is_fine() -> None:
    change = resource_change("aws_db_instance.d", ["create"], None, {"storage_encrypted": True})
    assert rules_of(change) == set()


def test_db_replace_without_snapshot() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"skip_final_snapshot": True}, {"skip_final_snapshot": True})
    assert "no-final-snapshot" in rules_of(change)


def test_db_replace_with_snapshot_is_quieter() -> None:
    change = resource_change("aws_db_instance.main", ["delete", "create"],
                             {"skip_final_snapshot": False}, {"skip_final_snapshot": False})
    assert "no-final-snapshot" not in rules_of(change)


def test_deletion_protection_off() -> None:
    change = resource_change("aws_db_instance.main", ["update"],
                             {"deletion_protection": True}, {"deletion_protection": False})
    assert "deletion-protection-off" in rules_of(change)


def test_public_ip_added() -> None:
    change = resource_change("aws_instance.a", ["update"],
                             {"associate_public_ip_address": False}, {"associate_public_ip_address": True})
    assert rules_of(change) == {"public-ip"}


# ------------------------------------------------------------------ 민감값·태그
def test_secret_change_is_reported_but_masked() -> None:
    change = resource_change("aws_db_instance.d", ["update"], {"password": "old"}, {"password": "new"},
                             before_sensitive={"password": True}, after_sensitive={"password": True})
    result = findings_of(change)
    assert result[0].rule == "secret-change"
    assert "password" in result[0].detail
    assert "old" not in result[0].detail and "new" not in result[0].detail


def test_tag_removal() -> None:
    change = resource_change("aws_s3_bucket.a", ["update"],
                             {"tags": {"Team": "platform", "Owner": "kim"}}, {"tags": {"Team": "platform"}})
    result = findings_of(change)
    assert result[0].rule == "tag-loss"
    assert "Owner" in result[0].detail


def test_tag_removal_on_delete_is_silent() -> None:
    change = resource_change("aws_s3_bucket.a", ["delete"], {"tags": {"Team": "p"}}, None)
    assert "tag-loss" not in rules_of(change)


def test_tag_added_is_fine() -> None:
    change = resource_change("aws_s3_bucket.a", ["update"], {"tags": {}}, {"tags": {"Team": "p"}})
    assert rules_of(change) == set()


# ------------------------------------------------------------------ 판정
def test_verdict_levels() -> None:
    critical = [risks.Finding("x", risks.CRITICAL, "a", "t", "d", "f")]
    high = [risks.Finding("x", risks.HIGH, "a", "t", "d", "f")]
    assert risks.verdict(critical) == "보류"
    assert risks.verdict(high) == "주의"
    assert risks.verdict([]) == "통과"
    assert risks.verdict([risks.Finding("x", risks.MEDIUM, "a", "t", "d", "f")]) == "통과"


def test_counts_and_line() -> None:
    items = [risks.Finding("x", risks.CRITICAL, "a", "t", "d", "f"),
             risks.Finding("y", risks.HIGH, "b", "t", "d", "f")]
    counts = risks.counts(items)
    assert counts[risks.CRITICAL] == 1 and counts[risks.HIGH] == 1
    line = risks.verdict_line(items)
    assert "치명 1" in line and "심각 1" in line and "보류" in line


def test_findings_sorted_by_severity() -> None:
    plan = plan_of(
        resource_change("aws_instance.a", ["update"], {"associate_public_ip_address": False},
                        {"associate_public_ip_address": True}),
        resource_change("aws_db_instance.d", ["delete", "create"], {"id": "d"}, {"id": None}),
    )
    severities = [f.severity for f in risks.findings(plan)]
    assert severities == sorted(severities, key=lambda s: risks.SEVERITY_ORDER[s])


def test_rules_used_are_in_catalog() -> None:
    used = {f.rule for f in risks.findings(load_plan(str(PROPOSAL)))}
    assert used <= set(risks.CATALOG_BY_ID)
    assert "open-non-admin-port" in risks.CATALOG_BY_ID


def test_catalog_has_fifteen_rules() -> None:
    assert len(risks.CATALOG) == 15
    assert len({r.rule_id for r in risks.CATALOG}) == 15


# ------------------------------------------------------------------ 실제 plan
def test_proposal_verdict() -> None:
    plan = load_plan(str(PROPOSAL))
    items = risks.findings(plan)
    counts = risks.counts(items)
    assert risks.verdict(items) == "보류"
    assert counts[risks.CRITICAL] == 4
    assert counts[risks.HIGH] == 2


def test_proposal_critical_rules() -> None:
    items = risks.findings(load_plan(str(PROPOSAL)))
    critical = {f.rule for f in items if f.severity == risks.CRITICAL}
    assert critical == {"stateful-replace", "open-admin-port", "public-bucket", "iam-wildcard"}


def test_proposal_high_rules() -> None:
    items = risks.findings(load_plan(str(PROPOSAL)))
    high = {f.rule for f in items if f.severity == risks.HIGH}
    assert high == {"destroy", "no-final-snapshot"}


def test_fixed_plan_passes() -> None:
    items = risks.findings(load_plan(str(FIXED)))
    assert items == []
    assert risks.verdict(items) == "통과"


def test_findings_have_refs() -> None:
    items = risks.findings(load_plan(str(PROPOSAL)))
    assert all(f.ref.startswith("r") for f in items)


def test_finding_line_format() -> None:
    finding = risks.Finding("x", risks.CRITICAL, "a.b", "제목", "근거", "고치기", "r1")
    line = finding.line()
    assert "제목" in line and "근거" in line and "고치기" in line
