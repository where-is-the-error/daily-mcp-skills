"""End-to-end: start the real MCP server and talk to it as a client would."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from mcp.client.client import Client

from repo_context.server import mcp

EXPECTED_TOOLS = {"repo_overview", "recent_changes", "file_outline", "context_pack"}


def _text(result) -> str:
    chunks = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _run(coro):
    return asyncio.run(coro)


def test_server_lists_four_tools(monkeypatch, repo: Path) -> None:
    monkeypatch.setenv("REPO_CONTEXT_ROOT", str(repo))

    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_context_pack_over_mcp(monkeypatch, repo: Path) -> None:
    monkeypatch.setenv("REPO_CONTEXT_ROOT", str(repo))

    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("context_pack", {"max_tokens": 600}))

    text = _run(scenario())
    assert text.startswith("# repo-context")
    assert "`main`" in text


def test_overview_and_outline_over_mcp(monkeypatch, repo: Path) -> None:
    monkeypatch.setenv("REPO_CONTEXT_ROOT", str(repo))

    async def scenario():
        async with Client(mcp) as client:
            overview = _text(await client.call_tool("repo_overview", {}))
            outlined = _text(await client.call_tool("file_outline", {"file": "app.py"}))
            recent = _text(await client.call_tool("recent_changes", {"limit": 2}))
            return overview, outlined, recent

    overview, outlined, recent = _run(scenario())
    assert "커밋: 2개" in overview
    assert "class `Greeter`" in outlined
    assert "fix: 로케일 주석" in recent


def test_sandbox_escape_over_mcp_is_refused(monkeypatch, repo: Path) -> None:
    monkeypatch.setenv("REPO_CONTEXT_ROOT", str(repo))

    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("file_outline", {"file": "../../etc/passwd"}))

    assert _run(scenario()).startswith("⚠️")
