"""terraform plan JSON 을 읽어 '무엇이 바뀌는가'로 바꾼다.

plan JSON(`terraform show -json plan.out`)은 사람이 읽기엔 너무 크고,
민감값은 그대로 들어 있다. 이 모듈은 다음 세 가지만 책임진다.

1. 파일/문자열 → `Plan` (형식 검사, 오류는 한국어로)
2. `resource_changes` → `Change` (액션을 create/update/delete/replace/noop/read 로 접기)
3. 민감값 마스킹 — 표시하기 전에 `«민감»` 으로 가린다 (project, plan 값은 건드리지 않는다)

판정(위험·순서·롤백)은 다른 모듈이 한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

MASK = "«민감»"
UNKNOWN = "(적용 후 결정)"

# plan JSON format_version 은 "1.2" 처럼 온다. 1.x 만 읽는다.
SUPPORTED_MAJOR = "1"

ACTION_LABELS = {
    "create": "생성",
    "update": "수정",
    "delete": "삭제",
    "replace": "재생성",
    "noop": "변화 없음",
    "read": "읽기",
}

ACTION_REASONS = {
    "replace_because_tainted": "taint 표시된 리소스",
    "replace_because_cannot_update": "제자리에서 바꿀 수 없는 속성",
    "replace_by_request": "-replace 로 지정됨",
    "delete_because_no_resource_config": "설정에서 빠짐",
    "delete_because_wrong_repetition": "count/for_each 가 줄어듦",
    "delete_because_count_index": "count 인덱스가 바뀜",
    "delete_because_each_key": "for_each 키가 빠짐",
    "delete_because_no_module": "모듈이 빠짐",
    "read_because_config_unknown": "설정값을 적용 시점에 앎",
    "read_because_dependency_pending": "의존 대상이 아직 없음",
    "read_because_check_nested": "check 블록",
}


class PlanError(ValueError):
    """plan JSON 이 아니거나 읽을 수 없을 때. 메시지는 사용자에게 그대로 보여 준다."""


@dataclass(frozen=True)
class Change:
    """리소스 하나의 변경. plan JSON 의 resource_changes 항목 하나에 대응한다."""

    address: str
    mode: str
    type: str
    name: str
    provider_name: str
    actions: tuple[str, ...]
    before: dict[str, Any] | None = field(default=None)
    after: dict[str, Any] | None = field(default=None)
    before_sensitive: Any = field(default=None)
    after_sensitive: Any = field(default=None)
    after_unknown: Any = field(default=None)
    action_reason: str | None = field(default=None)
    replace_paths: tuple[tuple[str, ...], ...] = field(default=())
    index: int = field(default=0)

    # ---------------------------------------------------------------- 분류
    @property
    def ref(self) -> str:
        return f"r{self.index + 1}"

    @property
    def kind(self) -> str:
        acts = set(self.actions)
        if acts == {"no-op"}:
            return "noop"
        if acts == {"read"}:
            return "read"
        if acts == {"create"}:
            return "create"
        if acts == {"delete"}:
            return "delete"
        if acts == {"update"}:
            return "update"
        if acts >= {"create", "delete"}:
            return "replace"
        return "other"

    @property
    def kind_label(self) -> str:
        return ACTION_LABELS[self.kind]

    @property
    def creates(self) -> bool:
        return "create" in self.actions

    @property
    def deletes(self) -> bool:
        return "delete" in self.actions

    @property
    def writes(self) -> bool:
        """이번에 값을 쓰는가(생성·수정·재생성) — 삭제만 있는 변경은 False."""
        return self.kind in ("create", "update", "replace")

    @property
    def destructive(self) -> bool:
        """지금 있는 것이 사라지는가 — 삭제·재생성만 True."""
        return self.deletes

    @property
    def create_before_destroy(self) -> bool:
        acts = list(self.actions)
        return acts[:2] == ["create", "delete"]

    @property
    def reason_label(self) -> str:
        if not self.action_reason:
            return ""
        return ACTION_REASONS.get(self.action_reason, self.action_reason)

    @property
    def module_address(self) -> str:
        """`module.net.aws_vpc.main` → `module.net` (중첩 모듈도 마지막 module 까지)."""
        parts = self.address.split(".")
        kept: list[str] = []
        index = 0
        while index < len(parts) and parts[index] == "module" and index + 1 < len(parts):
            kept.extend([parts[index], parts[index + 1]])
            index += 2
        return ".".join(kept)

    # ---------------------------------------------------------------- 값
    def before_masked(self) -> dict[str, Any]:
        return mask(self.before or {}, self.before_sensitive)

    def after_masked(self) -> dict[str, Any]:
        return mask(self.after or {}, self.after_sensitive)

    def after_with_unknown(self) -> dict[str, Any]:
        """after + 적용 시점에 정해지는 값 표시."""
        base = self.after_masked()
        return overlay_unknown(base, self.after_unknown)

    def get_before(self, key: str, default: Any = None) -> Any:
        return (self.before or {}).get(key, default)

    def get_after(self, key: str, default: Any = None) -> Any:
        return (self.after or {}).get(key, default)


@dataclass
class Plan:
    format_version: str
    terraform_version: str
    timestamp: str
    changes: list[Change]
    configuration: dict[str, Any] | None = None
    complete: bool = True
    errored: bool = False
    applyable: bool = True
    source: str = ""

    # ---------------------------------------------------------------- 요약
    def by_kind(self) -> dict[str, int]:
        counts = {k: 0 for k in ("create", "update", "delete", "replace", "noop", "read", "other")}
        for change in self.changes:
            counts[change.kind] += 1
        return counts

    def real_changes(self) -> list[Change]:
        return [c for c in self.changes if c.kind not in ("noop", "read")]

    def destructive(self) -> list[Change]:
        return [c for c in self.changes if c.destructive]

    def by_address(self) -> dict[str, Change]:
        return {c.address: c for c in self.changes}

    def find(self, address: str) -> list[Change]:
        return [c for c in self.changes if c.address == address or c.address.startswith(address.rstrip(".") + ".")]

    def types(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            if change.kind in ("noop", "read"):
                continue
            counts[change.type] = counts.get(change.type, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def provider_short(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            if change.kind in ("noop", "read"):
                continue
            name = change.provider_name.rsplit("/", 1)[-1] or change.provider_name
            counts[name] = counts.get(name, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "terraform_version": self.terraform_version,
            "changes": [
                {
                    "ref": c.ref,
                    "address": c.address,
                    "type": c.type,
                    "actions": list(c.actions),
                    "kind": c.kind,
                }
                for c in self.changes
            ],
        }


# -------------------------------------------------------------------- 로딩
def load_plan(source: str, base_dir: Path | None = None) -> Plan:
    """파일 경로 또는 plan JSON 문자열을 받는다.

    - 경로가 있으면 파일을 읽고, 없으면 문자열로 본다 (`{` 로 시작해야 한다).
    - `terraform show -json` 결과 전체와, `resource_changes` 만 있는 조각을 모두 받는다.
    """
    if source is None or (isinstance(source, str) and not source.strip()):
        raise PlanError("plan JSON 경로나 내용을 주세요.")

    text = source
    origin = ""
    candidate = Path(source) if isinstance(source, str) else None
    looks_like_json = isinstance(source, str) and source.lstrip().startswith("{")
    if candidate is not None and not looks_like_json:
        path = candidate
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        if not path.exists():
            raise PlanError(
                f"plan 파일을 찾을 수 없습니다: {candidate}\n"
                "`terraform plan -out=tfplan` 다음 `terraform show -json tfplan > plan.json` 로 만드세요."
            )
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PlanError(f"plan 파일을 읽지 못했습니다: {exc}") from exc
        origin = str(path)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"JSON 이 아닙니다 ({exc.msg}, {exc.lineno}번째 줄).") from exc

    return from_dict(data, source=origin)


def from_dict(data: Any, source: str = "") -> Plan:
    if not isinstance(data, dict):
        raise PlanError("plan JSON 의 최상위가 객체가 아닙니다.")

    # resource_changes 만 잘라 온 조각도 받는다.
    if "resource_changes" not in data and "format_version" not in data:
        raise PlanError(
            "terraform plan JSON 이 아닙니다. `format_version` 과 `resource_changes` 가 없습니다.\n"
            "`terraform show -json tfplan` 의 출력을 그대로 저장했는지 확인하세요."
        )

    fmt = str(data.get("format_version") or "1.0")
    if fmt.split(".")[0] != SUPPORTED_MAJOR:
        raise PlanError(f"지원하지 않는 plan 형식입니다: {fmt} (1.x 만 읽습니다).")

    raw_changes = data.get("resource_changes")
    if raw_changes is None:
        raw_changes = []
    if not isinstance(raw_changes, list):
        raise PlanError("resource_changes 가 배열이 아닙니다.")

    changes: list[Change] = []
    for index, item in enumerate(raw_changes):
        if not isinstance(item, dict):
            continue
        change = item.get("change") or {}
        actions = tuple(change.get("actions") or ())
        if not actions:
            continue
        changes.append(
            Change(
                address=str(item.get("address") or ""),
                mode=str(item.get("mode") or "managed"),
                type=str(item.get("type") or ""),
                name=str(item.get("name") or ""),
                provider_name=str(item.get("provider_name") or ""),
                actions=actions,
                before=change.get("before"),
                after=change.get("after"),
                before_sensitive=change.get("before_sensitive"),
                after_sensitive=change.get("after_sensitive"),
                after_unknown=change.get("after_unknown"),
                action_reason=change.get("action_reason"),
                replace_paths=tuple(tuple(p) for p in (change.get("replace_paths") or ())),
                index=index,
            )
        )

    return Plan(
        format_version=fmt,
        terraform_version=str(data.get("terraform_version") or "?"),
        timestamp=str(data.get("timestamp") or ""),
        changes=changes,
        configuration=data.get("configuration"),
        complete=bool(data.get("complete", True)),
        errored=bool(data.get("errored", False)),
        applyable=bool(data.get("applyable", True)),
        source=source,
    )


# -------------------------------------------------------------------- 마스킹
def mask(value: Any, sensitive: Any) -> Any:
    """terraform 의 before_sensitive / after_sensitive 모양을 따라 값을 가린다.

    sensitive 는 값과 같은 모양이다. 잎이 True 면 그 값을 «민감» 으로 바꾼다.
    목록은 같은 인덱스끼리 맞춘다 — terraform 도 그렇게 만든다.
    """
    if sensitive is True:
        return MASK
    if isinstance(value, dict) and isinstance(sensitive, dict):
        return {k: mask(v, sensitive.get(k)) for k, v in value.items()}
    if isinstance(value, list) and isinstance(sensitive, list):
        out = []
        for i, v in enumerate(value):
            out.append(mask(v, sensitive[i] if i < len(sensitive) else None))
        return out
    return value


def is_sensitive_at(sensitive: Any, path: Iterable[str | int]) -> bool:
    node = sensitive
    for step in path:
        if node is True:
            return True
        if isinstance(node, dict) and isinstance(step, str):
            node = node.get(step)
        elif isinstance(node, list) and isinstance(step, int):
            node = node[step] if step < len(node) else None
        else:
            return False
        if node is None:
            return False
    return node is True


def overlay_unknown(value: Any, unknown: Any) -> Any:
    """after_unknown 이 True 인 잎을 '(적용 후 결정)' 로 바꾼다."""
    if unknown is True:
        return UNKNOWN
    if isinstance(value, dict) and isinstance(unknown, dict):
        return {k: overlay_unknown(v, unknown.get(k)) for k, v in value.items()}
    if isinstance(value, list) and isinstance(unknown, list):
        return [overlay_unknown(v, unknown[i] if i < len(unknown) else None) for i, v in enumerate(value)]
    return value


def sensitive_paths(sensitive: Any, prefix: tuple = ()) -> list[tuple]:
    """민감 표시된 잎의 경로 목록 — 표시할 때 어떤 값이 가려졌는지 알려 주기 위해."""
    found: list[tuple] = []
    if sensitive is True:
        found.append(prefix)
    elif isinstance(sensitive, dict):
        for key, sub in sensitive.items():
            found.extend(sensitive_paths(sub, prefix + (key,)))
    elif isinstance(sensitive, list):
        for i, sub in enumerate(sensitive):
            found.extend(sensitive_paths(sub, prefix + (i,)))
    return found


def format_path(path: tuple) -> str:
    out = ""
    for step in path:
        if isinstance(step, int):
            out += f"[{step}]"
        else:
            out += f".{step}" if out else step
    return out


def short(value: Any, limit: int = 60) -> str:
    """diff 한 줄에 넣을 값 표기 — 문자열·숫자·불리언·목록·딕셔너리."""
    if value is None:
        return "(없음)"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        text = value.replace("\n", " ")
        return text if len(text) <= limit else text[: limit - 1] + "…"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ", ".join(short(v, 20) for v in value[:3])
        more = f" … {len(value)}개" if len(value) > 3 else ""
        return f"[{inner}]{more}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ", ".join(f"{k}={short(v, 18)}" for k, v in list(value.items())[:3])
        more = " …" if len(value) > 3 else ""
        return "{" + inner + more + "}"
    return str(value)[:limit]
