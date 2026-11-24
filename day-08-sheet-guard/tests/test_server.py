"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from mcp.client.client import Client

from sheet_guard.server import mcp

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "examples" / "raw_population.csv"
XLSX = ROOT / "examples" / "merged_population.xlsx"

EXPECTED_TOOLS = {
    "read_table",
    "profile_columns",
    "find_problems",
    "clean_plan",
    "apply_plan",
    "to_markdown",
    "compare_tables",
    "rule_catalog",
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


def test_lists_nine_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def _read(path) -> tuple[str, str]:
    out = _call("read_table", {"path": str(path)})
    match = re.search(r"ref (t\d+)", out)
    assert match, out
    return match.group(1), out


def test_read_table() -> None:
    out = _call("read_table", {"path": str(RAW)})
    assert "CP949" in out
    assert "ref t" in out
    assert "우편번호" in out


def test_read_table_missing_file() -> None:
    out = _call("read_table", {"path": str(ROOT / "없는파일.csv")})
    assert out.startswith("⚠️")


def test_read_table_xlsx() -> None:
    out = _call("read_table", {"path": str(XLSX)})
    assert "[인구]" in out
    assert "병합" in out


def test_profile_columns() -> None:
    ref, _ = _read(RAW)
    out = _call("profile_columns", {"ref": ref})
    assert "우편번호" in out
    assert "채움" in out


def test_unknown_ref_is_friendly() -> None:
    out = _call("profile_columns", {"ref": "t999"})
    assert "찾을 수 없습니다" in out


def test_find_problems() -> None:
    ref, _ = _read(RAW)
    out = _call("find_problems", {"ref": ref})
    assert "subtotal-row" in out
    assert "판정하지 않고" in out       # 한계 문구가 항상 붙는다


def test_find_problems_severity() -> None:
    ref, _ = _read(RAW)
    out = _call("find_problems", {"ref": ref, "severity": "error"})
    assert "subtotal-row" in out
    assert "thousands-separator" not in out


def test_clean_plan() -> None:
    ref, _ = _read(RAW)
    out = _call("clean_plan", {"ref": ref})
    assert "정리 계획" in out
    assert "확신" in out


def test_apply_plan_writes_files(tmp_path) -> None:
    ref, _ = _read(RAW)
    out_path = tmp_path / "clean.csv"
    out = _call("apply_plan", {"ref": ref, "out": str(out_path)})
    assert out_path.exists()
    assert "적용 완료" in out
    assert "정리본 ref" in out


def test_apply_plan_only(tmp_path) -> None:
    ref, _ = _read(RAW)
    out_path = tmp_path / "sub.csv"
    _call("apply_plan", {"ref": ref, "out": str(out_path), "only": "subtotal-row"})
    text = out_path.read_text(encoding="utf-8-sig")
    assert "소계" not in text


def test_to_markdown_tool() -> None:
    ref, _ = _read(RAW)
    out = _call("to_markdown", {"ref": ref, "max_rows": 3})
    assert "| 시도 |" in out


def test_to_markdown_clean() -> None:
    ref, _ = _read(RAW)
    out = _call("to_markdown", {"ref": ref, "clean": True, "max_rows": 3})
    assert "면적_단위" in out


def test_compare_tables(tmp_path) -> None:
    ref, _ = _read(RAW)
    out_path = tmp_path / "clean.csv"
    out = _call("apply_plan", {"ref": ref, "out": str(out_path)})
    clean_ref = out.split("정리본 ref: ")[1].split(" ")[0]
    diff = _call("compare_tables", {"ref_a": ref, "ref_b": clean_ref})
    assert "정리 전" in diff
    assert "사라진 칸" not in diff


def test_rule_catalog() -> None:
    out = _call("rule_catalog", {})
    assert "규칙" in out
    assert "duplicate-rows" in out


def test_rule_catalog_one() -> None:
    out = _call("rule_catalog", {"rule": "leading-zero-risk"})
    assert "왜:" in out


def test_rule_catalog_unknown() -> None:
    out = _call("rule_catalog", {"rule": "없는규칙"})
    assert out.startswith("⚠️")


def test_overview() -> None:
    out = _call("overview", {})
    assert "sheet-guard" in out
    assert "판정하지 않는" in out


def test_max_tokens_truncates() -> None:
    ref, _ = _read(RAW)
    out = _call("profile_columns", {"ref": ref, "max_tokens": 20})
    assert "토큰에서 잘랐습니다" in out


def test_stdio_transport(tmp_path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sheet_guard.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool("find_problems", {"path": str(RAW), "ref": ""})
                read_result = await session.call_tool("read_table", {"path": str(RAW)})
                return ({tool.name for tool in listed.tools}, _text(result), _text(read_result))

    names, problems, read_out = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "치명" in problems or "⚠️" in problems
    assert "CP949" in read_out
