"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp.client.client import Client

from deadline_clock.server import mcp

NOW = "2026-11-19T10:00:00+09:00"
EXPECTED_TOOLS = {
    "add_deadline",
    "list_deadlines",
    "deadline_status",
    "mark_done",
    "preview_when",
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
def server_db(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "deadlines.db"
    monkeypatch.setenv("DEADLINE_CLOCK_DB", str(path))
    monkeypatch.delenv("DEADLINE_CLOCK_NOW", raising=False)
    return path


def test_lists_six_tools(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_add_then_list(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            added = _text(await client.call_tool(
                "add_deadline",
                {"title": "공모전 제출", "when": "내일 오후 6시", "tags": "contest", "now": NOW},
            ))
            listed = _text(await client.call_tool("list_deadlines", {"now": NOW}))
            return added, listed

    added, listed = _run(scenario())
    assert "새 마감을 등록했습니다" in added
    assert "2026-11-20(금) 18:00 KST" in added
    assert "D-1" in added
    assert "공모전 제출" in listed
    assert "가장 급한 것" in listed


def test_duplicate_add_is_reported(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "공모전 제출", "when": "2026-11-20 18:00", "now": NOW})
            return _text(await client.call_tool(
                "add_deadline", {"title": "공모전 제출", "when": "11/20 18:00", "now": NOW}
            ))

    assert "이미 등록된 마감" in _run(scenario())


def test_status_by_title_then_done_then_undo(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "해커톤 마감", "when": "3일 뒤 18시", "now": NOW})
            status = _text(await client.call_tool("deadline_status", {"ref": "해커톤", "now": NOW}))
            done = _text(await client.call_tool("mark_done", {"ref": "해커톤", "now": NOW}))
            after = _text(await client.call_tool("list_deadlines", {"now": NOW}))
            undone = _text(await client.call_tool("mark_done", {"ref": "해커톤", "done": False, "now": NOW}))
            return status, done, after, undone

    status, done, after, undone = _run(scenario())
    assert "## 기록" in status
    assert "남은 평일" in status
    assert "완료로 표시했습니다" in done
    assert "예정된 마감 없음" in after
    assert "다시 진행 중으로" in undone


def test_preview_does_not_save(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            preview = _text(await client.call_tool("preview_when", {"when": "다음 주 금요일", "now": NOW}))
            listed = _text(await client.call_tool("list_deadlines", {"now": NOW}))
            return preview, listed

    preview, listed = _run(scenario())
    assert "2026-11-27" in preview
    assert "저장하지 않았습니다" in preview
    assert "예정된 마감 없음" in listed


def test_overview_counts(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "급한 것", "when": "+2h", "now": NOW})
            await client.call_tool("add_deadline", {"title": "여유", "when": "12/24", "now": NOW})
            default_view = _text(await client.call_tool("overview", {"now": NOW}))
            wide = _text(await client.call_tool("overview", {"horizon_days": 60, "now": NOW}))
            return default_view, wide

    default_view, wide = _run(scenario())
    assert "열린 마감 **1건** · 완료 0건 · 전체 2건" in default_view  # 12/24 는 14일 밖
    assert "6시간 이내 1" in default_view
    assert "`events`" in default_view
    assert "열린 마감 **2건**" in wide
    assert "여유" in wide


def test_tag_filter_and_all(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "공모전", "when": "11/25", "tags": "contest", "now": NOW})
            await client.call_tool("add_deadline", {"title": "구독", "when": "11/26", "tags": "money", "now": NOW})
            filtered = _text(await client.call_tool("list_deadlines", {"tag": "contest", "now": NOW}))
            everything = _text(await client.call_tool("list_deadlines", {"now": NOW}))
            return filtered, everything

    filtered, everything = _run(scenario())
    assert "공모전" in filtered
    assert "구독" not in filtered
    assert "구독" in everything


def test_window_days_zero_lists_all(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "먼 마감", "when": "2027-06-01", "now": NOW})
            narrow = _text(await client.call_tool("list_deadlines", {"now": NOW}))
            wide = _text(await client.call_tool("list_deadlines", {"window_days": 0, "now": NOW}))
            return narrow, wide

    narrow, wide = _run(scenario())
    assert "예정된 마감 없음" in narrow
    assert "먼 마감" in wide


def test_bad_when_returns_warning(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool(
                "add_deadline", {"title": "이상한 것", "when": "언젠가", "now": NOW}
            ))

    assert _run(scenario()).startswith("⚠️")


def test_dst_gap_is_refused_over_mcp(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool(
                "add_deadline",
                {"title": "뉴욕 새벽", "when": "2026-03-08 02:30 America/New_York", "now": NOW},
            ))

    text = _run(scenario())
    assert text.startswith("⚠️")
    assert "03:30" in text


def test_ambiguous_deadline_is_saved_with_warning(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            added = _text(await client.call_tool(
                "add_deadline",
                {"title": "뉴욕 마감", "when": "2026-11-01 01:30 America/New_York", "now": NOW},
            ))
            status = _text(await client.call_tool("deadline_status", {"ref": "뉴욕", "now": NOW}))
            return added, status

    added, status = _run(scenario())
    assert "두 번" in added
    assert "2026-11-01" in status


def test_unknown_ref_is_reported(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool("deadline_status", {"ref": "없는 마감", "now": NOW}))

    text = _run(scenario())
    assert text.startswith("⚠️")
    assert "list_deadlines" in text


def test_ambiguous_ref_lists_candidates(server_db) -> None:
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("add_deadline", {"title": "공모전 A", "when": "11/25", "now": NOW})
            await client.call_tool("add_deadline", {"title": "공모전 B", "when": "11/26", "now": NOW})
            return _text(await client.call_tool("deadline_status", {"ref": "공모전", "now": NOW}))

    text = _run(scenario())
    assert "여러 개가 걸립니다" in text
    assert "dl_" in text


def test_stdio_transport(server_db) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deadline_clock.server"],
        env={
            **os.environ,
            "DEADLINE_CLOCK_DB": str(server_db),
            "PYTHONPATH": str(root),
        },
        cwd=str(root),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                added = await session.call_tool(
                    "add_deadline", {"title": "stdio 확인", "when": "11월 25일", "now": NOW}
                )
                return names, _text(added)

    names, text = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "새 마감을 등록했습니다" in text
    assert "2026-11-25" in text
