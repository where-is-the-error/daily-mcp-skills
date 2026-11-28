#!/usr/bin/env python3
"""예제 before → after 실측 — 검사·고치기·대체 텍스트·전후 비교를 한 번에.

    python3 tools/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chart_guard import alttext, check, compare, fix, normalize, report  # noqa: E402

EXAMPLES = ROOT / "examples"
OUT_TXT = Path(__file__).resolve().parent / "demo-output.txt"
OUT_JSON = Path(__file__).resolve().parent / "demo-output.json"


def load(name: str):
    return normalize.normalize((EXAMPLES / name).read_text(encoding="utf-8"))


def main() -> int:
    lines: list[str] = []
    payload: dict = {}

    before = load("before.json")
    before_report = check.run(before)
    lines.append("=" * 72)
    lines.append("① examples/before.json — 그대로 올리면")
    lines.append("=" * 72)
    lines.append(check.summary_line(before_report))
    for finding in before_report.ordered():
        lines.append(f"  [{finding.severity}] {finding.rule_id} — {finding.title}")
        lines.append(f"      본 것: {finding.evidence}")
    lines.append("")
    lines.append("왜곡 계산")
    lines.extend("  " + line for line in report.distortion_lines(before))

    corrected = fix.corrected(before)
    corrected_chart = normalize.normalize(corrected)
    corrected_report = check.run(corrected_chart)
    lines.append("")
    lines.append("=" * 72)
    lines.append("② fix_plan 이 만든 스펙 — 같은 값, 고친 축")
    lines.append("=" * 72)
    lines.append(check.summary_line(corrected_report))
    lines.append("고친 것: " + ", ".join(item for item in fix.explain_difference(before)) if before.kind else "")

    after = load("after.json")
    after_report = check.run(after)
    diff = compare.compare(before_report, after_report)
    lines.append("")
    lines.append("=" * 72)
    lines.append("③ examples/after.json — 손으로 고친 최종본")
    lines.append("=" * 72)
    lines.append(check.summary_line(after_report))
    lines.append(f"전후 {diff['before_score']} → {diff['after_score']} ({diff['delta']:+d})")
    lines.append("고쳐진 규칙: " + ", ".join(diff["fixed"]))
    lines.append(f"잃은 범주 {diff['lost_categories']} · 잃은 값 {len(diff['lost_values'])}개")
    lines.append("")
    lines.append("대체 텍스트 (after)")
    lines.append("  " + alttext.short(after))
    lines.append("")
    lines.append("데이터 표 (after)")
    lines.extend("  " + line for line in alttext.table(after).splitlines())

    pie = load("pie-before.json")
    pie_report = check.run(pie)
    pie_fixed = fix.corrected(pie)
    lines.append("")
    lines.append("=" * 72)
    lines.append("④ examples/pie-before.json — 원 9조각 → 상위 4 + 기타")
    lines.append("=" * 72)
    lines.append(check.summary_line(pie_report))
    lines.append(f"고친 뒤 범주 {len(pie_fixed['categories'])}개: {', '.join(pie_fixed['categories'])}")
    lines.append(f"값 합계 {sum(pie.series[0].values)} → {sum(pie_fixed['series'][0]['values'])} (같아야 한다)")

    text = "\n".join(lines)
    OUT_TXT.write_text(text, encoding="utf-8")
    print(text)

    payload = {
        "before": {"score": before_report.score, "verdict": before_report.verdict,
                   "findings": [f.rule_id for f in before_report.findings]},
        "corrected": {"score": corrected_report.score, "verdict": corrected_report.verdict,
                      "findings": [f.rule_id for f in corrected_report.findings]},
        "after": {"score": after_report.score, "verdict": after_report.verdict,
                  "findings": [f.rule_id for f in after_report.findings]},
        "compare": diff,
        "pie": {"score": pie_report.score, "categories_after": pie_fixed["categories"],
                "sum_before": sum(pie.series[0].values), "sum_after": sum(pie_fixed["series"][0]["values"])},
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(OUT_TXT)
    print(OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
