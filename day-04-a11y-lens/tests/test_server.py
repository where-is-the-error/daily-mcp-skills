"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client.client import Client

from a11y_lens.server import mcp

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOOLS = {
    "snapshot_page",
    "find_in_snapshot",
    "audit_page",
    "audit_site",
    "fix_plan",
    "verify_fixes",
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


@pytest.fixture
def page_file(tmp_path) -> Path:
    path = tmp_path / "index.html"
    path.write_text(
        """<!doctype html><html lang="ko"><head><title>홈</title></head>
<body><main><h1>홈</h1><img src="a.png"><button></button></main></body></html>""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def fixed_file(tmp_path) -> Path:
    path = tmp_path / "fixed.html"
    path.write_text(
        """<!doctype html><html lang="ko"><head><title>홈</title></head>
<body><main><h1>홈</h1><img src="a.png" alt="로고"><button>저장</button></main></body></html>""",
        encoding="utf-8",
    )
    return path


def test_lists_seven_tools(lens_home) -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_snapshot_tool(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("snapshot_page", {"source": str(page_file)}))

    text = _run(scenario())
    assert 'document "홈" lang=ko' in text
    assert "ref=e" in text
    assert "heading" in text


def test_snapshot_tool_with_depth(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("snapshot_page", {"source": str(page_file), "depth": 1}))

    text = _run(scenario())
    assert "main" in text
    assert "heading" not in text


def test_snapshot_tool_inline_html() -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("snapshot_page", {"source": "<body><main><h1>메모</h1></main></body>"})
            )

    assert 'heading "메모"' in _run(scenario())


def test_find_in_snapshot(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("find_in_snapshot", {"source": str(page_file), "text": "홈"}))

    text = _run(scenario())
    assert "ref=e" in text
    assert "경로:" in text


def test_find_in_snapshot_regex(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("find_in_snapshot", {"source": str(page_file), "regex": "head"})
            )

    assert "heading" in _run(scenario())


def test_find_in_snapshot_requires_a_needle(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("find_in_snapshot", {"source": str(page_file)}))

    assert "⚠️" in _run(scenario())


def test_find_in_snapshot_bad_regex(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("find_in_snapshot", {"source": str(page_file), "regex": "["})
            )

    assert "⚠️" in _run(scenario())


def test_find_in_snapshot_no_match(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("find_in_snapshot", {"source": str(page_file), "text": "없는말"})
            )

    assert "없습니다" in _run(scenario())


def test_audit_page_markdown(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_page", {"source": str(page_file)}))

    text = _run(scenario())
    assert "점수" in text
    assert "image-alt" in text


def test_audit_page_json(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_page", {"source": str(page_file), "format": "json"}))

    data = json.loads(_run(scenario()))
    assert data["path"].endswith("index.html")
    assert {v["rule"] for v in data["violations"]} >= {"image-alt", "button-name"}


def test_audit_page_rule_filter(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("audit_page", {"source": str(page_file), "rules": "image-alt", "format": "json"})
            )

    data = json.loads(_run(scenario()))
    assert {v["rule"] for v in data["violations"]} == {"image-alt"}


def test_audit_page_missing_file() -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_page", {"source": "없는파일.html"}))

    assert "⚠️" in _run(scenario())


def test_audit_site_tool(site) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_site", {"directory": str(site)}))

    text = _run(scenario())
    assert "페이지 **3쪽**" in text
    assert "| 위반 패턴 |" in text


def test_audit_site_with_root_env(site, monkeypatch) -> None:
    monkeypatch.setenv("A11Y_LENS_ROOT", str(site))

    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_site", {"directory": "sub"}))

    assert "deep.html" in _run(scenario())


def test_audit_site_bad_directory() -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("audit_site", {"directory": "없는폴더"}))

    assert "⚠️" in _run(scenario())


def test_fix_plan_tool(page_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("fix_plan", {"source": str(page_file)}))

    text = _run(scenario())
    assert "고치기 순서" in text
    assert "바꿀 모양" in text


def test_fix_plan_clean_page(fixed_file) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("fix_plan", {"source": str(fixed_file)}))

    assert "✅" in _run(scenario())


def test_verify_save_then_check(page_file, fixed_file, lens_home) -> None:
    async def save():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("verify_fixes", {"source": str(page_file), "baseline": "demo", "mode": "save"})
            )

    async def check():
        async with Client(mcp) as client:
            return _text(await client.call_tool("verify_fixes", {"source": str(fixed_file), "baseline": "demo"}))

    assert "기준선 저장" in _run(save())
    text = _run(check())
    assert "✅" in text
    assert "없어짐" in text


def test_verify_check_without_baseline(page_file, lens_home) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("verify_fixes", {"source": str(page_file), "baseline": "none"}))

    assert "⚠️" in _run(scenario())


def test_verify_json_mode(page_file, lens_home) -> None:
    async def save():
        async with Client(mcp) as client:
            await client.call_tool("verify_fixes", {"source": str(page_file), "baseline": "j", "mode": "save"})

    async def check():
        async with Client(mcp) as client:
            return _text(
                await client.call_tool("verify_fixes", {"source": str(page_file), "baseline": "j", "format": "json"})
            )

    _run(save())
    data = json.loads(_run(check()))
    assert data["ok"] is True
    assert data["new"] == []


def test_overview_tool() -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("overview", {}))

    text = _run(scenario())
    assert "snapshot_page" in text
    assert "판정하지 않는 것" in text
    assert "image-alt" in text


def test_overview_token_budget() -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("overview", {"max_tokens": 60}))

    text = _run(scenario())
    assert "잘랐습니다" in text


def test_stdio_transport(page_file) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "a11y_lens.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                audited = await session.call_tool("audit_page", {"source": str(page_file)})
                return {tool.name for tool in listed.tools}, _text(audited)

    names, text = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "점수" in text
