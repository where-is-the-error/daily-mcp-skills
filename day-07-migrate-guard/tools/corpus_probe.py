#!/usr/bin/env python3
"""공개 저장소의 실제 마이그레이션을 그대로 읽어 본다 (네트워크 필요).

    python3 tools/corpus_probe.py                       # 기본: mattermost/mattermost
    python3 tools/corpus_probe.py --repo owner/name --path db/migrations --limit 50

파일은 내려받아 분석만 하고 저장소에 남기지 않는다(라이선스가 다른 코드를 복제하지 않는다).
목적은 두 가지다.
  1. 문장 나누기·분류가 실제 파일에서 깨지지 않는지 (예외 0건)
  2. 어떤 규칙이 실제 코드에서 얼마나 걸리는지
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrate_guard import risks                       # noqa: E402
from migrate_guard.dialect import Severity            # noqa: E402
from migrate_guard.fmt import duration                # noqa: E402
from migrate_guard.operations import analyze          # noqa: E402
from migrate_guard.splitter import split_statements   # noqa: E402


def list_files(repo: str, prefix: str, pattern: str) -> list[str]:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/trees/HEAD?recursive=1", "-q", ".tree[].path"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return sorted(path for path in out if path.startswith(prefix) and path.endswith(pattern))


def fetch(repo: str, path: str) -> str | None:
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="mattermost/mattermost")
    parser.add_argument("--path", default="server/channels/db/migrations/postgres/")
    parser.add_argument("--suffix", default=".up.sql")
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    paths = list_files(args.repo, args.path, args.suffix)[: args.limit]
    print(f"파일 {len(paths)}개 ({args.repo} {args.path}*{args.suffix})")

    with ThreadPoolExecutor(max_workers=16) as pool:
        bodies = list(pool.map(lambda path: fetch(args.repo, path), paths))

    kinds: Counter[str] = Counter()
    rule_hits: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    errors: list[str] = []
    statements = 0
    unclassified: list[str] = []
    longest: tuple[float, str, str] = (0.0, "", "")

    for path, body in zip(paths, bodies):
        if body is None:
            errors.append(f"{path}: 내려받지 못함")
            continue
        try:
            result = analyze(body, pg_version=16, label=path)
        except Exception as exc:                      # pragma: no cover - 실제 코퍼스 확인용
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        statements += len(result.ops)
        for operation in result.ops:
            kinds[operation.kind] += 1
            if operation.kind == "other":
                head = operation.sql.split(None, 1)[0].upper() if operation.sql.split() else ""
                if head not in {"SET", "SELECT", "COMMENT", "DO", "CALL", "WITH", "CREATE", "ALTER",
                                "DROP", "GRANT", "REVOKE", "ANALYZE", "VACUUM", "REINDEX"}:
                    unclassified.append(f"{path}: {operation.sql[:70]}")
        items = risks.findings(result)
        verdicts[risks.verdict(items)] += 1
        for finding in items:
            rule_hits[finding.rule_id] += 1
        worst = result.worst()
        if worst and worst.estimate() > longest[0]:
            longest = (worst.estimate(), path, f"{worst.table or '-'} {worst.lock_mode}")

    print(f"문장 {statements}개 · 예외 {len(errors)}건 · 분류 밖 {len(unclassified)}건")
    print("판정 분포: " + " · ".join(f"{key} {value}" for key, value in verdicts.most_common()))
    print("문장 종류 상위: " + ", ".join(f"{key} {value}" for key, value in kinds.most_common(10)))
    print("규칙 적중 상위:")
    for rule_id, count in rule_hits.most_common(8):
        rule = risks.rule(rule_id)
        print(f"  {count:4d}  {rule.severity.name} {rule_id} — {rule.title}")
    if longest[0]:
        print(f"가장 긴 잠금(가정 10만 행 기준): {duration(longest[0])} · {longest[1]} · {longest[2]}")
    for error in errors[:10]:
        print("  ERR", error)
    for line in unclassified[:10]:
        print("  ?", line)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "files": len(paths),
            "statements": statements,
            "errors": errors,
            "kinds": kinds.most_common(),
            "rules": rule_hits.most_common(),
            "verdicts": verdicts.most_common(),
            "unclassified": unclassified,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
