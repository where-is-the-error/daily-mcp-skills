"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp.client.client import Client

from plan_guard.server import mcp

ROOT = Path(__file__).resolve().parent.parent
PROPOSAL = ROOT / "examples" / "proposal-plan.json"
FIXED = ROOT / "examples" / "fixed-plan.json"

EXPECTED_TOOLS = {
    "read_plan",
    "list_changes",
    "diff_resource",
    "risk_report",
    "apply_order",
    "rollback_plan",
    "compare_plans",
    "redact_plan",
    "rule_catalog",
}


def _text(result) -> str:
    chunks = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _run(coro):
    return asyncio.run(coro)


def _call(name: str, arguments: dict) -> str:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool(name, arguments))

    return _run(scenario())


def test_lists_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_read_plan_summary() -> None:
    out = _call("read_plan", {"source": str(PROPOSAL)})
    assert "바뀌는 리소스" in out
    assert "보류" in out


def test_list_changes_with_filter() -> None:
    out = _call("list_changes", {"source": str(PROPOSAL), "kind": "delete"})
    assert "aws_instance.worker" in out
    assert "aws_db_instance.main" not in out


def test_diff_resource() -> None:
    out = _call("diff_resource", {"source": str(PROPOSAL), "address": "aws_security_group.api"})
    assert "ingress[tcp/22-22]" in out


def test_diff_resource_missing() -> None:
    out = _call("diff_resource", {"source": str(PROPOSAL), "address": "aws_nope.x"})
    assert "찾지 못했습니다" in out


def test_risk_report() -> None:
    out = _call("risk_report", {"source": str(PROPOSAL)})
    assert "치명 4" in out
    assert "IAM" in out


def test_risk_report_severity() -> None:
    out = _call("risk_report", {"source": str(PROPOSAL), "severity": "참고"})
    assert "보류" in out


def test_apply_order() -> None:
    out = _call("apply_order", {"source": str(PROPOSAL)})
    assert "쓰는 순서" in out


def test_rollback_plan() -> None:
    out = _call("rollback_plan", {"source": str(PROPOSAL)})
    assert "state pull" in out


def test_compare_plans() -> None:
    out = _call("compare_plans", {"before": str(PROPOSAL), "after": str(FIXED)})
    assert "치명 4 → 0" in out


def test_redact_plan_hides_secret() -> None:
    out = _call("redact_plan", {"source": str(PROPOSAL), "max_tokens": 100000})
    assert "correcthorsebatterystaple" not in out
    assert "«민감»" in out


def test_rule_catalog() -> None:
    out = _call("rule_catalog", {})
    assert "판정하지 않는 것" in out
    assert "stateful-replace" in out


def test_bad_source_returns_warning() -> None:
    out = _call("read_plan", {"source": "/nope/plan.json"})
    assert out.startswith("⚠️")


def test_bad_json_returns_warning() -> None:
    out = _call("read_plan", {"source": "{oops"})
    assert out.startswith("⚠️")


def test_token_budget_truncates() -> None:
    out = _call("list_changes", {"source": str(PROPOSAL), "max_tokens": 12})
    assert "잘랐습니다" in out


def test_root_env(tmp_path, monkeypatch) -> None:
    from conftest import write_plan, resource_change

    write_plan(tmp_path, [resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})])
    monkeypatch.setenv("PLAN_GUARD_ROOT", str(tmp_path))
    out = _call("read_plan", {"source": "plan.json"})
    assert "생성 1" in out


def test_stdio_transport() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "plan_guard.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool("risk_report", {"source": str(PROPOSAL)})
                return {tool.name for tool in listed.tools}, _text(result)

    names, output = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "치명 4" in output
