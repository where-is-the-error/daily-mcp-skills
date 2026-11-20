"""기준선(baseline) 저장과 비교 — "고쳤다"를 말이 아니라 숫자로 확인한다.

브라우저 기반 도구는 지금 화면만 보여 준다. 정적 검사는 지문(fingerprint)을 남길 수 있어서,
고치기 전후를 **없어진 것 / 남은 것 / 새로 생긴 것**으로 나눌 수 있다.
Baseline 은 그냥 JSON 한 장이라 커밋해 두면 CI 에서도 같은 판정이 나온다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .audit import PageAudit, SiteAudit
from .rules import IMPACT_LABEL, IMPACT_ORDER

__all__ = [
    "DEFAULT_ENV",
    "home",
    "resolve",
    "flatten",
    "save",
    "load",
    "compare",
    "render_compare",
]

DEFAULT_ENV = "A11Y_LENS_HOME"
_SAFE = re.compile(r"[^0-9A-Za-z_.\-가-힣]")


def home() -> Path:
    import os

    base = os.environ.get(DEFAULT_ENV)
    root = Path(base) if base else Path.home() / ".local" / "share" / "a11y-lens"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve(name: str) -> Path:
    """이름 하나만 받는다 — 경로가 섞이면 홈 밖으로 나가지 못하게 지운다."""
    stem = _SAFE.sub("-", (name or "baseline").strip()).replace("..", "-").strip(".-") or "baseline"
    if stem.endswith(".json"):
        stem = stem[:-5]
    return home() / f"{stem}.json"


def flatten(audit: PageAudit | SiteAudit) -> list[dict]:
    items: list[dict] = []
    pages = audit.pages if isinstance(audit, SiteAudit) else [audit]
    for page in pages:
        for violation in page.violations:
            items.append(
                {
                    "fingerprint": violation.fingerprint,
                    "rule": violation.rule.id,
                    "impact": violation.impact,
                    "selector": violation.selector,
                    "file": violation.file or page.path,
                    "line": violation.line,
                    "snippet": violation.snippet,
                    "message": violation.message,
                }
            )
    return items


def save(name: str, audit: PageAudit | SiteAudit, target: str | None = None) -> Path:
    path = Path(target) if target else resolve(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": "a11y-lens",
        "version": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": audit.root if isinstance(audit, SiteAudit) else audit.path,
        "count": len(flatten(audit)),
        "violations": flatten(audit),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load(name: str, target: str | None = None) -> dict:
    path = Path(target) if target else resolve(name)
    if not path.exists():
        raise FileNotFoundError(f"기준선이 없습니다: {path} — 먼저 mode=\"save\" 로 저장하세요.")
    return json.loads(path.read_text(encoding="utf-8"))


def compare(baseline: dict, audit: PageAudit | SiteAudit) -> dict:
    before = baseline.get("violations", [])
    after = flatten(audit)
    before_counter = Counter(item["fingerprint"] for item in before)
    after_counter = Counter(item["fingerprint"] for item in after)

    resolved = []
    remaining = []
    for item in before:
        fingerprint = item["fingerprint"]
        if after_counter[fingerprint] > 0:
            after_counter[fingerprint] -= 1
            remaining.append(item)
        else:
            resolved.append(item)

    new = []
    before_counter_rest = Counter(item["fingerprint"] for item in before)
    for item in after:
        fingerprint = item["fingerprint"]
        if before_counter_rest[fingerprint] > 0:
            before_counter_rest[fingerprint] -= 1
        else:
            new.append(item)

    return {
        "baseline_count": len(before),
        "current_count": len(after),
        "resolved": resolved,
        "remaining": remaining,
        "new": new,
        "ok": not new,
    }


def _row(item: dict) -> str:
    label = IMPACT_LABEL.get(item.get("impact", ""), item.get("impact", ""))
    where = item.get("file") or ""
    if item.get("line"):
        where += f":{item['line']}"
    return f"- {label} · `{item.get('rule')}` · `{item.get('selector')}` · {where}"


def render_compare(result: dict, baseline: dict, title: str = "") -> str:
    head = f"## 고친 뒤 확인{f' · {title}' if title else ''}"
    delta = result["baseline_count"] - result["current_count"]
    sign = "−" if delta > 0 else ("+" if delta < 0 else "±")
    lines = [head]
    lines.append(
        f"- 기준선 {result['baseline_count']}건 → 지금 {result['current_count']}건 (**{sign}{abs(delta)}**)"
    )
    lines.append(
        f"- 없어짐 **{len(result['resolved'])}** · 남음 **{len(result['remaining'])}** · 새로 생김 **{len(result['new'])}**"
    )
    if result["ok"] and not result["remaining"]:
        lines.append("")
        lines.append("✅ 기준선의 위반이 모두 사라졌습니다. 이 상태를 새 기준선으로 저장해 두세요.")
    elif result["ok"]:
        lines.append("")
        lines.append("✅ 새로 생긴 위반은 없습니다 (남은 위반은 아래).")
    else:
        lines.append("")
        lines.append("⚠️ 새로 생긴 위반이 있습니다 — 고치다 다른 곳을 망가뜨렸는지 확인하세요.")
    for key, label in (("new", "새로 생김"), ("remaining", "남음"), ("resolved", "없어짐")):
        if not result[key]:
            continue
        lines.append("")
        lines.append(f"### {label} ({len(result[key])})")
        for item in sorted(result[key], key=lambda i: IMPACT_ORDER.get(i.get("impact", ""), 9))[:12]:
            lines.append(_row(item))
        if len(result[key]) > 12:
            lines.append(f"- … {len(result[key]) - 12}건 더")
    saved = baseline.get("saved_at")
    if saved:
        lines.append("")
        lines.append(f"> 기준선 저장 시각: {saved}")
    return "\n".join(lines)
