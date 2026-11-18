"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp.client.client import Client

from web_memo import fetch
from web_memo.server import mcp

EXPECTED_TOOLS = {"remember_page", "page_changes", "recall", "annotate", "overview"}


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
def memo_db(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "memo.db"
    monkeypatch.setenv("WEB_MEMO_DB", str(path))
    return path


@pytest.fixture
def fake_fetch(monkeypatch):
    """네트워크 대신 고정된 페이지를 돌려주는 가짜 fetch."""
    state = {"text": "타임아웃은 30초입니다.\n재시도는 3회입니다."}

    def _fake(url, **kwargs):
        from datetime import datetime, timezone

        normalized = fetch.normalize_url(url)
        return fetch.Page(
            url=normalized,
            final_url=normalized,
            status=200,
            title="API 타임아웃",
            text=state["text"],
            content_type="text/html",
            size_bytes=len(state["text"]),
            fetched_at=datetime(2026, 11, 18, 1, tzinfo=timezone.utc),
            robots_url="robots.txt 허용",
        )

    monkeypatch.setattr("web_memo.fetch.fetch_page", _fake)
    return state


def test_server_lists_five_tools(memo_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_remember_then_unchanged_then_changed(memo_db, fake_fetch) -> None:
    async def scenario():
        async with Client(mcp) as client:
            first = _text(await client.call_tool("remember_page",
                                                 {"url": "https://docs.example.com/api"}))
            second = _text(await client.call_tool("remember_page",
                                                  {"url": "https://docs.example.com/api"}))
            fake_fetch["text"] = "타임아웃은 60초입니다.\n재시도는 3회입니다."
            third = _text(await client.call_tool("remember_page",
                                                 {"url": "https://docs.example.com/api"}))
            return first, second, third

    first, second, third = _run(scenario())
    assert "새로 기억함" in first
    assert "변경" in second
    assert "변경 없음" in second
    assert "바뀐 부분" in third
    assert "+ 타임아웃은 60초입니다." in third


def test_page_changes_over_mcp(memo_db, fake_fetch) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("remember_page", {"url": "https://docs.example.com/api"})
            fake_fetch["text"] = "타임아웃은 90초입니다.\n재시도는 3회입니다."
            await client.call_tool("remember_page", {"url": "https://docs.example.com/api"})
            return _text(await client.call_tool("page_changes",
                                                {"url": "https://docs.example.com/api"}))

    text = _run(scenario())
    assert "## 차이" in text
    assert "- 타임아웃은 30초입니다." in text
    assert "+ 타임아웃은 90초입니다." in text


def test_recall_over_mcp(memo_db, fake_fetch) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("remember_page", {"url": "https://docs.example.com/api"})
            return _text(await client.call_tool("recall", {"query": "재시도"}))

    text = _run(scenario())
    assert "docs.example.com/api" in text
    assert "재시도" in text


def test_annotate_over_mcp(memo_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool(
                "annotate",
                {"target": "https://docs.example.com/api", "note": "여기 자주 바뀜", "tags": "docs,api"},
            ))

    text = _run(scenario())
    assert "#docs" in text
    assert "여기 자주 바뀜" in text


def test_overview_over_mcp(memo_db, fake_fetch) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("remember_page", {"url": "https://docs.example.com/api"})
            return _text(await client.call_tool("overview", {"stale_days": 7}))

    text = _run(scenario())
    assert "기억한 페이지 1개" in text
    assert "docs.example.com/api" in text


def test_bad_url_is_refused_over_mcp(memo_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("remember_page", {"url": "file:///etc/passwd"}))

    assert _run(scenario()).startswith("⚠️")


def test_page_changes_on_unknown_url(memo_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("page_changes", {"url": "https://nope.example.com/x"}))

    assert "기억에 없는 페이지" in _run(scenario())


def test_stdio_transport(memo_db) -> None:
    """실제 프로세스를 stdio로 띄워 툴 목록과 호출을 확인한다."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "web_memo.server"],
        env={**os.environ, "WEB_MEMO_DB": str(memo_db), "PYTHONPATH": str(root)},
        cwd=str(root),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                called = await session.call_tool("overview", {"stale_days": 30})
                return names, _text(called)

    names, text = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "web-memo · overview" in text
