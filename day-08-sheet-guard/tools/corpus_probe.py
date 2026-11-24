#!/usr/bin/env python3
"""실제 공개 데이터로 돌려 본 결과를 잰다.

    python3 tools/corpus_probe.py                 # 내려받아서 잰다
    python3 tools/corpus_probe.py 파일1 파일2     # 이미 받은 파일로 잰다

파일은 **저장소에 넣지 않는다**(내려받아 분석만 하고 버린다). 출처는 아래 SOURCES.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sheet_guard.apply import apply_plan  # noqa: E402
from sheet_guard.compare import compare  # noqa: E402
from sheet_guard.plan import build_plan  # noqa: E402
from sheet_guard.rules import check, counts  # noqa: E402
from sheet_guard.table import load_table  # noqa: E402

SOURCES = {
    "mois_age.csv": (
        "행정안전부 주민등록 연령별 인구현황(2026-01~06)",
        "https://raw.githubusercontent.com/chanho12/BC_Context/main/"
        "data/%EC%99%B8%EB%B6%80%EB%8D%B0%EC%9D%B4%ED%84%B0/%EB%B3%B4%EC%A1%B0_%EC%9B%90%EB%B3%B8/"
        "mois/202601_202606_age_population.csv",
    ),
    "living.csv": (
        "행정안전부 주민등록 지역별 생활인구(2026-01~03)",
        "https://raw.githubusercontent.com/chanho12/BC_Context/main/"
        "data/%EC%99%B8%EB%B6%80%EB%8D%B0%EC%9D%B4%ED%84%B0/%EB%B3%B4%EC%A1%B0_%EC%9B%90%EB%B3%B8/"
        "mois_living_population/202601_202603_living_population_by_region.csv",
    ),
    "examples/raw_population.csv": ("이 저장소의 예제(공공데이터 흉내, 오염 표시용)", ""),
}


def fetch(name: str, url: str, folder: Path) -> Path:
    target = folder / name
    if target.exists():
        return target
    if not url:
        return Path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, target)
    return target


def probe(path: Path, label: str) -> dict:
    size = path.stat().st_size
    t0 = time.perf_counter()
    table = load_table(path)
    read_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    findings = check(table)
    rules_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    plan = build_plan(table, findings)
    applied = apply_plan(table, plan)
    apply_ms = (time.perf_counter() - t0) * 1000

    diff = compare(table, applied.table)
    tally = counts(findings)
    cells = len(table.rows) * table.width

    return {
        "label": label,
        "file": path.name,
        "bytes": size,
        "encoding": table.encoding,
        "confidence": table.encoding_confidence,
        "rows": len(table.data_rows),
        "cols": table.width,
        "cells": cells,
        "read_ms": read_ms,
        "rules_ms": rules_ms,
        "apply_ms": apply_ms,
        "error": tally["error"],
        "warn": tally["warn"],
        "info": tally["info"],
        "top_rules": [f"{f.rule}×{max(1, f.count)}" for f in findings[:4]],
        "plan_steps": len(plan.actions),
        "changes": len(applied.changes),
        "dropped": len(applied.dropped),
        "quarantined": len(applied.quarantined),
        "rows_after": len(applied.table.rows),
        "values_lost": len(diff.values_lost),
    }


def main(argv: list[str]) -> int:
    folder = Path(tempfile.mkdtemp(prefix="sheet-guard-corpus-"))
    rows = []
    try:
        paths = [Path(arg) for arg in argv[1:]]
        if paths:
            for path in paths:
                rows.append(probe(path, path.name))
        else:
            for name, (label, url) in SOURCES.items():
                path = fetch(name, url, folder)
                if not path.exists():
                    print(f"건너뜀: {name} (없음)")
                    continue
                rows.append(probe(path, label))
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    header = (f"{'파일':<26} {'인코딩':<10} {'행×열':>12} {'읽기':>8} {'규칙':>8} "
              f"{'적용':>8} {'치명':>4} {'주의':>4} {'바뀐칸':>7} {'잃은값':>6}")
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['file'][:26]:<26} {row['encoding']:<10} "
              f"{row['rows']:>5}×{row['cols']:<6} {row['read_ms']:>6.0f}ms {row['rules_ms']:>6.0f}ms "
              f"{row['apply_ms']:>6.0f}ms {row['error']:>4} {row['warn']:>4} "
              f"{row['changes']:>7} {row['values_lost']:>6}")
    for row in rows:
        print(f"\n{row['file']} — {row['label']}")
        print(f"  {row['bytes']:,}바이트 · {row['cells']:,}칸 · 인코딩 {row['encoding']}"
              f"(확신 {row['confidence']:.2f})")
        print(f"  판정 치명 {row['error']} · 주의 {row['warn']} · 참고 {row['info']} / 상위: {', '.join(row['top_rules'])}")
        print(f"  계획 {row['plan_steps']}단계 → 바뀐 칸 {row['changes']:,} · 뺀 행 {row['dropped']} · "
              f"격리 {row['quarantined']} · 남은 행 {row['rows_after']} · 값 손실 {row['values_lost']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
