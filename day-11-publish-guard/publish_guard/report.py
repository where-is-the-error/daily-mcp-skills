"""보고서 — 사람이 읽는 줄과 기계가 읽는 JSON.

모든 출력 끝에는 이 도구가 판정하지 않은 것을 붙인다.
"""

from __future__ import annotations

import json
from typing import Any

from .platforms import AS_OF, PROFILES
from .types import CATEGORY_LABEL, SEVERITY_LABEL, CaptionFacts, Finding, MediaFacts, Report

VERDICT_LABEL = {"pass": "통과", "revise": "수정 후 발행", "hold": "보류"}
MARK = {"block": "✕", "warn": "!", "note": "·"}
ORIENTATION = {"vertical": "세로", "square": "정사각", "landscape": "가로"}

LIMITS = (
    "판정하지 않음: 영상 안에 실제로 그려진 글자·로고의 위치(선언된 상자만 봄) · 사람이 느끼는 재미·"
    "편집 품질 · 소리의 내용(음성 인식 없음) · 플랫폼 심사·저작권 · 조회수. "
    f"규격은 {AS_OF} 에 확인한 공개 문서 기준이고 바뀔 수 있다."
)


def verdict_text(value: str) -> str:
    return VERDICT_LABEL.get(value, value)


def media_lines(media: MediaFacts) -> list[str]:
    lines = [f"파일: {media.path}"]
    fps = f"{media.fps:.2f}fps" if media.fps is not None else "?fps"
    lines.append(
        f"  {media.duration_s:.2f}초 · {media.width}×{media.height} ({ORIENTATION.get(media.orientation, media.orientation)}) · {fps}"
        f" · {media.video_codec or '?'}"
        + (f" {media.video_profile}" if media.video_profile else "")
        + f" · {media.pix_fmt or '?'}"
    )
    audio = (
        f"{media.audio_codec} {media.audio_sample_rate or '?'}Hz {media.audio_channels or '?'}ch"
        if media.has_audio
        else "오디오 없음"
    )
    lines.append(
        f"  오디오: {audio} · {media.size_mb:.2f}MB · {media.total_bitrate_kbps}kbps"
        + (f" · 비디오 {media.video_bitrate_kbps}kbps" if media.video_bitrate_kbps else "")
    )
    if media.loudness_lufs is None:
        lines.append("  소리: 음량을 재지 않았다")
    else:
        peak = "?" if media.true_peak_dbtp is None else f"{media.true_peak_dbtp:+.1f} dBTP"
        lines.append(
            f"  소리: {media.loudness_lufs:.1f} LUFS (목표 -14.0 ±1.5) · 트루피크 {peak} (한계 -1.0)"
        )
    if media.head_silence_s is not None or media.tail_silence_s is not None:
        lines.append(
            f"  무음: 앞 {media.head_silence_s or 0:.2f}초 · 뒤 {media.tail_silence_s or 0:.2f}초"
        )
    if media.rotation:
        lines.append(f"  회전 메타데이터: {media.rotation}°")
    if media.probed_with:
        tool = media.probed_with.split(" · ")[0]
        lines.append(f"  측정: {tool} · {media.measured_at or '-'}")
    return lines


def caption_lines(caption: CaptionFacts) -> list[str]:
    return [
        f"캡션: {caption.hook_chars_nospace}자 훅 · {caption.chars}자 전체 · 해시태그 {caption.hashtag_count}개"
        f" · 멘션 {len(caption.mentions)} · 링크 {len(caption.links)} · {caption.language}",
        f"  첫 줄: {caption.first_line[:80]}",
    ]


def finding_lines(findings: list[Finding], show_command: bool = True) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        where = f" [{', '.join(PROFILES[p].label for p in finding.platforms)}]" if finding.platforms else ""
        lines.append(
            f"  {MARK[finding.severity]} {finding.rule} ({CATEGORY_LABEL[finding.category]})"
            f" — {finding.title}{where}"
        )
        lines.append(f"     {finding.message}")
        lines.append(f"     고치기: {finding.fix}")
        if show_command and finding.command:
            lines.append(f"     $ {finding.command}")
    return lines


def verdict_lines(report: Report) -> list[str]:
    counts = report.counts()
    score = report.score()
    verdict = report.verdict()
    lines = [
        f"판정: {verdict_text(verdict)} ({score}/100)",
        f"  막음 {counts['block']} · 주의 {counts['warn']} · 참고 {counts['note']}"
        f" · 상자 {report.boxes_checked}개",
    ]
    return lines


def fix_order(report: Report) -> list[Finding]:
    blocks = [f for f in report.ordered() if f.severity == "block"]
    warns = [f for f in report.ordered() if f.severity == "warn"]
    return blocks + warns


def fix_lines(report: Report) -> list[str]:
    order = fix_order(report)
    if not order:
        return ["고칠 것 없음 — 이대로 올려도 된다."]
    lines = ["고치기 순서"]
    for index, finding in enumerate(order, start=1):
        lines.append(f" {index}. [{SEVERITY_LABEL[finding.severity]}] {finding.rule} — {finding.fix}")
        if finding.command:
            lines.append(f"      $ {finding.command}")
    return lines


def platform_lines(report: Report) -> list[str]:
    lines = ["플랫폼별"]
    for verdict in report.platform_verdicts():
        lines.append(
            f"  {verdict.label}: {verdict_text(verdict.verdict)} ({verdict.score}/100)"
            + (f" · 막음 {', '.join(verdict.blocking)}" if verdict.blocking else "")
            + (f" · 주의 {', '.join(verdict.warnings)}" if verdict.warnings else "")
        )
    return lines


def publish_report(report: Report) -> str:
    lines: list[str] = []
    lines.append("발행 전 검사 — " + (report.media.path if report.media else "캡션만"))
    if report.media:
        lines.extend(media_lines(report.media))
    if report.caption:
        lines.extend(caption_lines(report.caption))
    lines.append("")
    lines.extend(verdict_lines(report))
    lines.append("")
    if report.findings:
        lines.append("발견")
        lines.extend(finding_lines(report.ordered()))
        lines.append("")
    lines.extend(fix_lines(report))
    if len(report.platforms) > 1:
        lines.append("")
        lines.extend(platform_lines(report))
    lines.append("")
    lines.append(LIMITS)
    if report.ref:
        lines.append(f"보고서 ref: {report.ref}")
    return "\n".join(lines)


def compare_report(result: dict[str, Any]) -> str:
    before: Report = result["before"]
    after: Report = result["after"]
    lines = [
        f"↔ {before.score()} → {after.score()} "
        f"({verdict_text(before.verdict())} → {verdict_text(after.verdict())})",
        f"  고쳐진 것 {len(result['fixed'])} · 남은 것 {len(result['remaining'])}"
        f" · 새로 생긴 것 {len(result['added'])}",
    ]
    if result["fixed"]:
        lines.append("  고쳐짐: " + ", ".join(f.rule for f in result["fixed"][:12]))
    if result["remaining"]:
        lines.append("  남음: " + ", ".join(f.rule for f in result["remaining"][:12]))
    if result["added"]:
        lines.append("  새로 생김: " + ", ".join(f.rule for f in result["added"][:12]))

    caption = result.get("caption") or {}
    if caption:
        lost_numbers = caption.get("numbers_lost") or []
        lost_tags = caption.get("hashtags_lost") or []
        lost_links = caption.get("links_lost") or []
        lines.append(
            f"  캡션: {caption['chars_before']}자 → {caption['chars_after']}자"
            f" · AI 신호 {caption['tells_before']} → {caption['tells_after']}"
        )
        lines.append(
            "  사실 보존: "
            + (
                "잃은 숫자·해시태그·링크 없음"
                if not (lost_numbers or lost_tags or lost_links)
                else "잃은 것 — 숫자 "
                + (", ".join(lost_numbers) or "없음")
                + " / 해시태그 "
                + (", ".join("#" + t for t in lost_tags) or "없음")
                + " / 링크 "
                + (", ".join(lost_links) or "없음")
            )
        )
    media = result.get("media") or {}
    if media:
        lines.append(
            f"  파일: {media['duration_before']:.2f} → {media['duration_after']:.2f}초"
            f" · {media['lufs_before'] if media['lufs_before'] is not None else '?'}"
            f" → {media['lufs_after'] if media['lufs_after'] is not None else '?'} LUFS"
            f" · {media['peak_before'] if media['peak_before'] is not None else '?'}"
            f" → {media['peak_after'] if media['peak_after'] is not None else '?'} dBTP"
        )
    lines.append("")
    lines.append(LIMITS)
    return "\n".join(lines)


def to_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
