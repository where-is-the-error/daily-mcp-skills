"""명령줄 — 영상과 캡션을 한 번에 검사한다.

    publish-guard check reels.mp4 --caption instagram-caption.md --boxes boxes.json
    publish-guard check reels.mp4 --caption caption.md --json > report.json
    publish-guard compare before.json after.json
    publish-guard rules

종료 코드: 0 통과 · 1 사용 오류 · 2 보류 · 3 수정 후 발행.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import check, probe, report, rules, safearea
from .caption import read_caption
from .platforms import PlatformError, parse_platforms
from .types import Report

EXIT = {"pass": 0, "hold": 2, "revise": 3}


def _boxes(value: str) -> list[safearea.Box]:
    if not value:
        return []
    path = Path(value).expanduser()
    payload = path.read_text(encoding="utf-8") if path.exists() else value
    return safearea.parse_boxes(payload)


def _check(args) -> int:
    media = probe.probe(args.video, measure_audio=not args.no_measure) if args.video else None
    if args.caption:
        caption_path = Path(args.caption).expanduser()
        text = caption_path.read_text(encoding="utf-8") if caption_path.exists() else args.caption
        caption = read_caption(text=text, hook=args.hook or "", section=getattr(args, "section", ""))
    elif args.hook:
        caption = read_caption(text="", hook=args.hook)
    else:
        caption = None
    if media is None and caption is None:
        raise SystemExit("--caption 또는 --hook 또는 영상 경로가 필요합니다")
    result = check.publish_check(
        media=media,
        caption=caption,
        platforms=parse_platforms(args.platforms),
        boxes=_boxes(args.boxes),
        keyword=args.keyword,
        zone_set=args.zone_set,
    )
    if args.json:
        text = report.to_json(result)
        print(text)
        if args.save:
            Path(args.save).write_text(text, encoding="utf-8")
    else:
        print(report.publish_report(result))
        if args.save:
            Path(args.save).write_text(report.to_json(result), encoding="utf-8")
    return EXIT[result.verdict()]


def _media(args) -> int:
    facts = probe.probe(args.video, measure_audio=not args.no_measure)
    if args.json:
        print(json.dumps(facts.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("\n".join(report.media_lines(facts)))
    return 0


def _caption(args) -> int:
    path = Path(args.caption).expanduser()
    text = path.read_text(encoding="utf-8") if path.exists() else args.caption
    facts = read_caption(text=text, hook=args.hook or "", section=getattr(args, "section", ""))
    findings = check.check_caption(facts, parse_platforms(args.platforms), args.keyword)
    result = Report(media=None, caption=facts, platforms=parse_platforms(args.platforms), findings=findings)
    if args.json:
        print(report.to_json(result))
    else:
        print("\n".join(report.caption_lines(facts)))
        print("")
        print("\n".join(report.verdict_lines(result)))
        print("")
        print("\n".join(report.finding_lines(result.ordered(), show_command=False)) or "걸린 것 없음.")
        print("")
        print(report.LIMITS)
    return EXIT[result.verdict()]


def _compare(args) -> int:
    before = Report.from_dict(json.loads(Path(args.before).read_text(encoding="utf-8")))
    after = Report.from_dict(json.loads(Path(args.after).read_text(encoding="utf-8")))
    print(report.compare_report(check.compare(before, after)))
    return 0


def _rules(args) -> int:
    rows = rules.catalog(args.rule)
    if args.json:
        print(json.dumps([row.__dict__ for row in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"그런 규칙이 없습니다: {args.rule}")
        return 1
    counts = rules.counts()
    print(f"규칙 {counts['total']}종 — 파일 {counts['file']} · 화면 {counts['safe']} · 훅 {counts['hook']} · 캡션 {counts['copy']}")
    for row in rows:
        print(f"[{row.severity}] {row.id} — {row.title}")
        print(f"    {row.doc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-guard", description="올리기 전 파일과 글을 함께 검사한다")
    sub = parser.add_subparsers(dest="command")

    check_cmd = sub.add_parser("check", help="영상 + 캡션 발행 전 검사")
    check_cmd.add_argument("video", nargs="?", default="", help="영상 파일")
    check_cmd.add_argument("--caption", default="", help="캡션 파일 또는 본문")
    check_cmd.add_argument("--hook", default="", help="화면에 띄운 훅 문구")
    check_cmd.add_argument("--section", default="", help="캡션 파일의 ## 구역 이름 (auto = 본문/캡션 구역)")
    check_cmd.add_argument("--boxes", default="", help="문구 상자 JSON 파일 또는 JSON 문자열")
    check_cmd.add_argument("--platforms", default="all", help="all 또는 youtube_shorts,instagram_reels,tiktok")
    check_cmd.add_argument("--keyword", default="", help="캡션 앞부분에 있어야 할 검색어")
    check_cmd.add_argument("--zone-set", default="house", choices=["house", "platform", "both"])
    check_cmd.add_argument("--no-measure", action="store_true", help="음량·무음 측정 생략")
    check_cmd.add_argument("--json", action="store_true")
    check_cmd.add_argument("--save", default="", help="보고서 JSON 저장 경로")
    check_cmd.set_defaults(func=_check)

    media_cmd = sub.add_parser("media", help="파일 사실만")
    media_cmd.add_argument("video")
    media_cmd.add_argument("--no-measure", action="store_true")
    media_cmd.add_argument("--json", action="store_true")
    media_cmd.set_defaults(func=_media)

    caption_cmd = sub.add_parser("caption", help="캡션만")
    caption_cmd.add_argument("caption", help="캡션 파일 또는 본문")
    caption_cmd.add_argument("--hook", default="")
    caption_cmd.add_argument("--section", default="")
    caption_cmd.add_argument("--platforms", default="all")
    caption_cmd.add_argument("--keyword", default="")
    caption_cmd.add_argument("--json", action="store_true")
    caption_cmd.set_defaults(func=_caption)

    compare_cmd = sub.add_parser("compare", help="보고서 두 개 비교")
    compare_cmd.add_argument("before")
    compare_cmd.add_argument("after")
    compare_cmd.set_defaults(func=_compare)

    rules_cmd = sub.add_parser("rules", help="규칙 목록")
    rules_cmd.add_argument("rule", nargs="?", default="")
    rules_cmd.add_argument("--json", action="store_true")
    rules_cmd.set_defaults(func=_rules)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except (probe.ProbeError, safearea.BoxError, PlatformError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
