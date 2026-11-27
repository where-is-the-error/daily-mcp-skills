"""시연 — 어제 편(day-10)과 오늘 편(day-11)을 같은 도구로 재고, 캡션 고치기에서 잃은 사실을 보여준다.

    python tools/demo.py
    python tools/demo.py --out tools/demo-output.txt

영상은 고치지 않는다. 재고 비교하기만 한다. (loudnorm 시연은 README 에 명령으로 적혀 있다.)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from publish_guard import check, probe, report  # noqa: E402
from publish_guard.caption import read_caption  # noqa: E402
from publish_guard.platforms import DEFAULT_PLATFORMS  # noqa: E402
from publish_guard.safearea import parse_boxes  # noqa: E402


def _check(video: Path, caption: Path, boxes: Path | None = None):
    media = probe.probe(video)
    facts = read_caption(path=str(caption), section="auto")
    box_list = parse_boxes(json.dumps(json.loads(boxes.read_text(encoding="utf-8")))) if boxes else []
    return check.publish_check(
        media=media,
        caption=facts,
        platforms=DEFAULT_PLATFORMS,
        boxes=box_list,
        zone_set="house",
    )


def _line(label: str, result) -> str:
    counts = result.counts()
    blocking = [f.rule for f in result.ordered() if f.severity == "block"]
    return (
        f"{label}: {result.score():>3}/100 · {report.verdict_text(result.verdict()):<7} "
        f"막음 {counts['block']} · 주의 {counts['warn']} · 참고 {counts['note']} "
        f"{', '.join(blocking[:4]) if blocking else ''}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="어제 편 vs 오늘 편")
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    lines: list[str] = []

    yesterday_dir = root.parent / "day-10-test-radar"
    yesterday = _check(yesterday_dir / "reels-day10.mp4", yesterday_dir / "instagram-caption.md")
    today = _check(root / "reels-day11.mp4", root / "instagram-caption.md", root / "reels" / "boxes-day11.json")

    lines.append("발행 전 검사 — 어제 편 vs 오늘 편")
    lines.append("")
    lines.append(_line("Day 10 (test-radar)", yesterday))
    lines.append(_line("Day 11 (publish-guard)", today))
    lines.append("")
    lines.append("Day 10 에서 걸린 것")
    for finding in yesterday.ordered():
        if finding.severity == "block":
            lines.append(f"  ✕ {finding.rule} — {finding.message}")
    lines.append("")
    lines.append("Day 11 파일·화면")
    media = today.media
    lines.append(
        f"  {media.duration_s:.2f}초 · {media.width}×{media.height} · {media.fps:.0f}fps · "
        f"{media.video_codec} {media.video_profile} · {media.audio_codec} {media.audio_sample_rate}Hz "
        f"{media.audio_channels}ch · {media.size_mb:.2f}MB"
    )
    lines.append(
        f"  {media.loudness_lufs:.1f} LUFS · {media.true_peak_dbtp:+.1f} dBTP · "
        f"앞뒤 무음 {media.head_silence_s:.2f}/{media.tail_silence_s:.2f}초 · 상자 {today.boxes_checked}개"
    )
    lines.append("")

    # 캡션 고치기 — 같은 사실을 남기는지
    before = check.publish_check(
        caption=read_caption(path=str(root / "examples" / "caption-before.txt")),
        platforms=DEFAULT_PLATFORMS,
    )
    after = check.publish_check(
        caption=read_caption(path=str(root / "examples" / "caption-after.txt")),
        platforms=DEFAULT_PLATFORMS,
    )
    comparison = check.compare(before, after)
    lines.append("캡션 고치기 — examples/caption-before.txt → caption-after.txt")
    lines.append(_line("  전", before))
    lines.append(_line("  후", after))
    caption = comparison["caption"]
    lines.append(
        f"  숫자 잃음: {caption['numbers_lost'] or '없음'} · 해시태그 잃음: {caption['hashtags_lost'] or '없음'}"
    )
    lines.append(f"  AI 신호 {caption['tells_before']} → {caption['tells_after']}")
    lines.append("")
    lines.append(report.LIMITS)

    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(
            json.dumps(
                {
                    "yesterday": yesterday.to_dict(),
                    "today": today.to_dict(),
                    "caption_compare": {
                        "score_before": comparison["score_before"],
                        "score_after": comparison["score_after"],
                        "caption": comparison["caption"],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
