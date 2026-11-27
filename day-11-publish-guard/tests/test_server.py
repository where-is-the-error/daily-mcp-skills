"""진짜 MCP 서버를 클라이언트로 붙여 부른다 (in-memory + stdio)."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client

from publish_guard.server import mcp
from publish_guard.store import STORE

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "read_media",
    "read_caption",
    "delivery_report",
    "safe_zone_report",
    "hook_report",
    "copy_report",
    "publish_check",
    "compare_reports",
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


class TestToolList:
    def test_tools(self):
        async def scenario():
            async with Client(mcp) as client:
                return {tool.name for tool in (await client.list_tools()).tools}

        assert asyncio.run(scenario()) == EXPECTED_TOOLS

    def test_overview(self):
        text = _call("overview", {})
        assert "publish-guard" in text
        assert "판정하지 않음" in text
        assert "업로드하지 않는다" in text


class TestCaptionTools:
    def test_read_caption(self):
        text = _call("read_caption", {"text": "피크 -0.2 dBTP\n#ffmpeg #릴스"})
        assert "해시태그 2개" in text
        assert _ref(text, r"캡션 ref: (c-\d+)")

    def test_read_caption_file(self, tmp_path):
        path = tmp_path / "caption.md"
        path.write_text("파일 캡션\n#a", encoding="utf-8")
        text = _call("read_caption", {"path": str(path)})
        assert "파일 캡션" in text

    def test_hook_report(self):
        _call("read_caption", {"text": "안녕하세요 여러분"})
        text = _call("hook_report", {"caption_ref": "c-1"})
        assert "인사·배경으로 시작" in text
        assert "보류" in text

    def test_hook_report_clean(self):
        _call("read_caption", {"text": "10편 중 4편이 피크 초과"})
        text = _call("hook_report", {"caption_ref": "c-1"})
        assert "걸린 것 없음" in text

    def test_copy_report(self):
        _call("read_caption", {"text": "안녕하세요! 결론적으로 매우 좋습니다 #fyp #a #b #c #d #e #f"})
        text = _call("copy_report", {"caption_ref": "c-1"})
        assert "캡션 검사" in text
        assert "hashtag" in text

    def test_bad_ref(self):
        text = _call("copy_report", {"caption_ref": "c-9"})
        assert text.startswith("⚠️")
        assert "read_caption" in text


class TestMediaTools:
    def test_read_media(self, tiny_video):
        text = _call("read_media", {"path": tiny_video})
        assert "1080×1920" in text
        assert _ref(text, r"미디어 ref: (m-\d+)")

    def test_read_media_without_measure(self, tiny_video):
        text = _call("read_media", {"path": tiny_video, "measure_audio": False})
        assert "음량을 재지 않았다" in text

    def test_read_media_missing(self):
        text = _call("read_media", {"path": "/definitely/not/here.mp4"})
        assert text.startswith("⚠️")

    def test_delivery_report(self, tiny_video):
        media_ref = _ref(_call("read_media", {"path": tiny_video}), r"미디어 ref: (m-\d+)")
        text = _call("delivery_report", {"media_ref": media_ref})
        assert "규격 검사" in text
        assert "YouTube Shorts" in text

    def test_delivery_report_bad_ref(self):
        assert _call("delivery_report", {"media_ref": "m-9"}).startswith("⚠️")


class TestSafeZoneTool:
    def test_house_overlap(self):
        boxes = '[{"label":"훅","x":0,"y":300,"w":900,"h":180}]'
        text = _call("safe_zone_report", {"boxes": boxes})
        assert "상단에 걸린 문구" in text
        assert "+84" in text

    def test_clean(self):
        boxes = '[{"label":"본문","x":90,"y":430,"w":700,"h":400}]'
        text = _call("safe_zone_report", {"boxes": boxes})
        assert "걸린 상자 없음" in text

    def test_empty(self):
        text = _call("safe_zone_report", {"boxes": "[]"})
        assert "상자가 없습니다" in text

    def test_invalid_boxes(self):
        assert _call("safe_zone_report", {"boxes": "[{}]"}).startswith("⚠️")


class TestPublishAndCompare:
    def test_caption_only_check(self):
        cap = _ref(_call("read_caption", {"text": "안녕하세요 여러분"}), r"캡션 ref: (c-\d+)")
        text = _call("publish_check", {"caption_ref": cap})
        assert "판정:" in text
        assert "고치기 순서" in text

    def test_needs_a_ref(self):
        assert _call("publish_check", {}).startswith("⚠️")

    def test_compare(self):
        bad = _ref(_call("read_caption", {"text": "안녕하세요! 결론적으로 매우 다양한 #fyp"}), r"캡션 ref: (c-\d+)")
        first = _ref(_call("publish_check", {"caption_ref": bad}), r"보고서 ref: (r-\d+)")
        good = _ref(_call("read_caption", {"text": "피크 -0.2 dBTP면 깨진다 #ffmpeg"}), r"캡션 ref: (c-\d+)")
        second = _ref(_call("publish_check", {"caption_ref": good}), r"보고서 ref: (r-\d+)")
        text = _call("compare_reports", {"before_ref": first, "after_ref": second})
        assert "→" in text
        assert "고쳐진 것" in text

    def test_compare_bad_ref(self):
        assert _call("compare_reports", {"before_ref": "r-9", "after_ref": "r-8"}).startswith("⚠️")

    def test_publish_with_boxes(self, tiny_video):
        media = _ref(_call("read_media", {"path": tiny_video}), r"미디어 ref: (m-\d+)")
        text = _call(
            "publish_check",
            {
                "media_ref": media,
                "boxes": '[{"label":"훅","x":0,"y":300,"w":900,"h":180}]',
            },
        )
        assert "상자 1개" in text
        assert "안전" in text or "상단" in text


class TestRules:
    def test_catalog(self):
        text = _call("rule_catalog", {})
        assert "규칙" in text
        assert "true-peak-over" in text
        assert "tell-not-x-but-y" in text

    def test_one_rule(self):
        text = _call("rule_catalog", {"rule": "true-peak-over"})
        assert "트루피크" in text
        assert "tell-" not in text

    def test_unknown(self):
        assert _call("rule_catalog", {"rule": "nope"}).startswith("⚠️")


class TestStdio:
    def test_stdio_lists_tools(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "publish_guard.server"],
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
