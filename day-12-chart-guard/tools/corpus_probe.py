#!/usr/bin/env python3
"""실제 공개 Vega-Lite 스펙 표본 실측 — 저장소에 넣지 않고 읽기만 한다.

    python3 tools/corpus_probe.py --dir /path/to/vega-lite/examples/specs --limit 400

무엇을 재나
· 파싱: 읽힌 스펙 / 읽지 못한 스펙(모르는 mark, 데이터 없음)
· 판정: 규칙별 적중 수, 판정 분포(통과/주의/보류)
· 거짓 양성 점검: 축 하한을 0으로 밝힌 스펙에서 '잘린 축' 경고가 나오는가(나오면 버그)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chart_guard import check, normalize  # noqa: E402


def probe(directory: Path, limit: int | None, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    files = sorted(directory.rglob("*.json"))
    if limit:
        files = files[:limit]
    findings: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    errors: list[dict] = []
    skipped: Counter[str] = Counter()
    false_positive = 0
    checked = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            chart = normalize.normalize(text)
        except Exception as exc:
            errors.append({"file": str(path.relative_to(directory)), "error": str(exc)[:120]})
            continue
        checked += 1
        kinds[chart.kind] += 1
        report = check.run(chart)
        if exclude:
            report = check.score(
                [f for f in report.findings if f.rule_id not in exclude],
                chart=chart,
                skipped=report.skipped,
            )
        verdicts[report.verdict] += 1
        for finding in report.findings:
            findings[finding.rule_id] += 1
        for item in report.skipped:
            skipped[item.split(" — ")[0][:60]] += 1
        if "bar-truncated-baseline" in report.rule_ids() and chart.y.min == 0:
            false_positive += 1
    return {
        "files": len(files),
        "checked": checked,
        "errors": len(errors),
        "error_sample": errors[:12],
        "kinds": dict(kinds.most_common()),
        "verdicts": dict(verdicts),
        "findings": dict(findings.most_common()),
        "skipped": dict(skipped.most_common(10)),
        "false_positive_truncated_with_zero": false_positive,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exclude", default="", help="빼고 집계할 규칙 id (쉼표)")
    args = parser.parse_args(argv)
    exclude = {item.strip() for item in args.exclude.split(",") if item.strip()}
    result = probe(Path(args.dir), args.limit, exclude)
    result["excluded"] = sorted(exclude)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"파일 {result['files']} · 읽음 {result['checked']} · 읽지 못함 {result['errors']}")
    print(f"판정: {result['verdicts']}")
    print(f"형식: {result['kinds']}")
    print("규칙 적중:")
    for rule, count in result["findings"].items():
        print(f"  {count:4d}  {rule}")
    print("건너뛴 이유:")
    for reason, count in result["skipped"].items():
        print(f"  {count:4d}  {reason}")
    print(f"거짓 양성(0에서 시작했는데 잘린 축): {result['false_positive_truncated_with_zero']}")
    if result["error_sample"]:
        print("읽지 못한 예:")
        for item in result["error_sample"][:5]:
            print(f"  {item['file']}: {item['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
