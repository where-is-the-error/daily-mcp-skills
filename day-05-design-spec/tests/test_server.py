"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client.client import Client

from design_spec.server import mcp

ROOT = Path(__file__).resolve().parent.parent
BEFORE = ROOT / "examples" / "demo" / "before.json"
AFTER = ROOT / "examples" / "demo" / "after.json"
EXPECTED_TOOLS = {
    "read_design",
    "find_in_design",
    "palette_report",
    "scale_report",
    "audit_design",
    "fix_order",
    "write_design_md",
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


def test_lists_eight_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_every_tool_has_a_description() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return [(tool.name, tool.description or "") for tool in listed.tools]

    for name, description in _run(scenario()):
        assert len(description) > 20, name


def test_read_design() -> None:
    output = _call("read_design", {"source": str(BEFORE)})
    assert output.startswith('document "예제몰')
    assert "ref=e" in output


def test_read_design_modes() -> None:
    layout = _call("read_design", {"source": str(BEFORE), "mode": "layout", "depth": 3})
    visual = _call("read_design", {"source": str(BEFORE), "mode": "visual"})
    assert "@" in layout
    assert "fill" in visual


def test_read_design_ref() -> None:
    output = _call("read_design", {"source": str(BEFORE), "ref": "e29"})
    assert "Button/Pay" in output


def test_read_design_missing_file() -> None:
    assert "⚠️" in _call("read_design", {"source": "없는파일.json"})


def test_read_design_inline_json() -> None:
    payload = json.dumps({"type": "FRAME", "name": "Inline", "children": []})
    assert "Inline" in _call("read_design", {"source": payload})


def test_read_design_token_budget() -> None:
    output = _call("read_design", {"source": str(BEFORE), "max_tokens": 40})
    assert "잘랐습니다" in output


def test_find_in_design() -> None:
    output = _call("find_in_design", {"source": str(BEFORE), "text": "쿠폰"})
    assert "ref=e" in output
    assert "경로:" in output


def test_find_in_design_regex() -> None:
    assert "instance" in _call("find_in_design", {"source": str(BEFORE), "regex": "icon"})


def test_find_in_design_needs_a_needle() -> None:
    assert "⚠️" in _call("find_in_design", {"source": str(BEFORE)})


def test_find_in_design_bad_regex() -> None:
    assert "⚠️" in _call("find_in_design", {"source": str(BEFORE), "regex": "["})


def test_find_in_design_no_match() -> None:
    assert "없습니다" in _call("find_in_design", {"source": str(BEFORE), "text": "없는말"})


def test_palette_report() -> None:
    output = _call("palette_report", {"source": str(BEFORE)})
    assert "색 10종" in output
    assert "거의 같은 색" in output
    assert "역할(추정)" in output


def test_palette_report_tolerance() -> None:
    strict = _call("palette_report", {"source": str(BEFORE), "tolerance": 1})
    loose = _call("palette_report", {"source": str(BEFORE), "tolerance": 60})
    assert "거의 같은 색 없음" in strict
    assert "거의 같은 색 없음" not in loose


def test_palette_report_max_colors() -> None:
    output = _call("palette_report", {"source": str(BEFORE), "max_colors": 3})
    assert "종 더" in output


def test_scale_report_spacing() -> None:
    output = _call("scale_report", {"source": str(BEFORE), "kind": "spacing"})
    assert "기준 단위" in output
    assert "스케일 밖" in output


def test_scale_report_type() -> None:
    output = _call("scale_report", {"source": str(BEFORE), "kind": "type"})
    assert "6단계" in output
    assert "붙어 있는 단계" in output


def test_scale_report_radius() -> None:
    output = _call("scale_report", {"source": str(BEFORE), "kind": "radius"})
    assert "반경" in output


def test_scale_report_rejects_unknown_kind() -> None:
    assert "⚠️" in _call("scale_report", {"source": str(BEFORE), "kind": "nope"})


def test_audit_design_markdown() -> None:
    output = _call("audit_design", {"source": str(BEFORE)})
    assert "점수 **0/100**" in output
    assert "contrast-text" in output


def test_audit_design_json() -> None:
    data = json.loads(_call("audit_design", {"source": str(BEFORE), "format": "json"}))
    assert data["score"] == 0
    assert {item["rule"] for item in data["violations"]} >= {"contrast-text", "touch-target"}


def test_audit_design_rule_filter() -> None:
    data = json.loads(
        _call("audit_design", {"source": str(BEFORE), "rules": "touch-target", "format": "json"})
    )
    assert {item["rule"] for item in data["violations"]} == {"touch-target"}


def test_audit_design_min_touch() -> None:
    data = json.loads(
        _call("audit_design", {"source": str(BEFORE), "min_touch": 24, "format": "json"})
    )
    assert "touch-target" not in {item["rule"] for item in data["violations"]}


def test_audit_design_clean_file() -> None:
    assert "위반 없음" in _call("audit_design", {"source": str(AFTER)})


def test_fix_order() -> None:
    output = _call("fix_order", {"source": str(BEFORE)})
    assert "고치기 순서" in output
    assert "바꿀 것" in output


def test_fix_order_clean_file() -> None:
    assert "✅" in _call("fix_order", {"source": str(AFTER)})


def test_write_design_md_inline() -> None:
    output = _call("write_design_md", {"source": str(AFTER)})
    assert "## 1. Visual Theme & Atmosphere" in output
    assert "## 5. Layout Principles" in output


def test_write_design_md_saves_inside_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DESIGN_SPEC_ROOT", str(tmp_path))
    output = _call("write_design_md", {"source": str(AFTER), "save_to": "DESIGN.md"})
    saved = tmp_path / "DESIGN.md"
    assert saved.exists()
    assert "💾" in output
    assert "Design System" in saved.read_text(encoding="utf-8")


def test_write_design_md_refuses_outside_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DESIGN_SPEC_ROOT", str(tmp_path / "inside"))
    (tmp_path / "inside").mkdir()
    output = _call("write_design_md", {"source": str(AFTER), "save_to": "../escape.md"})
    assert "⚠️" in output
    assert not (tmp_path / "escape.md").exists()


def test_write_design_md_token_budget() -> None:
    output = _call("write_design_md", {"source": str(AFTER), "max_tokens": 50})
    assert "잘랐습니다" in output


def test_overview() -> None:
    output = _call("overview", {})
    assert "read_design" in output
    assert "판정하지 않는 것" in output
    assert "contrast-text" in output


def test_overview_token_budget() -> None:
    assert "잘랐습니다" in _call("overview", {"max_tokens": 40})


def test_stdio_transport() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "design_spec.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool("audit_design", {"source": str(BEFORE)})
                return {tool.name for tool in listed.tools}, _text(result)

    names, output = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "점수" in output
