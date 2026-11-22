"""plan 파일을 그대로 공유해도 되게 만든다.

`terraform show -json` 의 출력에는 DB 비밀번호 같은 값이 **평문으로** 들어 있다.
terraform 은 sensitive 로 '표시'만 하고 지우지는 않기 때문이다. 실제로 한 plan 에서
같은 비밀번호가 세 곳에 나온다.

1. `resource_changes[].change.before/after` — sensitive 표시가 붙어 있다 (여기는 확실히 가린다)
2. `planned_values` / `prior_state` — 리소스의 `sensitive_values` 를 따른다. 없으면 같은 주소의
   `resource_changes` 표시를 빌려 쓴다.
3. `configuration...expressions.<이름>.constant_value` — **설정 파일에 쓴 값 그대로**다.
   여기엔 sensitive 표시가 없다. 그래서 이름(password·secret·token·key…)으로 판단해 가린다.

한계: 이름으로도 알 수 없고 sensitive 표시도 없는 값은 가려지지 않는다.
이 함수는 **가린 사본**을 돌려줄 뿐, 원본 파일은 건드리지 않는다.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from .plan import MASK, mask

SENSITIVE_NAME = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|passphrase|credential|auth)",
    re.I,
)


def _count_sensitive(sensitive: Any) -> int:
    if sensitive is True:
        return 1
    if isinstance(sensitive, dict):
        return sum(_count_sensitive(v) for v in sensitive.values())
    if isinstance(sensitive, list):
        return sum(_count_sensitive(v) for v in sensitive)
    return 0


def _redact_values(container: dict, value_key: str, sensitive_key: str) -> int:
    value = container.get(value_key)
    sensitive = container.get(sensitive_key)
    if value is None or sensitive is None:
        return 0
    container[value_key] = mask(value, sensitive)
    return _count_sensitive(sensitive)


def _sensitivity_map(data: dict) -> dict[str, Any]:
    """주소 → (before_sensitive, after_sensitive) — 다른 절에서 표시를 빌려 쓰기 위해."""
    out: dict[str, Any] = {}
    for item in data.get("resource_changes") or []:
        if not isinstance(item, dict):
            continue
        change = item.get("change") or {}
        out[str(item.get("address"))] = (change.get("before_sensitive"), change.get("after_sensitive"))
    return out


def merge_sensitive(a: Any, b: Any) -> Any:
    """두 민감 표시를 합친다 — 어느 한쪽이 민감하면 민감."""
    if a is True or b is True:
        return True
    if isinstance(a, dict) or isinstance(b, dict):
        left = a if isinstance(a, dict) else {}
        right = b if isinstance(b, dict) else {}
        return {key: merge_sensitive(left.get(key), right.get(key)) for key in set(left) | set(right)}
    if isinstance(a, list) or isinstance(b, list):
        left = a if isinstance(a, list) else []
        right = b if isinstance(b, list) else []
        size = max(len(left), len(right))
        return [merge_sensitive(left[i] if i < len(left) else None, right[i] if i < len(right) else None)
                for i in range(size)]
    return a if a is not None else b


def _walk_module(module: dict, fallback: dict[str, Any], side: str) -> int:
    count = 0
    for resource in module.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        own = resource.get("sensitive_values")
        address = str(resource.get("address") or "")
        pair = fallback.get(address)
        if pair:
            own = merge_sensitive(own, pair[1] if side == "after" else pair[0])
        if own is not None and resource.get("values") is not None:
            resource["values"] = mask(resource["values"], own)
            count += _count_sensitive(own)
    for call in module.get("child_modules") or []:
        if isinstance(call, dict):
            count += _walk_module(call, fallback, side)
    return count


def _redact_configuration(module: dict) -> int:
    """설정에 박힌 상수 중 이름이 수상한 것 — terraform 이 표시해 주지 않는 자리."""
    count = 0
    for resource in module.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        for name, expression in (resource.get("expressions") or {}).items():
            if not isinstance(expression, dict):
                continue
            if not SENSITIVE_NAME.search(str(name)):
                continue
            if expression.get("constant_value") not in (None, ""):
                expression["constant_value"] = MASK
                count += 1
    for call in (module.get("module_calls") or {}).values():
        inner = (call or {}).get("module") or {}
        if isinstance(inner, dict):
            count += _redact_configuration(inner)
    return count


def redact_document(data: dict) -> tuple[dict, int]:
    """사본을 만들어 민감값을 가린다. (가린 사본, 가린 값 개수)"""
    if not isinstance(data, dict):
        raise ValueError("plan JSON 의 최상위가 객체가 아닙니다.")
    out = copy.deepcopy(data)
    masked = 0

    for item in out.get("resource_changes") or []:
        if not isinstance(item, dict):
            continue
        change = item.get("change") or {}
        masked += _redact_values(change, "before", "before_sensitive")
        masked += _redact_values(change, "after", "after_sensitive")

    fallback = _sensitivity_map(data)

    planned = out.get("planned_values")
    if isinstance(planned, dict) and isinstance(planned.get("root_module"), dict):
        masked += _walk_module(planned["root_module"], fallback, "after")

    prior = out.get("prior_state")
    if isinstance(prior, dict) and isinstance(prior.get("values"), dict):
        root = prior["values"].get("root_module")
        if isinstance(root, dict):
            masked += _walk_module(root, fallback, "before")

    configuration = out.get("configuration")
    if isinstance(configuration, dict) and isinstance(configuration.get("root_module"), dict):
        masked += _redact_configuration(configuration["root_module"])

    out["_redacted"] = {
        "note": "plan-guard 가 sensitive 표시와 이름 규칙으로 값을 가린 사본입니다.",
        "masked_values": masked,
        "mask": MASK,
    }
    return out, masked


def to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)
