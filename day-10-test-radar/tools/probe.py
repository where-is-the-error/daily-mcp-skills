#!/usr/bin/env python3
"""실측 — 실제 저장소(day-09-log-triage, 304 테스트)에 변이를 넣고
'고른 테스트만 돌렸을 때 그 변이를 잡는가'를 확인한다.

    python3 tools/probe.py                 # 표 + 요약
    python3 tools/probe.py --json out.json # 기계가 읽는 결과
    python3 tools/probe.py --subject ../day-09-log-triage

각 변이마다 두 번 돌린다 — 선택한 테스트만 / 전체 테스트. 두 결과를 비교해서
'선택이 잡은 것'과 '전체도 못 잡은 것(테스트 구멍)'을 구분한다.
저장소는 임시 복사본에서만 고친다. 원본은 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from test_radar import diffparse                      # noqa: E402
from test_radar.graph import load                     # noqa: E402
from test_radar.risk import check as check_risks, counts as risk_counts  # noqa: E402
from test_radar.select import build as build_selection  # noqa: E402

DEFAULT_SUBJECT = ROOT.parent / "day-09-log-triage"

MUTANTS = [
    {
        "name": "levels: SEVERE → WARN",
        "path": "log_triage/levels.py",
        "old": '"error": "ERROR", "err": "ERROR", "severe": "ERROR", "e": "ERROR",',
        "new": '"error": "ERROR", "err": "ERROR", "severe": "WARN", "e": "ERROR",',
        "note": "공용 모듈 — 여러 테스트가 함께 본다",
    },
    {
        "name": "signature: 공백 접기 제거",
        "path": "log_triage/signature.py",
        "old": '    text = WS.sub(" ", text).strip()',
        "new": '    text = text.strip()',
        "note": "전체 실행으로도 안 잡히면 선택 실패가 아니라 테스트 구멍",
    },
    {
        "name": "rates: 오류를 CRITICAL 만 셈",
        "path": "log_triage/rates.py",
        "old": "        if record.is_error:\n            bucket.errors += 1",
        "new": '        if record.level == "CRITICAL":\n            bucket.errors += 1',
        "note": "",
    },
    {
        "name": "redact: Luhn 검사 무력화",
        "path": "log_triage/redact.py",
        "old": "    return checksum % 10 == 0",
        "new": "    return True",
        "note": "",
    },
    {
        "name": "stack: Python 안쪽 프레임 반대",
        "path": "log_triage/stack.py",
        "old": '        info.top_frame = frames[-1] if frames else ""',
        "new": '        info.top_frame = frames[0] if frames else ""',
        "note": "",
    },
]


def unified(path: str, old: str, new: str) -> str:
    body = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                     fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=3))
    if not body:
        return ""
    return f"diff --git a/{path} b/{path}\n" + "\n".join(body) + "\n"


def run_pytest(cwd: Path, files: list[str], timeout: int = 300) -> tuple[int, float, str]:
    command = [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", *files]
    started = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    elapsed = round(time.perf_counter() - started, 2)
    tail = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode, elapsed, tail[-1] if tail else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    parser.add_argument("--subject", default=str(DEFAULT_SUBJECT))
    args = parser.parse_args()

    subject = Path(args.subject).expanduser().resolve()
    if not subject.exists():
        print(f"⚠️ 실측 대상이 없습니다: {subject}")
        return 1

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="test-radar-probe-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(subject, work)
        repo = load(work)
        info = repo.summary()
        all_files = sorted(test.path for test in repo.tests.values() if not test.is_conftest)
        print(f"📦 {subject.name} · 모듈 {info['modules']} · 테스트 {info['tests']}파일/{info['test_items']}항목")
        code, seconds, tail = run_pytest(work, all_files)
        print(f"   전체 실행 기준: exit {code} · {seconds}s · {tail}")
        baseline = {"exit": code, "seconds": seconds}

        for mutant in MUTANTS:
            path = mutant["path"]
            original = (work / path).read_text(encoding="utf-8")
            if mutant["old"] not in original:
                print(f"⚠️ 변이 지점을 찾지 못함: {mutant['name']}")
                continue
            mutated = original.replace(mutant["old"], mutant["new"], 1)
            (work / path).write_text(mutated, encoding="utf-8")
            try:
                fresh = load(work)
                diff = diffparse.parse(unified(path, original, mutated))
                change_set = build_selection(fresh, diff)
                selected = change_set.selected_paths()
                risks = check_risks(change_set)
                sel_code, sel_seconds, sel_tail = run_pytest(work, selected)
                full_code, full_seconds, _ = run_pytest(work, all_files)
                rows.append({
                    "mutant": mutant["name"],
                    "note": mutant["note"],
                    "file": path,
                    "selected_files": len(selected),
                    "selected_items": change_set.selected_items(),
                    "total_items": change_set.total_items(),
                    "selected": selected,
                    "fallback": change_set.fallback,
                    "risks": risk_counts(risks),
                    "selected_exit": sel_code,
                    "full_exit": full_code,
                    "selected_seconds": sel_seconds,
                    "full_seconds": full_seconds,
                    "selected_tail": sel_tail,
                })
                verdict = ("선택이 잡음" if sel_code else
                           "전체도 못 잡음(테스트 구멍)" if full_code == 0 else
                           "선택은 놓침 · 전체가 잡음")
                print(f"   · {mutant['name']}: {len(selected)}파일/{change_set.selected_items()}항목"
                      f" · 선택 {sel_seconds}s(exit {sel_code}) · 전체 {full_seconds}s(exit {full_code})"
                      f" → {verdict}")
            finally:
                (work / path).write_text(original, encoding="utf-8")

    caught = sum(1 for row in rows if row["selected_exit"] != 0)
    summary = {
        "subject": str(subject),
        "tests": info["test_items"],
        "test_files": info["tests"],
        "baseline": baseline,
        "mutants": rows,
        "caught_by_selection": caught,
        "missed_by_selection_but_caught_by_full": sum(
            1 for row in rows if row["selected_exit"] == 0 and row["full_exit"] != 0),
        "survived_all": sum(1 for row in rows if row["selected_exit"] == 0 and row["full_exit"] == 0),
        "total_mutants": len(rows),
        "selection_seconds": round(sum(row["selected_seconds"] for row in rows), 2),
        "full_seconds": round(sum(row["full_seconds"] for row in rows), 2),
    }

    if rows:
        print()
        print(f"변이 {summary['total_mutants']}개 · 선택이 잡음 {caught} · 선택은 놓치고 전체가 잡음 "
              f"{summary['missed_by_selection_but_caught_by_full']} · 전체도 못 잡음 {summary['survived_all']}")
        print(f"선택 실행 합계 {summary['selection_seconds']}s vs 전체 실행 합계 {summary['full_seconds']}s")

    if args.json:
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
