"""MCP 배선 — 열 툴.

    PUBLISH_GUARD_ROOT=/path/to/videos python -m publish_guard.server

MCP 클라이언트 설정:

    {"mcpServers": {"publish-guard": {
      "command": "python", "args": ["-m", "publish_guard.server"],
      "env": {"PUBLISH_GUARD_ROOT": "/path/to/videos"}}}}

읽기 전용이다. 영상을 고치지 않고, 업로드하지 않는다 — ffmpeg 명령은 문자열로만 만든다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import caption as caption_module
from . import check, hook as hook_module, probe, report, rules, safearea, tells
from .platforms import DEFAULT_PLATFORMS, PROFILES, parse_platforms
from .store import STORE
from .types import Report

LIMITS = report.LIMITS

OVERVIEW = """publish-guard — 올리기 전 12초, 파일과 글을 같은 자리에서 검사한다.

1. read_media 로 영상을 재고(read_media → ref), read_caption 으로 캡션을 읽습니다.
2. publish_check 한 번으로 파일 규격·음량·훅·캡션·화면 상자를 함께 봅니다.
3. 고친 뒤 다시 읽어 compare_reports 로 0→100 을 확인합니다.

재는 것: ffprobe 의 길이·해상도·fps·코덱·크기, ffmpeg ebur128 의 통합 음량·트루피크, silencedetect 의 앞뒤 무음.
읽는 것: 첫 줄(훅), 해시태그·멘션·링크, AI 글투 신호, 선언된 문구 상자의 좌표.
읽지 않는 것: 영상 안에 실제로 그려진 글자, 사람이 느끼는 재미, 플랫폼 심사.

태도
· 잰 값만 말한다. 재지 못한 것은 '재지 못했다'고 적는다.
· 강한 AI 신호는 한 번만 봐도 고치고, 약한 신호는 둘 이상 겹칠 때만 고친다.
· 캡션을 고칠 때 숫자·날짜·링크·해시태그가 사라지면 그 사실을 먼저 알린다.
· 영상을 고치지 않고 업로드하지 않는다. 명령은 문자열로만 만든다.

""" + LIMITS

mcp = MCPServer(
    name="publish-guard",
    title="publish-guard",
    version="0.1.0",
    instructions=(
        "올리기 전에 영상과 캡션을 함께 검사합니다. "
        "read_media 로 파일을 재고, read_caption 으로 캡션을 읽은 뒤, publish_check 로 규격·음량·훅·캡션·안전 영역을 한 번에 봅니다. "
        "고친 파일과 캡션을 다시 읽어 compare_reports 로 점수 변화와 잃은 사실을 확인합니다. "
        "영상을 고치거나 업로드하지 않습니다. 실제 화면의 글자 위치는 읽지 못하고 선언된 상자만 봅니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("PUBLISH_GUARD_ROOT")
    return Path(root) if root else None


def _path(value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    root = _root()
    return str(root / path) if root else str(path)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _platforms(value: str) -> tuple[str, ...]:
    return parse_platforms(value)


@mcp.tool()
def read_media(path: str, measure_audio: bool = True) -> str:
    """영상 파일을 재서 사실을 돌려준다 — 길이·해상도·fps·코덱·크기·음량·트루피크·앞뒤 무음.

    path: 파일 경로 (PUBLISH_GUARD_ROOT 기준 상대경로 가능).
    measure_audio: false 면 ffprobe 만 쓴다 (음량·무음은 비운다).
    파일은 고치지 않는다.
    """
    try:
        facts = probe.probe(_path(path), measure_audio=measure_audio)
        ref = STORE.add_media(facts)
        lines = report.media_lines(facts)
        gaps = facts.missing()
        if gaps:
            lines.append("  비어 있는 값: " + ", ".join(gaps))
        lines.append("")
        lines.append("영상은 고치지 않았습니다 — 잰 값만 읽었습니다.")
        lines.append(LIMITS)
        lines.append(f"미디어 ref: {ref}")
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def read_caption(text: str = "", path: str = "", hook: str = "", section: str = "") -> str:
    """캡션을 읽어 첫 줄·훅·해시태그·멘션·링크·길이·언어를 돌려준다.

    text: 캡션 본문. path: 본문 파일(텍스트가 비었을 때만). hook: 화면에 띄운 훅 문구(없으면 첫 줄).
    section: 마크다운 캡션 파일에서 꺼낼 `##` 구역 이름. "auto" 면 본문/캡션 구역.
    고치지 않는다.
    """
    try:
        facts = caption_module.read_caption(text=text, path=_path(path) if path else "", hook=hook, section=section)
        ref = STORE.add_caption(facts)
        lines = report.caption_lines(facts)
        if facts.hashtags:
            lines.append("  해시태그: " + ", ".join("#" + tag for tag in facts.hashtags[:20]))
            if len(facts.hashtags) > 20:
                lines.append(f"  … 외 {len(facts.hashtags) - 20}개")
        if facts.links:
            lines.append("  링크: " + ", ".join(facts.links[:5]))
        lines.append("")
        lines.append(LIMITS)
        lines.append(f"캡션 ref: {ref}")
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def delivery_report(media_ref: str, platforms: str = "all") -> str:
    """파일만 플랫폼 규격에 걸어 판정한다 (캡션·훅은 보지 않는다).

    media_ref: read_media 가 돌려준 ref. platforms: all 또는 youtube_shorts,instagram_reels,tiktok,house.
    """
    try:
        media = STORE.media(media_ref)
        keys = _platforms(platforms)
        findings = check.check_media(media, keys)
        result = Report(media=media, caption=None, platforms=keys, findings=findings, created_at=check._now())
        lines = [f"규격 검사 — {media.path}", ""]
        lines.extend(report.verdict_lines(result))
        lines.append("")
        lines.extend(report.finding_lines(result.ordered()))
        lines.append("")
        lines.extend(report.platform_lines(result))
        lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def safe_zone_report(boxes: str, media_ref: str = "", zone_set: str = "house", platforms: str = "all") -> str:
    """선언된 문구 상자가 상단·하단·우측 버튼 영역에 걸리는지 보고, 몇 px 옮기면 되는지 계산한다.

    boxes: JSON. [{"label":"훅","x":0,"y":430,"w":900,"h":180}, ...] 또는 {"boxes":[...]}.
    media_ref: 있으면 그 해상도를 화면 크기로 쓴다 (없으면 1080x1920).
    zone_set: house(내 규칙) | platform(플랫폼 추정/공식) | both.
    영상 픽셀을 읽지 않는다 — 선언된 상자만 본다.
    """
    try:
        media = STORE.media(media_ref) if media_ref else None
        canvas = safearea.canvas_for(media)
        box_list = safearea.parse_boxes(boxes)
        keys = _platforms(platforms)
        findings = check.check_boxes(box_list, canvas, keys, zone_set)
        result = Report(
            media=media,
            caption=None,
            platforms=keys,
            findings=findings,
            boxes_checked=len(box_list),
            created_at=check._now(),
        )
        lines = [f"화면 검사 — {canvas[0]}×{canvas[1]} · 상자 {len(box_list)}개 · 영역 {zone_set}", ""]
        if not box_list:
            lines.append("상자가 없습니다. 편집 파이프라인이 문구 좌표를 넘겨야 검사할 수 있습니다.")
        elif not findings:
            lines.append("걸린 상자 없음 — 선언된 문구는 모두 안전 영역 안에 있다.")
        else:
            lines.extend(report.finding_lines(result.ordered()))
        lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def hook_report(caption_ref: str = "", hook: str = "") -> str:
    """첫 1.5초 훅을 판정한다 — 인사·예고로 시작하는지, 숫자나 결과가 있는지, 길이.

    caption_ref 또는 hook 중 하나. caption_ref 를 주면 그 캡션의 훅(첫 줄)을 본다.
    """
    try:
        facts = STORE.caption(caption_ref) if caption_ref else caption_module.read_caption(text=hook)
        if caption_ref and hook:
            facts = caption_module.read_caption(text=facts.text, hook=hook)
        findings = hook_module.check_hook(facts.hook, facts.first_line, facts.language)
        score = max(0, 100 - sum(f.weight for f in findings))
        lines = [f"훅 검사 — '{facts.hook or '(없음)'}' ({facts.hook_chars_nospace}자, {facts.language})", ""]
        lines.append(f"판정: {report.verdict_text('hold' if any(f.severity == 'block' for f in findings) else 'pass')} ({score}/100)")
        lines.append("")
        lines.extend(report.finding_lines(findings))
        if not findings:
            lines.append("걸린 것 없음 — 첫 줄이 결론이고 잰 값이 들어 있다.")
        lines.append("")
        lines.append("첫 1.5초에 실제로 보이는 것은 영상 프레임이다 — 여기서는 선언된 훅 문구만 본다.")
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def copy_report(caption_ref: str, platforms: str = "all", keyword: str = "") -> str:
    """캡션만 검사한다 — 길이 상한·해시태그·첫 줄·AI 글투와 약한 신호의 겹침.

    caption_ref: read_caption 이 돌려준 ref. keyword: 앞 125자에 있어야 할 검색어.
    """
    try:
        caption = STORE.caption(caption_ref)
        keys = _platforms(platforms)
        findings = check.check_caption(caption, keys, keyword)
        result = Report(media=None, caption=caption, platforms=keys, findings=findings, created_at=check._now())
        lines = [f"캡션 검사 — {caption.chars}자 · 해시태그 {caption.hashtag_count}개", ""]
        lines.extend(report.verdict_lines(result))
        lines.append("")
        lines.extend(report.finding_lines(result.ordered(), show_command=False))
        if not findings:
            lines.append("걸린 것 없음.")
        lines.append("")
        lines.append(LIMITS)
        return "\n".join(lines)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def publish_check(
    media_ref: str = "",
    caption_ref: str = "",
    platforms: str = "all",
    boxes: str = "",
    keyword: str = "",
    zone_set: str = "house",
) -> str:
    """파일·화면·훅·캡션을 한 번에 검사하고 점수·판정·고치기 순서를 돌려준다.

    media_ref·caption_ref 는 각각 read_media·read_caption 의 ref (하나만 있어도 된다).
    boxes: 문구 상자 JSON (safe_zone_report 와 같은 형식). keyword: 캡션 앞부분에 있어야 할 검색어.
    영상을 고치지 않고 업로드하지 않는다 — 명령은 문자열로만 만든다.
    """
    try:
        if not media_ref and not caption_ref:
            return "⚠️ media_ref 또는 caption_ref 가 필요합니다."
        media = STORE.media(media_ref) if media_ref else None
        caption = STORE.caption(caption_ref) if caption_ref else None
        keys = _platforms(platforms)
        box_list = safearea.parse_boxes(boxes) if boxes else []
        result = check.publish_check(
            media=media,
            caption=caption,
            platforms=keys,
            boxes=box_list,
            keyword=keyword,
            zone_set=zone_set,
        )
        ref = STORE.add_report(result)
        return report.publish_report(result)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_reports(before_ref: str, after_ref: str) -> str:
    """두 검사 결과를 비교한다 — 점수 변화, 고쳐진 규칙, 남은 규칙, 캡션에서 잃은 숫자·해시태그·링크.

    before_ref · after_ref: publish_check 가 돌려준 보고서 ref.
    """
    try:
        before = STORE.report(before_ref)
        after = STORE.report(after_ref)
        return report.compare_report(check.compare(before, after))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog(rule: str = "") -> str:
    """규칙 목록(파일·화면·훅·캡션 + AI 글투)과 각 규칙이 무엇을 보는지. rule 을 주면 하나만.

    rule: 규칙 id (예: true-peak-over, tell-not-x-but-y).
    """
    rows = rules.catalog(rule)
    if not rows:
        return f"⚠️ 그런 규칙이 없습니다: {rule}"
    counts = rules.counts()
    lines = [
        f"규칙 {counts['total']}종 — 파일 {counts['file']} · 화면 {counts['safe']}"
        f" · 훅 {counts['hook']} · 캡션 {counts['copy']} (AI 글투 {len(tells.TELLS)}종 포함)"
    ]
    for row in rows:
        lines.append(f"[{row.severity}] {row.id} — {row.title}")
        lines.append(f"    {row.doc}")
    return "\n".join(lines)


@mcp.tool()
def overview() -> str:
    """이 서버가 무엇을 하고 무엇을 판정하지 않는지."""
    return OVERVIEW


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="publish-guard MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="영상 기준 디렉터리 (PUBLISH_GUARD_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["PUBLISH_GUARD_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
