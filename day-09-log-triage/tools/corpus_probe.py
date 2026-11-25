#!/usr/bin/env python3
"""실제 공개 로그로 측정한다 — 만든 예제가 아니라 남이 쓰는 로그.

Loghub(logpai/loghub)의 2,000줄 샘플을 내려받아 파싱률·서명 수·규칙 위반·속도를
센다. 내려받은 파일은 저장소에 넣지 않는다(`--cache` 기본값은 시스템 임시 폴더).

    python tools/corpus_probe.py                 # 표만
    python tools/corpus_probe.py --md            # README 에 붙일 마크다운
    python tools/corpus_probe.py --only HDFS,Apache
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from log_triage.parse import parse_text, decode_bytes          # noqa: E402
from log_triage.rates import analyze                            # noqa: E402
from log_triage.rules import check, counts                      # noqa: E402
from log_triage.signature import cluster                        # noqa: E402

BASE = "https://raw.githubusercontent.com/logpai/loghub/master"
CORPORA = [
    ("HDFS", "HDFS/HDFS_2k.log", "Hadoop HDFS (2008)"),
    ("Apache", "Apache/Apache_2k.log", "Apache httpd error log"),
    ("Linux", "Linux/Linux_2k.log", "Linux syslog"),
    ("Mac", "Mac/Mac_2k.log", "macOS syslog"),
    ("Zookeeper", "Zookeeper/Zookeeper_2k.log", "ZooKeeper"),
    ("OpenStack", "OpenStack/OpenStack_2k.log", "OpenStack Nova"),
    ("HPC", "HPC/HPC_2k.log", "HPC cluster"),
    ("Proxifier", "Proxifier/Proxifier_2k.log", "Proxifier"),
    ("HealthApp", "HealthApp/HealthApp_2k.log", "Android HealthApp"),
    ("BGL", "BGL/BGL_2k.log", "Blue Gene/L"),
    ("Spark", "Spark/Spark_2k.log", "Apache Spark"),
    ("Android", "Android/Android_2k.log", "Android logcat"),
    ("Thunderbird", "Thunderbird/Thunderbird_2k.log", "Thunderbird"),
    ("Windows", "Windows/Windows_2k.log", "Windows event log"),
]


def fetch(url: str, target: Path) -> bytes:
    if target.exists():
        return target.read_bytes()
    with urllib.request.urlopen(url, timeout=40) as response:
        data = response.read()
    target.write_bytes(data)
    return data


def measure(data: bytes) -> dict:
    text, encoding, confidence, bom = decode_bytes(data)
    started = time.perf_counter()
    log = parse_text(text, path="mem", encoding=encoding, confidence=confidence, bom=bom)
    parse_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    clusters = cluster(log)
    cluster_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    findings = check(log)
    rules_ms = (time.perf_counter() - started) * 1000

    rate = analyze(log, templates={c.signature: c.template for c in clusters})
    first, last, seconds = log.span()
    top = clusters[0] if clusters else None
    return {
        "encoding": encoding,
        "confidence": confidence,
        "lines": log.total_lines,
        "records": len(log.records),
        "parse_rate": 100.0 * len(log.records) / max(1, log.total_lines),
        "coverage": 100.0 * (len(log.records) + log.continuation_lines + len(log.orphans))
                    / max(1, log.total_lines),
        "clusters": len(clusters),
        "top_share": 100.0 * top.count / max(1, len(log.records)) if top else 0.0,
        "errors": len(log.error_records()),
        "minutes": seconds / 60.0,
        "kinds": ", ".join(k for k, _ in log.ts_kinds().most_common(2)),
        "findings": counts(findings),
        "parse_ms": parse_ms,
        "cluster_ms": cluster_ms,
        "rules_ms": rules_ms,
        "bursts": len(rate.error_bursts),
        "gaps": len(rate.gaps),
        "out_of_order": rate.out_of_order,
        "top_template": top.template[:70] if top else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "loghub-2k"))
    parser.add_argument("--only", default="")
    parser.add_argument("--md", action="store_true", help="README 용 마크다운 표")
    args = parser.parse_args()

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    wanted = {name.strip().lower() for name in args.only.split(",") if name.strip()}

    rows = []
    for name, path, note in CORPORA:
        if wanted and name.lower() not in wanted:
            continue
        url = f"{BASE}/{path}"
        try:
            data = fetch(url, cache / Path(path).name)
        except Exception as exc:                     # 네트워크가 없으면 그 줄만 건너뛴다
            print(f"skip {name}: {exc}", file=sys.stderr)
            continue
        stats = measure(data)
        stats.update(name=name, note=note, bytes=len(data))
        rows.append(stats)

    if args.md:
        print("| 코퍼스 | 줄 | 레코드 | 시각 읽음 | 버린 줄 없음 | 서명 | 최다 비중 | ERROR | 기간 | 인코딩 | 규칙(치명/주의/참고) |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
        for row in rows:
            findings = row["findings"]
            print(f"| {row['name']} | {row['lines']:,} | {row['records']:,} | "
                  f"{row['parse_rate']:.1f}% | {row['coverage']:.1f}% | {row['clusters']:,} | "
                  f"{row['top_share']:.0f}% | {row['errors']:,} | {row['minutes']:.0f}분 | "
                  f"{row['encoding']} | "
                  f"{findings.get('critical', 0)}/{findings.get('warn', 0)}/{findings.get('info', 0)} |")
    else:
        header = f"{'corpus':<12}{'bytes':>9}{'lines':>7}{'recs':>7}{'parse':>7}{'sigs':>6}{'top%':>6}{'err':>5}{'min':>6}  {'enc':<10}{'parse_ms':>9}{'rules_ms':>9}"
        print(header)
        print("-" * len(header))
        for row in rows:
            line = (f"{row['name']:<12}{row['bytes']:>9,}{row['lines']:>7,}{row['records']:>7,}"
                    f"{row['parse_rate']:>6.1f}%{row['clusters']:>6,}{row['top_share']:>5.0f}%"
                    f"{row['errors']:>5,}{row['minutes']:>6.0f}  {row['encoding']:<10}"
                    f"{row['parse_ms']:>9.1f}{row['rules_ms']:>9.1f}")
            print(line)

    if rows:
        total_lines = sum(r["lines"] for r in rows)
        total_records = sum(r["records"] for r in rows)
        parse_ms = sum(r["parse_ms"] for r in rows)
        print()
        print(f"합계 {len(rows)}개 코퍼스 · {total_lines:,}줄 → 레코드 {total_records:,} "
              f"({100 * total_records / max(1, total_lines):.1f}%) · 파싱 {parse_ms:.0f}ms")
        unparsed = [r["name"] for r in rows if r["parse_rate"] < 50]
        if unparsed:
            print("절반 미만: " + ", ".join(unparsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
