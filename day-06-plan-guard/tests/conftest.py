"""테스트 도우미 — plan JSON 을 손으로 만들 때 쓰는 최소 빌더."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
PROPOSAL = EXAMPLES / "proposal-plan.json"
FIXED = EXAMPLES / "fixed-plan.json"


def resource_change(
    address: str,
    actions: list[str],
    before: dict | None = None,
    after: dict | None = None,
    *,
    before_sensitive: Any = None,
    after_sensitive: Any = None,
    after_unknown: Any = None,
    reason: str | None = None,
    replace_paths: list[list[str]] | None = None,
    provider: str = "registry.terraform.io/hashicorp/aws",
) -> dict:
    rtype, _, name = address.rpartition(".")
    return {
        "address": address,
        "mode": "managed",
        "type": rtype,
        "name": name,
        "provider_name": provider,
        "change": {
            "actions": actions,
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(after),
            "before_sensitive": copy.deepcopy(before_sensitive),
            "after_sensitive": copy.deepcopy(after_sensitive),
            "after_unknown": copy.deepcopy(after_unknown),
            "action_reason": reason,
            "replace_paths": replace_paths,
        },
    }


def plan_dict(changes: list[dict], configuration: dict | None = None, **extra) -> dict:
    data = {
        "format_version": "1.2",
        "terraform_version": "1.9.8",
        "timestamp": "2026-11-22T00:00:00Z",
        "applyable": True,
        "complete": True,
        "errored": False,
        "resource_changes": changes,
        "configuration": configuration or {"root_module": {"resources": []}},
    }
    data.update(extra)
    return data


def plan_json(changes: list[dict], **extra) -> str:
    return json.dumps(plan_dict(changes, **extra), ensure_ascii=False)


def write_plan(tmp_path: Path, changes: list[dict], name: str = "plan.json", **extra) -> Path:
    path = tmp_path / name
    path.write_text(plan_json(changes, **extra), encoding="utf-8")
    return path


@pytest.fixture()
def sg_update() -> dict:
    """22번 포트 출처가 10.0.0.0/8 → 0.0.0.0/0 으로 바뀌는 보안 그룹."""
    before = {
        "id": "sg-1",
        "name": "api",
        "ingress": [
            {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"]},
            {"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"]},
        ],
        "tags": {"Name": "api"},
    }
    after = copy.deepcopy(before)
    after["ingress"][0]["cidr_blocks"] = ["0.0.0.0/0"]
    return resource_change("aws_security_group.api", ["update"], before, after)


@pytest.fixture()
def db_replace() -> dict:
    before = {
        "id": "acme-prod-db",
        "identifier": "acme-prod-db",
        "engine": "postgres",
        "storage_encrypted": False,
        "skip_final_snapshot": True,
        "password": "hunter2",
        "tags": {"Team": "platform"},
    }
    after = copy.deepcopy(before)
    after.update({"id": None, "storage_encrypted": True, "password": None})
    return resource_change(
        "aws_db_instance.main",
        ["delete", "create"],
        before,
        after,
        before_sensitive={"password": True},
        after_sensitive={"password": True},
        after_unknown={"id": True},
        replace_paths=[["storage_encrypted"]],
    )
