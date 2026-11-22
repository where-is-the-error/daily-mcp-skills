"""속성 단위 diff — plan 이 '무엇을' 바꾸는지, 목록 안쪽까지.

terraform 은 `before`/`after` 를 통째로 준다. 그대로 비교하면 보안 그룹 규칙처럼
목록 순서가 바뀐 것만으로도 전부 달라진 것처럼 보인다. 그래서 목록은

1. 완전히 같은 항목끼리 먼저 붙이고(순서 무관),
2. 남은 항목은 식별자(`from_port/to_port/protocol`, `name`, `key`, `id`)로 붙이고,
3. 그래도 남으면 인덱스 순서대로 붙인다.

이렇게 하면 `ingress` 두 개 중 22번만 대상이 바뀐 것을 한 줄로 보여 줄 수 있다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .plan import Change, is_sensitive_at, short

KIND_ORDER = {"changed": 0, "added": 1, "removed": 2, "unknown": 3}
KIND_LABELS = {"changed": "바뀜", "added": "생김", "removed": "사라짐", "unknown": "적용 후 결정"}

# 리소스를 새로 만들거나 지울 때 먼저 보여 줄 속성 — 나머지는 개수만 센다.
KEY_ATTRS = (
    "identifier",
    "name",
    "username",
    "password",
    "bucket",
    "acl",
    "engine",
    "engine_version",
    "instance_class",
    "instance_type",
    "ami",
    "cidr_blocks",
    "from_port",
    "to_port",
    "protocol",
    "action",
    "policy",
    "enabled",
    "storage_encrypted",
    "skip_final_snapshot",
    "deletion_protection",
    "count",
    "runtime",
    "handler",
)


@dataclass(frozen=True)
class AttrDiff:
    path: str
    kind: str
    before: Any = None
    after: Any = None
    sensitive: bool = False

    @property
    def label(self) -> str:
        return KIND_LABELS[self.kind]

    def line(self) -> str:
        left = "«민감»" if self.sensitive else short(self.before)
        right = "«민감»" if self.sensitive else short(self.after)
        if self.kind == "added":
            return f"{self.path} = {right}"
        if self.kind == "removed":
            return f"{self.path} = {left} → (사라짐)"
        if self.kind == "unknown":
            return f"{self.path} → 적용 후 결정"
        return f"{self.path}: {left} → {right}"


def canonical(item: Any) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)


def identity_of(item: Any) -> str | None:
    """목록 항목의 식별자 — 보안 그룹 규칙, 이름 있는 블록을 붙이기 위해."""
    if not isinstance(item, dict):
        return None
    if {"from_port", "to_port", "protocol"} <= item.keys():
        return f"{item['protocol']}/{item['from_port']}-{item['to_port']}"
    for key in ("name", "key", "id", "mount_point", "device_name"):
        if key in item and isinstance(item[key], (str, int)):
            return f"{key}={item[key]}"
    return None


def match_lists(before: list, after: list) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """(짝지은 (before_idx, after_idx), 남은 before 인덱스, 남은 after 인덱스)."""
    pairs: list[tuple[int, int]] = []
    left = list(range(len(before)))
    right = list(range(len(after)))

    # 1) 완전히 같은 항목
    same_left: dict[str, list[int]] = {}
    for i in left:
        same_left.setdefault(canonical(before[i]), []).append(i)
    for j in list(right):
        key = canonical(after[j])
        bucket = same_left.get(key)
        if bucket:
            i = bucket.pop(0)
            pairs.append((i, j))
            left.remove(i)
            right.remove(j)

    # 2) 식별자가 같은 항목
    by_identity: dict[str, list[int]] = {}
    for i in left:
        ident = identity_of(before[i])
        if ident:
            by_identity.setdefault(ident, []).append(i)
    for j in list(right):
        ident = identity_of(after[j])
        if not ident:
            continue
        bucket = by_identity.get(ident)
        if bucket:
            i = bucket.pop(0)
            pairs.append((i, j))
            left.remove(i)
            right.remove(j)

    # 3) 남은 것은 인덱스 순서대로
    while left and right:
        pairs.append((left.pop(0), right.pop(0)))

    return sorted(pairs), left, right


def _walk(before: Any, after: Any, path: str, sens_b: Any, sens_a: Any, out: list[AttrDiff]) -> None:
    sensitive = sens_b is True or sens_a is True

    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            _walk(
                before.get(key),
                after.get(key),
                child,
                sens_b.get(key) if isinstance(sens_b, dict) else None,
                sens_a.get(key) if isinstance(sens_a, dict) else None,
                out,
            )
        return

    if isinstance(before, list) and isinstance(after, list):
        pairs, only_before, only_after = match_lists(before, after)
        for i, j in pairs:
            ident = identity_of(before[i]) or identity_of(after[j])
            key = f"{path}[{ident}]" if ident else f"{path}[{j}]"
            _walk(
                before[i],
                after[j],
                key,
                sens_b[i] if isinstance(sens_b, list) and i < len(sens_b) else None,
                sens_a[j] if isinstance(sens_a, list) and j < len(sens_a) else None,
                out,
            )
        for i in only_before:
            ident = identity_of(before[i])
            key = f"{path}[{ident}]" if ident else f"{path}[{i}]"
            out.append(AttrDiff(key, "removed", before=before[i], sensitive=sensitive))
        for j in only_after:
            ident = identity_of(after[j])
            key = f"{path}[{ident}]" if ident else f"{path}[{j}]"
            out.append(AttrDiff(key, "added", after=after[j], sensitive=sensitive))
        return

    if before == after:
        return
    # 한쪽에만 있는 '빈 값'은 소음이다 — terraform 은 블록 속성을 ""/[]/{} 로 채워 보낸다.
    if before is None and after in ("", [], {}):
        return
    if after is None and before in ("", [], {}):
        return
    if before is None:
        out.append(AttrDiff(path, "added", after=after, sensitive=sensitive))
    elif after is None:
        out.append(AttrDiff(path, "removed", before=before, sensitive=sensitive))
    else:
        out.append(AttrDiff(path, "changed", before=before, after=after, sensitive=sensitive))


def diff_change(change: Change, include_unknown: bool = True) -> list[AttrDiff]:
    """리소스 하나의 속성 diff. plan 값은 건드리지 않는다."""
    out: list[AttrDiff] = []
    before = change.before or {}
    after = change.after or {}
    _walk(before, after, "", change.before_sensitive, change.after_sensitive, out)

    if change.kind == "replace":
        # 재생성은 '이전 것'이 없는 새 객체다 — 사라진 속성은 '적용 후 결정'이 맞다.
        out = [AttrDiff(d.path, "unknown", sensitive=d.sensitive) if d.kind == "removed" else d for d in out]

    if include_unknown and isinstance(change.after_unknown, dict):
        for key in sorted(change.after_unknown):
            if change.after_unknown.get(key) is True and after.get(key) is None:
                out.append(AttrDiff(key, "unknown", sensitive=False))

    seen: set[tuple[str, str]] = set()
    unique: list[AttrDiff] = []
    for diff in out:
        key = (diff.path, diff.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(diff)
    return sorted(unique, key=lambda d: (KIND_ORDER[d.kind], d.path))


def summary(diffs: list[AttrDiff]) -> dict[str, int]:
    counts = {"changed": 0, "added": 0, "removed": 0, "unknown": 0}
    for diff in diffs:
        counts[diff.kind] += 1
    return counts


def key_values(change: Change, side: str = "after", limit: int = 6) -> list[tuple[str, Any]]:
    """새로 생기거나 사라지는 리소스에서 먼저 보여 줄 속성."""
    data = (change.after if side == "after" else change.before) or {}
    sensitive = change.after_sensitive if side == "after" else change.before_sensitive
    picked: list[tuple[str, Any]] = []
    for key in KEY_ATTRS:
        if key in data and data[key] not in (None, "", [], {}):
            value = "«민감»" if is_sensitive_at(sensitive, (key,)) else data[key]
            picked.append((key, value))
        if len(picked) >= limit:
            break
    return picked


def describe(change: Change, max_items: int = 8) -> list[str]:
    """diff 를 사람이 읽는 줄로. 개수가 많으면 잘라서 알려 준다."""
    if change.kind in ("create", "delete"):
        side = "after" if change.kind == "create" else "before"
        picked = key_values(change, side)
        label = "(새 리소스)" if change.kind == "create" else "(사라지는 값)"
        return [label + ("" if not picked else " " + ", ".join(f"{k}={short(v, 24)}" for k, v in picked))]

    diffs = diff_change(change)
    if not diffs:
        return ["(속성 변화 없음)"]

    unknown = [d for d in diffs if d.kind == "unknown"]
    shown = [d for d in diffs if d.kind != "unknown"] if len(unknown) > 3 else diffs
    lines = [f"- {d.line()}" for d in shown[:max_items]]
    left = len(shown) - len(lines)
    if left > 0:
        lines.append(f"… 그 밖에 {left}개")
    if len(unknown) > 3:
        lines.append(f"- (재생성·생성이라 속성 {len(unknown)}개는 적용 후에 정해집니다)")
    return lines
