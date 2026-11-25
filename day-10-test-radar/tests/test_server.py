"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from mcp.client.client import Client

from conftest import SHOP, make_diff
from test_radar.server import mcp
from test_radar.store import STORE

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "open_repo",
    "read_diff",
    "list_changes",
    "map_tests",
    "impact_report",
    "untested_surface",
    "ci_plan",
    "compare_selections",
    "rule_catalog",
    "overview",
}

SHOP_ROOT = str(ROOT / "examples" / "shop")
PRICING_DIFF = make_diff("shop/pricing.py", SHOP["shop/pricing.py"],
                         SHOP["shop/pricing.py"].replace("0.1", "0.2"))


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


def _repo_ref() -> str:
    out = _call("open_repo", {"path": SHOP_ROOT})
    match = re.search(r"ref: (repo-\d+)", out)
    assert match, out
    return match.group(1)


def _diff_ref() -> str:
    ref = _repo_ref()
    out = _call("read_diff", {"diff": PRICING_DIFF, "repo_ref": ref})
    match = re.search(r"변경집합 (cs-\d+)", out)
    assert match, out
    return match.group(1)


def setup_function() -> None:
    STORE.clear()


def test_lists_all_tools() -> None:
    async def scenario():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}

    assert _run(scenario()) == EXPECTED_TOOLS


def test_open_repo() -> None:
    out = _call("open_repo", {"path": SHOP_ROOT})
    assert "모듈" in out
    assert "ref: repo-" in out
    assert "read_diff" in out


def test_open_repo_missing() -> None:
    out = _call("open_repo", {"path": "/없는/저장소"})
    assert out.startswith("⚠️")


def test_open_repo_relative_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_RADAR_ROOT", str(tmp_path))
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    out = _call("open_repo", {"path": "."})
    assert "ref: repo-" in out


def test_read_diff() -> None:
    ref = _repo_ref()
    out = _call("read_diff", {"diff": PRICING_DIFF, "repo_ref": ref})
    assert "변경집합 cs-" in out
    assert "shop/pricing.py" in out


def test_read_diff_requires_repo() -> None:
    out = _call("read_diff", {"diff": PRICING_DIFF})
    assert out.startswith("⚠️")
    assert "open_repo" in out


def test_read_diff_empty() -> None:
    ref = _repo_ref()
    out = _call("read_diff", {"diff": "", "repo_ref": ref})
    assert out.startswith("⚠️")


def test_read_diff_garbage() -> None:
    ref = _repo_ref()
    out = _call("read_diff", {"diff": "hello\n", "repo_ref": ref})
    assert out.startswith("⚠️")


def test_read_diff_from_file(tmp_path) -> None:
    ref = _repo_ref()
    path = tmp_path / "x.patch"
    path.write_text(PRICING_DIFF, encoding="utf-8")
    out = _call("read_diff", {"path": str(path), "repo_ref": ref})
    assert "변경집합 cs-" in out


def test_list_changes() -> None:
    ref = _diff_ref()
    out = _call("list_changes", {"ref": ref})
    assert "바뀐 심볼" in out
    assert "TAX_RATE" in out


def test_list_changes_hunks() -> None:
    ref = _diff_ref()
    out = _call("list_changes", {"ref": ref, "include_hunks": True})
    assert "@@" in out


def test_list_changes_unknown_ref() -> None:
    out = _call("list_changes", {"ref": "cs-99"})
    assert out.startswith("⚠️")


def test_map_tests() -> None:
    ref = _diff_ref()
    out = _call("map_tests", {"ref": ref})
    assert "tests/test_pricing.py" in out
    assert "L1" in out
    assert "판정하지 않음" in out


def test_map_tests_limit() -> None:
    ref = _diff_ref()
    out = _call("map_tests", {"ref": ref, "limit": 1})
    assert out


def test_impact_report() -> None:
    ref = _diff_ref()
    out = _call("impact_report", {"ref": ref})
    assert "판정:" in out
    assert "위험 규칙" in out


def test_impact_report_shards() -> None:
    ref = _diff_ref()
    out = _call("impact_report", {"ref": ref, "shards": 3})
    assert "조각" in out


def test_untested_surface() -> None:
    ref = _diff_ref()
    out = _call("untested_surface", {"ref": ref})
    assert "테스트 근거" in out


def test_untested_surface_none() -> None:
    ref = _repo_ref()
    diff = make_diff("shop/pricing.py", "def total_for(items):\n    return 0\n",
                     "def total_for(items):\n    return 1\n")
    cs = re.search(r"변경집합 (cs-\d+)", _call("read_diff", {"diff": diff, "repo_ref": ref})).group(1)
    out = _call("untested_surface", {"ref": cs})
    assert "테스트 근거" in out


def test_ci_plan() -> None:
    ref = _diff_ref()
    out = _call("ci_plan", {"ref": ref, "shards": 2})
    assert "python -m pytest" in out
    assert "실행하지 않았습니다" in out


def test_ci_plan_fallback() -> None:
    ref = _repo_ref()
    diff = make_diff("tests/conftest.py", SHOP["tests/conftest.py"], SHOP["tests/conftest.py"] + "\n# x\n")
    cs = re.search(r"변경집합 (cs-\d+)", _call("read_diff", {"diff": diff, "repo_ref": ref})).group(1)
    out = _call("ci_plan", {"ref": cs})
    assert "전체 실행" in out


def test_compare_selections() -> None:
    ref = _repo_ref()
    first = re.search(r"변경집합 (cs-\d+)", _call("read_diff", {"diff": PRICING_DIFF, "repo_ref": ref})).group(1)
    other = make_diff("shop/cart.py", SHOP["shop/cart.py"], SHOP["shop/cart.py"] + "\n# x\n")
    second = re.search(r"변경집합 (cs-\d+)", _call("read_diff", {"diff": other, "repo_ref": ref})).group(1)
    out = _call("compare_selections", {"ref_a": first, "ref_b": second})
    assert "겹침" in out


def test_compare_selections_unknown() -> None:
    out = _call("compare_selections", {"ref_a": "cs-1", "ref_b": "cs-2"})
    assert out.startswith("⚠️")


def test_rule_catalog() -> None:
    out = _call("rule_catalog", {})
    assert "test-config-changed" in out
    assert "규칙 23종" in out


def test_rule_catalog_one() -> None:
    out = _call("rule_catalog", {"rule": "dynamic-import"})
    assert "동적 import" in out
    assert len([line for line in out.splitlines() if line.startswith("[")]) == 1


def test_rule_catalog_unknown() -> None:
    assert _call("rule_catalog", {"rule": "nope"}).startswith("⚠️")


def test_overview() -> None:
    out = _call("overview", {})
    assert "test-radar" in out
    assert "판정하지 않음" in out


def test_token_budget() -> None:
    ref = _diff_ref()
    out = _call("map_tests", {"ref": ref, "max_tokens": 1})
    assert "잘랐습니다" in out


def test_stdio_transport() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "test_radar.server"],
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                opened = await session.call_tool("open_repo", {"path": SHOP_ROOT})
                text = _text(opened)
                ref = re.search(r"ref: (repo-\d+)", text).group(1)
                created = await session.call_tool("read_diff", {"diff": PRICING_DIFF, "repo_ref": ref})
                cs = re.search(r"변경집합 (cs-\d+)", _text(created)).group(1)
                mapped = await session.call_tool("map_tests", {"ref": cs})
                return names, _text(mapped)

    names, mapped = _run(scenario())
    assert names == EXPECTED_TOOLS
    assert "tests/test_pricing.py" in mapped


def test_stdio_root_env() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "test_radar.server"],
            env={**os.environ, "PYTHONPATH": str(ROOT), "TEST_RADAR_ROOT": SHOP_ROOT},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("open_repo", {"path": "."})
                return _text(result)

    assert "ref: repo-" in _run(scenario())
