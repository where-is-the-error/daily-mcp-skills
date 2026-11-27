"""실측 — 저장소의 릴스·캡션, 그리고 공개 표본 영상을 한 번에 잰다.

    python tools/audit.py                     # ../day-*/reels-day*.mp4 와 캡션
    python tools/audit.py --public ~/samples  # 내려받은 공개 표본까지
    python tools/audit.py --json tools/audit-result.json

영상 파일은 저장소에 넣지 않는다. 잰 값만 남긴다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from publish_guard import check, probe  # noqa: E402
from publish_guard.caption import read_caption  # noqa: E402
from publish_guard.platforms import DEFAULT_PLATFORMS  # noqa: E402
from publish_guard.types import Report  # noqa: E402

MEDIA_HEADER = f"{'파일':28} {'길이':>7} {'해상도':>11} {'LUFS':>6} {'피크':>6} {'점수':>4} {'판정':<6} 걸린 규칙"


def _short(path: str, width: int = 28) -> str:
    name = Path(path).name
    return name if len(name) <= width else name[: width - 1] + "…"


def _fmt(value, digits: int = 1, plus: bool = False) -> str:
    if value is None:
        return "?"
    if value == float("-inf"):
        return "-inf"
    return f"{value:+.{digits}f}" if plus else f"{value:.{digits}f}"


def audit_media(paths: list[str]) -> list[dict]:
    rows = []
    for path in paths:
        try:
            media = probe.probe(path)
        except probe.ProbeError as exc:
            rows.append({"file": path, "error": str(exc)})
            continue
        report = check.publish_check(media=media, platforms=DEFAULT_PLATFORMS)
        rows.append(
            {
                "file": path,
                "duration_s": media.duration_s,
                "width": media.width,
                "height": media.height,
                "fps": media.fps,
                "video_codec": media.video_codec,
                "audio_codec": media.audio_codec,
                "lufs": media.loudness_lufs,
                "peak": media.true_peak_dbtp,
                "size_mb": round(media.size_mb, 2),
                "score": report.score(),
                "verdict": report.verdict(),
                "rules": [f.rule for f in report.ordered() if f.weight > 0],
                "blocking": [f.rule for f in report.ordered() if f.severity == "block"],
            }
        )
    return rows


def audit_captions(paths: list[str], section: str = "auto") -> list[dict]:
    rows = []
    for path in paths:
        facts = read_caption(path=path, section=section)
        report = Report(
            media=None,
            caption=facts,
            platforms=DEFAULT_PLATFORMS,
            findings=check.check_caption(facts, DEFAULT_PLATFORMS),
            created_at=check._now(),
        )
        rows.append(
            {
                "file": path,
                "chars": facts.chars,
                "hashtags": facts.hashtag_count,
                "hook_chars": facts.hook_chars_nospace,
                "language": facts.language,
                "score": report.score(),
                "verdict": report.verdict(),
                "rules": [f.rule for f in report.ordered() if f.weight > 0],
                "tells": [f.rule for f in report.findings if f.rule.startswith("tell-") and f.weight > 0],
            }
        )
    return rows


def print_media(rows: list[dict]) -> None:
    print(f"미디어 {len(rows)}편")
    print(MEDIA_HEADER)
    for row in rows:
        if "error" in row:
            print(f"{_short(row['file']):28} ERROR {row['error'][:60]}")
            continue
        rules = ",".join(row["blocking"]) or (row["rules"][0] if row["rules"] else "-")
        print(
            f"{_short(row['file']):28} {row['duration_s']:6.2f}s "
            f"{row['width']}x{row['height']:<6} {_fmt(row['lufs']):>6} {_fmt(row['peak'], 1, True):>6} "
            f"{row['score']:>4} {row['verdict']:<6} {rules[:48]}"
        )


def print_captions(rows: list[dict]) -> None:
    print(f"\n캡션 {len(rows)}편")
    print(f"{'파일':34} {'글자':>6} {'태그':>4} {'훅':>4} {'점수':>4} {'판정':<10} 걸린 규칙")
    for row in rows:
        rules = ",".join(row["rules"][:3]) or "-"
        print(
            f"{_short(row['file'], 34):34} {row['chars']:>6} {row['hashtags']:>4} {row['hook_chars']:>4} "
            f"{row['score']:>4} {row['verdict']:<10} {rules[:52]}"
        )


def summarise(media: list[dict], captions: list[dict]) -> dict:
    ok = [row for row in media if "error" not in row]
    return {
        "media_count": len(ok),
        "over_peak": sum(1 for row in ok if row["peak"] is not None and row["peak"] > -1.0),
        "hot": sum(1 for row in ok if row["lufs"] is not None and row["lufs"] > -12.5),
        "quiet": sum(1 for row in ok if row["lufs"] is not None and row["lufs"] < -15.5 and row["lufs"] != float("-inf")),
        "no_audio": sum(1 for row in ok if not row["audio_codec"]),
        "landscape": sum(1 for row in ok if row["width"] > row["height"]),
        "over_2200": sum(1 for row in captions if row["chars"] > 2200),
        "hook_over_18": sum(1 for row in captions if row["hook_chars"] > 18),
        "with_tells": sum(1 for row in captions if row["tells"]),
        "caption_count": len(captions),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="릴스·캡션 실측")
    parser.add_argument("--repo", default=str(ROOT), help="daily-mcp-skills 루트")
    parser.add_argument("--media", nargs="*", default=None, help="영상 경로 (기본: ../day-*/reels-day*.mp4)")
    parser.add_argument("--captions", nargs="*", default=None, help="캡션 경로 (기본: ../day-*/instagram-caption.md)")
    parser.add_argument("--public", nargs="*", default=None, help="공개 표본 영상 경로")
    parser.add_argument("--section", default="auto", help="캡션 파일의 ## 구역 (auto)")
    parser.add_argument("--json", default="", help="결과 JSON 저장 경로")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    media_paths = args.media or sorted(str(p) for p in root.parent.glob("day-*/reels-day*.mp4"))
    caption_paths = args.captions or sorted(str(p) for p in root.parent.glob("day-*/instagram-caption.md"))

    media_rows = audit_media(media_paths)
    caption_rows = audit_captions(caption_paths, args.section)

    print_media(media_rows)
    print_captions(caption_rows)
    if args.public:
        public_rows = audit_media(args.public)
        print("\n공개 표본")
        print(MEDIA_HEADER)
        for row in public_rows:
            if "error" in row:
                print(f"{_short(row['file']):28} ERROR {row['error'][:60]}")
                continue
            rules = ",".join(row["blocking"]) or (row["rules"][0] if row["rules"] else "-")
            print(
                f"{_short(row['file']):28} {row['duration_s']:6.2f}s {row['width']}x{row['height']:<6} "
                f"{_fmt(row['lufs']):>6} {_fmt(row['peak'], 1, True):>6} {row['score']:>4} "
                f"{row['verdict']:<6} {rules[:48]}"
            )
        media_rows += public_rows

    summary = summarise(media_rows, caption_rows)
    print("\n요약")
    print(
        f"  영상: 피크 초과 {summary['over_peak']}/{summary['media_count']}"
        f" · 목표보다 큼 {summary['hot']} · 목표보다 작음 {summary['quiet']}"
        f" · 오디오 없음 {summary['no_audio']} · 가로 {summary['landscape']}"
    )
    print(
        f"  캡션: 2,200자 초과 {summary['over_2200']}/{summary['caption_count']}"
        f" · 훅 18자 초과 {summary['hook_over_18']} · AI 신호 있는 편 {summary['with_tells']}"
    )

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"media": media_rows, "captions": caption_rows, "summary": summary},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
