"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from mcp.client.client import Client

from conftest import AFTER, BEFORE, FORMATS, MESSY
from log_triage.server import mcp

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "read_logs",
    "signature_report",
    "rate_report",
    "compare_logs",
    "stack_report",
    "timeline",
    "find_text",
    "redact_secrets",
    "rule_catalog",
    "find_problems",
    "overview",
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


def _read(path) -> tuple[str, str]:
    out = _call("read_logs", {"path": str(path)})
    match = re.search(r"ref (lg-\d+)", out)
    assert match, out
    return match.group(1), out


def test_lists_all_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_read_logs() -> None:
    out = _call("read_logs", {"path": str(BEFORE)})
    assert "api-before.log" in out
    assert "레벨:" in out
    assert "판정하지 않음" in out


def test_read_logs_missing_file() -> None:
    out = _call("read_logs", {"path": str(ROOT / "없는파일.log")})
    assert out.startswith("⚠️")


def test_read_logs_directory(tmp_path) -> None:
    out = _call("read_logs", {"path": str(tmp_path)})
    assert out.startswith("⚠️")


def test_signature_report() -> None:
    ref, _ = _read(AFTER)
    out = _call("signature_report", {"ref": ref, "limit": 5})
    assert "서명" in out
    assert "PoolTimeoutError" in out


def test_unknown_ref_is_friendly() -> None:
    out = _call("signature_report", {"ref": "lg-9999"})
    assert "찾을 수 없습니다" in out
    assert "read_logs" in out


def test_rate_report() -> None:
    ref, _ = _read(AFTER)
    out = _call("rate_report", {"ref": ref, "bucket_seconds": 60})
    assert "구간" in out


def test_compare_logs() -> None:
    before_ref, _ = _read(BEFORE)
    after_ref, _ = _read(AFTER)
    out = _call("compare_logs", {"ref_before": before_ref, "ref_after": after_ref})
    assert "새로 생김" in out
    assert "ERROR/CRITICAL" in out


def test_stack_report() -> None:
    ref, _ = _read(AFTER)
    out = _call("stack_report", {"ref": ref})
    assert "pool.py:64" in out


def test_timeline() -> None:
    ref, _ = _read(AFTER)
    out = _call("timeline", {"ref": ref})
    assert "첫 오류" in out


def test_timeline_with_baseline() -> None:
    before_ref, _ = _read(BEFORE)
    after_ref, _ = _read(AFTER)
    out = _call("timeline", {"ref": after_ref, "baseline_ref": before_ref})
    assert "기준선" in out


def test_find_text() -> None:
    ref, _ = _read(BEFORE)
    out = _call("find_text", {"ref": ref, "pattern": "ConnectionReset", "context": 1})
    assert "일치" in out


def test_find_text_regex_error() -> None:
    ref, _ = _read(BEFORE)
    out = _call("find_text", {"ref": ref, "pattern": "([", "regex": True})
    assert out.startswith("⚠️")


def test_redact_secrets_preview() -> None:
    ref, _ = _read(MESSY)
    out = _call("redact_secrets", {"ref": ref, "preview": 3})
    assert "지운 값" in out
    assert "0 확인" in out
    assert "hunter2" not in out


def test_redact_secrets_writes_file(tmp_path) -> None:
    ref, _ = _read(MESSY)
    target = tmp_path / "masked.log"
    out = _call("redact_secrets", {"ref": ref, "out": str(target)})
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "저장" in out


def test_find_problems() -> None:
    ref, _ = _read(MESSY)
    out = _call("find_problems", {"ref": ref})
    assert "비밀번호·토큰" in out
    assert "고치는 순서" in out


def test_find_problems_clean_file() -> None:
    ref, _ = _read(BEFORE)
    out = _call("find_problems", {"ref": ref})
    assert "규칙 위반" in out or "걸리는 것 없음" in out


def test_rule_catalog() -> None:
    out = _call("rule_catalog", {})
    assert "규칙 25종" in out


def test_rule_catalog_one() -> None:
    out = _call("rule_catalog", {"rule": "retry-storm"})
    assert "왜:" in out


def test_rule_catalog_unknown() -> None:
    out = _call("rule_catalog", {"rule": "없는규칙"})
    assert out.startswith("⚠️")


def test_overview() -> None:
    out = _call("overview", {})
    assert "log-triage" in out
    assert "판정하지 않는 것" in out


def test_max_tokens_truncates() -> None:
    ref, _ = _read(AFTER)
    out = _call("signature_report", {"ref": ref, "max_tokens": 20})
    assert "토큰에서 잘랐습니다" in out


def test_reading_formats_file() -> None:
    out = _call("read_logs", {"path": str(FORMATS)})
    assert "json" in out


def test_stdio_transport() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "log_triage.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                read_result = await session.call_tool("read_logs", {"path": str(BEFORE)})
                ref = re.search(r"ref (lg-\d+)", _text(read_result)).group(1)
                problems = await session.call_tool("find_problems", {"ref": ref})
                return ({tool.name for tool in listed.tools}, _text(read_result), _text(problems))

    names, read_out, problems = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "api-before.log" in read_out
    assert "규칙" in problems


def test_stdio_root_env(tmp_path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    (tmp_path / "app.log").write_text(
        "2026-11-25 09:00:01 INFO hello\n", encoding="utf-8")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "log_triage.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT), "LOG_TRIAGE_ROOT": str(tmp_path)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("read_logs", {"path": "app.log"})
                return _text(result)

    assert "app.log" in _run(scenario())
