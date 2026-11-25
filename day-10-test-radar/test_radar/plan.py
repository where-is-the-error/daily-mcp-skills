"""선택 결과를 CI 명령으로 바꾼다 — 무엇을, 어떤 순서로, 몇 조각으로.

시간은 **모델**이다(항목 수 × 가정 초). 실측 시간이 아니다 — 결과에도 그렇게 적는다.
"""

from __future__ import annotations

from .select import ChangeSet
from .types import Plan

DEFAULT_PER_ITEM_MS = 50
DEFAULT_STARTUP_MS = 250


def _commands_for(language: str, files: list[str]) -> str:
    if language == "javascript":
        return "npx jest " + " ".join(files)
    return "python -m pytest " + " ".join(files)


def _language(change_set: ChangeSet, path: str) -> str:
    test = change_set.repo.test(path)
    return test.language if test else "python"


def _estimate(items: int, files: int, per_item_ms: int, startup_ms: int) -> float:
    return round((items * per_item_ms + files * startup_ms) / 1000.0, 2)


def build(change_set: ChangeSet, shards: int = 2, per_item_ms: int = DEFAULT_PER_ITEM_MS,
          startup_ms: int = DEFAULT_STARTUP_MS, max_per_shard: int = 0) -> Plan:
    shards = max(1, min(int(shards or 1), 8))
    mandatory = [sel for sel in change_set.selections.values() if sel.mandatory]
    optional = [sel for sel in change_set.selections.values() if not sel.mandatory]
    mandatory.sort(key=lambda sel: (-sel.score, sel.path))
    optional.sort(key=lambda sel: (-sel.score, sel.path))

    commands: list[dict] = []
    for language in ("python", "javascript"):
        files = [sel.path for sel in mandatory if _language(change_set, sel.path) == language]
        if not files:
            continue
        if shards == 1 or len(files) <= 1:
            items = sum(sel.items for sel in mandatory if sel.path in files)
            commands.append({
                "label": f"{language} 필수",
                "command": _commands_for(language, files),
                "files": files,
                "items": items,
                "est_seconds": _estimate(items, len(files), per_item_ms, startup_ms),
                "note": "먼저 돌려 실패를 빨리 본다",
            })
            continue
        buckets: list[list] = [[] for _ in range(shards)]
        loads = [0] * shards
        for sel in [row for row in mandatory if row.path in files]:
            index = min(range(shards), key=lambda i: (loads[i], i))
            buckets[index].append(sel)
            loads[index] += sel.items
        for number, bucket in enumerate(buckets, start=1):
            if not bucket:
                continue
            bucket_files = [sel.path for sel in bucket]
            items = sum(sel.items for sel in bucket)
            if max_per_shard and items > max_per_shard:
                note = f"한 조각 {max_per_shard}항목 초과 — 조각을 늘리세요"
            else:
                note = f"조각 {number}/{shards}"
            commands.append({
                "label": f"{language} 필수 {number}",
                "command": _commands_for(language, bucket_files),
                "files": bucket_files,
                "items": items,
                "est_seconds": _estimate(items, len(bucket_files), per_item_ms, startup_ms),
                "note": note,
            })

    if optional:
        for language in ("python", "javascript"):
            files = [sel.path for sel in optional if _language(change_set, sel.path) == language]
            if not files:
                continue
            items = sum(sel.items for sel in optional if sel.path in files)
            commands.append({
                "label": f"{language} 참고",
                "command": _commands_for(language, files),
                "files": files,
                "items": items,
                "est_seconds": _estimate(items, len(files), per_item_ms, startup_ms),
                "note": "근거가 약함(같은 디렉터리) — 실패해도 이번 변경 탓으로 단정하지 말 것",
            })

    total_items = change_set.total_items()
    full_command = "python -m pytest" if change_set.repo.test and any(
        change_set.repo.test(path) and change_set.repo.test(path).language == "python"
        for path in change_set.repo.tests) else "npx jest"
    fallback = {
        "command": full_command,
        "items": total_items,
        "est_seconds": _estimate(total_items, len(change_set.repo.tests), per_item_ms, startup_ms),
        "reasons": list(change_set.fallback),
        "triggered": bool(change_set.fallback),
    }
    assumed = {
        "per_item_ms": per_item_ms,
        "startup_ms": startup_ms,
        "shards": shards,
        "note": "시간은 항목 수 × 가정값 모델입니다 — 실제 실행 시간이 아닙니다",
    }
    return Plan(commands=commands, fallback=fallback, assumed=assumed)


def estimated_total(plan: Plan) -> float:
    return round(sum(command["est_seconds"] for command in plan.commands), 2)
