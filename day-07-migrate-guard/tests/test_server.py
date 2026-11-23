"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp.client.client import Client

from migrate_guard.server import mcp

ROOT = Path(__file__).resolve().parent.parent
RISKY = ROOT / "examples" / "0012_add_email_verified.up.sql"
FIXED = ROOT / "examples" / "0012_add_email_verified.fixed.up.sql"
SCHEMA = ROOT / "examples" / "schema.sql"
STATS = ROOT / "examples" / "stats.json"

EXPECTED_TOOLS = {
    "read_migration",
    "list_statements",
    "lock_report",
    "risk_report",
    "rollout_plan",
    "rollback_plan",
    "schema_change",
    "compare_migrations",
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


def base() -> dict:
    return {"baseline": str(SCHEMA), "rows": str(STATS)}


def test_lists_nine_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_read_migration() -> None:
    out = _call("read_migration", {"source": str(RISKY), **base()})
    assert "판정 **보류**" in out
    assert "최대 잠금 12분" in out


def test_read_migration_without_rows_says_assumed() -> None:
    out = _call("read_migration", {"source": str(RISKY), "baseline": str(SCHEMA)})
    assert "가정" in out


def test_list_statements() -> None:
    out = _call("list_statements", {"source": str(RISKY), **base()})
    assert "s3 · 줄 6 · alter_type" in out


def test_lock_report() -> None:
    out = _call("lock_report", {"source": str(RISKY), **base()})
    assert "ACCESS EXCLUSIVE" in out
    assert "모델" in out


def test_risk_report() -> None:
    out = _call("risk_report", {"source": str(RISKY), **base()})
    assert "치명" in out
    assert "고치기" in out


def test_risk_report_severity() -> None:
    out = _call("risk_report", {"source": str(RISKY), "severity": "치명", **base()})
    assert "심각 ·" not in out


def test_rollout_plan() -> None:
    out = _call("rollout_plan", {"source": str(RISKY), **base()})
    assert "1단계" in out
    assert "CREATE INDEX CONCURRENTLY" in out


def test_rollback_plan() -> None:
    out = _call("rollback_plan", {"source": str(RISKY), "baseline": str(SCHEMA)})
    assert "되돌리기 SQL" in out


def test_schema_change() -> None:
    out = _call("schema_change", {"source": str(RISKY), "baseline": str(SCHEMA)})
    assert "사라지는 컬럼: sessions.legacy_token" in out


def test_compare_migrations() -> None:
    out = _call("compare_migrations", {"before": str(RISKY), "after": str(FIXED), **base()})
    assert "치명: 3 → 0" in out


def test_rule_catalog() -> None:
    out = _call("rule_catalog", {})
    assert "판정하지 않는 것" in out
    assert "drop-table" in out


def test_missing_file_warns() -> None:
    out = _call("read_migration", {"source": "/nope/0012.sql"})
    assert out.startswith("⚠️")


def test_bad_rows_json_warns() -> None:
    out = _call("read_migration", {"source": str(RISKY), "rows": "{oops"})
    assert out.startswith("⚠️")


def test_token_budget_truncates() -> None:
    out = _call("list_statements", {"source": str(RISKY), "max_tokens": 10})
    assert "잘랐습니다" in out


def test_root_env(tmp_path, monkeypatch) -> None:
    (tmp_path / "0013.sql").write_text("CREATE INDEX idx ON users (phone);", encoding="utf-8")
    (tmp_path / "schema.sql").write_text(SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("MIGRATE_GUARD_ROOT", str(tmp_path))
    out = _call("read_migration", {"source": "0013.sql", "baseline": "schema.sql", "rows": '{"users": 1000}'})
    assert "주의" in out


def test_stdio_transport() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "migrate_guard.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool(
                    "risk_report", {"source": str(RISKY), "baseline": str(SCHEMA), "rows": str(STATS)}
                )
                return {tool.name for tool in listed.tools}, _text(result)

    names, output = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "치명" in output
