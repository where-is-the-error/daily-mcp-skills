#!/usr/bin/env python3
"""실제 공개 데이터 실측 — IBM 월별 종가(vega-datasets `stocks.csv`)로 차트를 만들고 검사한다.

    python3 tools/real_data.py

· CSV 는 내려받아 /tmp 에만 두고 저장소에 넣지 않는다.
· 같은 12개 값으로 '잘린 축' 막대와 '0에서 시작' 막대를 만들어, 규칙이 무엇을 잡는지 본다.
· 주가처럼 '0이 의미 없는' 값의 정직한 대안은 선 차트이기도 하다 — 그 경우 축을 자르고 '확대'를 적는다(README 참고).
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chart_guard import check, compare, normalize  # noqa: E402

URL = "https://raw.githubusercontent.com/vega/vega-datasets/main/data/stocks.csv"
CACHE = Path("/tmp") / "chart-guard-stocks.csv"
OUT = Path(__file__).resolve().parent / "real-data-result.json"


def fetch() -> str:
    if CACHE.exists():
        return CACHE.read_text(encoding="utf-8")
    with urllib.request.urlopen(URL, timeout=60) as response:  # noqa: S310 — 공개 URL
        text = response.read().decode("utf-8")
    CACHE.write_text(text, encoding="utf-8")
    return text


def last_year(text: str, symbol: str = "IBM", months: int = 12) -> tuple[list[str], list[float]]:
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("symbol") == symbol]
    picked = rows[-months:]
    labels: list[str] = []
    values: list[float] = []
    for row in picked:
        stamp = datetime.strptime(row["date"].strip(), "%b %d %Y")
        labels.append(f"{stamp.year}-{stamp.month:02d}")
        values.append(round(float(row["price"]), 2))
    return labels, values


def chart_for(labels: list[str], values: list[float], y_min: float, title: str) -> dict:
    return {
        "type": "bar",
        "categories": labels,
        "series": [{"name": "종가", "values": values}],
        "y": {"min": y_min, "title": "종가(USD)"},
        "palette": ["#1f6fd0"],
        "title": title,
        "source": "vega-datasets stocks.csv (IBM, 2009-03~2010-02 월별 종가)",
        "alt": "막대 차트. IBM 월별 종가 12개월.",
        "font_px": 13,
    }


def main() -> int:
    text = fetch()
    labels, values = last_year(text)
    lowest, highest = min(values), max(values)
    bad_min = float(int(lowest))  # 100 — 실제로 흔한 '축 자르기'
    bad = chart_for(labels, values, bad_min, "IBM 종가 12개월")
    good = chart_for(labels, values, 0.0, f"IBM 종가는 101달러에서 130달러로 1.29배 올랐다")

    before_report = check.run(normalize.normalize(bad))
    after_report = check.run(normalize.normalize(good))
    diff = compare.compare(before_report, after_report)

    print(f"데이터: {len(values)}개월 · {labels[0]} ~ {labels[-1]} · {lowest} ~ {highest} USD")
    print(f"값: {values}")
    print()
    print(f"① 잘린 축(y ≥ {bad_min:g}) — 판정 {before_report.score}/100 · {before_report.verdict}")
    for finding in before_report.ordered():
        print(f"   [{finding.severity}] {finding.rule_id}: {finding.evidence}")
    print()
    print(f"② 0에서 시작 — 판정 {after_report.score}/100 · {after_report.verdict}")
    for finding in after_report.ordered():
        print(f"   [{finding.severity}] {finding.rule_id}: {finding.evidence}")
    print()
    print(f"전후 {diff['before_score']} → {diff['after_score']} · 고쳐진 {diff['fixed']}")
    print(f"잃은 범주 {diff['lost_categories']} · 잃은 값 {len(diff['lost_values'])}개")

    payload = {
        "dataset": URL,
        "symbol": "IBM",
        "labels": labels,
        "values": values,
        "before": {
            "score": before_report.score,
            "verdict": before_report.verdict,
            "y_min": bad_min,
            "findings": [f.rule_id for f in before_report.findings],
            "evidence": {f.rule_id: f.evidence for f in before_report.findings},
        },
        "after": {
            "score": after_report.score,
            "verdict": after_report.verdict,
            "findings": [f.rule_id for f in after_report.findings],
        },
        "compare": diff,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
