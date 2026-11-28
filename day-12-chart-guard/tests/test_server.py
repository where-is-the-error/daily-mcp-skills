"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client

from chart_guard.server import mcp
from chart_guard.store import STORE

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

EXPECTED_TOOLS = {
    "read_chart",
    "describe_chart",
    "distortion_report",
    "find_problems",
    "chart_check",
    "fix_plan",
    "alt_text",
    "compare_charts",
    "rule_catalog",
    "overview",
}


@pytest.fixture(autouse=True)
def clean_store():
    STORE.clear()
    yield
    STORE.clear()


def _text(result) -> str:
    chunks = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _call(name: str, arguments: dict) -> str:
    async def scenario():
        async with Client(mcp) as client:
            return _text(await client.call_tool(name, arguments))

    return asyncio.run(scenario())


def _ref(out: str, pattern: str) -> str:
    match = re.search(pattern, out)
    assert match, out
    return match.group(1)


BEFORE = (EXAMPLES / "before.json").read_text(encoding="utf-8")
AFTER = (EXAMPLES / "after.json").read_text(encoding="utf-8")
PIE = (EXAMPLES / "pie-before.json").read_text(encoding="utf-8")


class TestToolList:
    def test_tools(self):
        async def scenario():
            async with Client(mcp) as client:
                return {tool.name for tool in (await client.list_tools()).tools}

        assert asyncio.run(scenario()) == EXPECTED_TOOLS

    def test_overview(self):
        text = _call("overview", {})
        assert "chart-guard" in text
        assert "41종" in text
        assert "판정하지 않음" in text
        assert "스펙을 고치지 않고" in text


class TestReadChart:
    def test_inline_spec(self):
        text = _call("read_chart", {"spec": BEFORE})
        assert "차트 — 막대" in text
        assert "범주 9개" in text
        assert _ref(text, r"차트 ref: (c-\d+)")

    def test_from_path(self):
        text = _call("read_chart", {"path": str(EXAMPLES / "before.json")})
        assert "차트 — 막대" in text

    def test_root_relative_path(self, monkeypatch):
        monkeypatch.setenv("CHART_GUARD_ROOT", str(EXAMPLES))
        text = _call("read_chart", {"path": "before.json"})
        assert "차트 — 막대" in text

    def test_no_input(self):
        text = _call("read_chart", {})
        assert text.startswith("⚠️")

    def test_bad_spec(self):
        text = _call("read_chart", {"spec": "{\"hello\":1}"})
        assert text.startswith("⚠️")
        assert "읽을 수 있는" in text

    def test_korean_stays_readable(self):
        text = _call("read_chart", {"spec": BEFORE})
        assert "서울" in text or "2026" in text


class TestDescribe:
    def test_describe(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("describe_chart", {"chart_ref": ref})
        assert "설명 —" in text
        assert "한 줄 요약" in text
        assert "판정하지 않음" in text

    def test_bad_ref(self):
        text = _call("describe_chart", {"chart_ref": "c-9"})
        assert text.startswith("⚠️")
        assert "read_chart" in text


class TestDistortion:
    def test_numbers(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("distortion_report", {"chart_ref": ref})
        assert "화면 길이비" in text
        assert "과장" in text
        assert "렌더링 결과를 재지 않습니다" in text

    def test_bad_ref(self):
        assert _call("distortion_report", {"chart_ref": "c-1"}).startswith("⚠️")


class TestProblems:
    def test_all(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("find_problems", {"chart_ref": ref})
        assert "막음" in text
        assert "bar-truncated-baseline" in text

    def test_only_block(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("find_problems", {"chart_ref": ref, "severity": "block"})
        assert "bar-truncated-baseline" in text
        assert "unsorted-bars" not in text


class TestCheck:
    def test_check_by_ref(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("chart_check", {"chart_ref": ref})
        assert "판정: 보류" in text
        assert "고치기 순서" in text
        assert _ref(text, r"보고서 ref: (r-\d+)")

    def test_check_one_shot(self):
        text = _call("chart_check", {"spec": AFTER})
        assert "판정: 통과" in text
        assert "(100/100)" in text

    def test_needs_input(self):
        assert _call("chart_check", {}).startswith("⚠️")


class TestFixAndAlt:
    def test_fix_plan(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("fix_plan", {"chart_ref": ref})
        assert "고친 스펙" in text
        assert '"min": 0' in text
        assert "고치면 이렇게 바뀝니다" in text

    def test_fix_plan_without_spec(self):
        ref = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        text = _call("fix_plan", {"chart_ref": ref, "include_spec": False})
        assert "고친 스펙" not in text
        assert "고치기" in text

    def test_corrected_spec_is_json(self):
        ref = _ref(_call("read_chart", {"spec": PIE}), r"차트 ref: (c-\d+)")
        text = _call("fix_plan", {"chart_ref": ref})
        start = text.index("{")
        payload = json.loads(text[start : text.rindex("}") + 1])
        assert payload["type"] == "bar"

    def test_alt_text(self):
        ref = _ref(_call("read_chart", {"spec": AFTER}), r"차트 ref: (c-\d+)")
        text = _call("alt_text", {"chart_ref": ref})
        assert "alt (" in text
        assert "| 구분 |" in text

    def test_bad_ref(self):
        assert _call("alt_text", {"chart_ref": "c-3"}).startswith("⚠️")


class TestCompare:
    def test_compare(self):
        before = _ref(_call("read_chart", {"spec": BEFORE}), r"차트 ref: (c-\d+)")
        after = _ref(_call("read_chart", {"spec": AFTER}), r"차트 ref: (c-\d+)")
        text = _call("compare_charts", {"before_ref": before, "after_ref": after})
        assert "전후 비교" in text
        assert "고쳐진 것" in text
        assert "잃은 값 없음" in text

    def test_bad_ref(self):
        assert _call("compare_charts", {"before_ref": "c-8", "after_ref": "c-9"}).startswith("⚠️")


class TestRules:
    def test_catalog(self):
        text = _call("rule_catalog", {})
        assert "규칙 41종" in text
        assert "bar-truncated-baseline" in text
        assert "문제 아닌 때" in text

    def test_one(self):
        text = _call("rule_catalog", {"rule": "rainbow-palette"})
        assert "무지개" in text
        assert "three-d" not in text

    def test_unknown(self):
        assert _call("rule_catalog", {"rule": "nope"}).startswith("⚠️")


class TestStdio:
    def test_stdio_lists_tools(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "chart_guard.server"],
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            cwd=str(ROOT),
        )

        async def scenario():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return {tool.name for tool in tools.tools}

        try:
            names = asyncio.run(scenario())
        except Exception as exc:  # pragma: no cover - 환경 문제
            pytest.skip(f"stdio 기동 실패: {exc}")
        assert names == EXPECTED_TOOLS

    def test_stdio_calls_a_tool(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "chart_guard.server"],
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            cwd=str(ROOT),
        )

        async def scenario():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("chart_check", {"spec": AFTER})
                    return _text(result)

        try:
            text = asyncio.run(scenario())
        except Exception as exc:  # pragma: no cover - 환경 문제
            pytest.skip(f"stdio 기동 실패: {exc}")
        assert "판정: 통과" in text
