"""MCP 배선 — 여덟 툴.

    PLAN_GUARD_ROOT=/path/to/infra python -m plan_guard.server

MCP 클라이언트 설정:

    {"mcpServers": {"plan-guard": {
      "command": "python", "args": ["-m", "plan_guard.server"],
      "env": {"PLAN_GUARD_ROOT": "/Users/me/infra"}}}}
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import report
from . import risks
from .compare import compare
from .plan import PlanError, load_plan
from .redact import redact_document, to_json

# 대략 4글자 = 1토큰. 넘치면 잘라서 알려 준다.
DEFAULT_TOKENS = 1500
CHARS_PER_TOKEN = 4

mcp = MCPServer(
    name="plan-guard",
    title="plan-guard",
    version="0.1.0",
    instructions=(
        "terraform plan JSON(`terraform show -json tfplan`)을 apply 전에 읽는 서버입니다. "
        "read_plan 으로 무엇이 바뀌는지 보고, risk_report 로 지워지는 것·열리는 포트·공개되는 버킷을 확인하고, "
        "apply_order·rollback_plan 으로 순서와 되돌리기를 준비하세요. "
        "판정하지 않는 것: 비용, 실제 데이터 크기, apply 시점에 정해지는 값, provider 가 sensitive 로 표시하지 않은 비밀. "
        "plan 파일에는 민감값이 평문으로 들어 있으니 공유 전에 redact_plan 을 쓰세요."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("PLAN_GUARD_ROOT")
    return Path(root) if root else None


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _finish(text: str, max_tokens: int | None) -> str:
    budget = DEFAULT_TOKENS if not max_tokens else max(1, int(max_tokens))
    limit = budget * CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n\n… ({budget} 토큰에서 잘랐습니다. max_tokens 를 늘리세요)"


@mcp.tool()
def read_plan(source: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """plan 을 한 화면으로 요약한다 — 무엇이 몇 개 바뀌고, 삭제·재생성이 몇 개인지.

    source: plan JSON 파일 경로(PLAN_GUARD_ROOT 기준) 또는 JSON 문자열.
    """
    try:
        plan = load_plan(source, base_dir=_root())
        text = report.summary(plan) + "\n\n" + report.quick(plan)
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def list_changes(source: str, kind: str = "", max_items: int = 20, max_tokens: int = DEFAULT_TOKENS) -> str:
    """바뀌는 리소스 목록 — 액션과 바뀐 속성 개수. ref(r1…)로 뒤에서 지목할 수 있다.

    kind: create | update | replace | delete 또는 리소스 타입(aws_db_instance 등). 비우면 전부.
    """
    try:
        plan = load_plan(source, base_dir=_root())
        return _finish(report.changes(plan, kind_filter=kind, max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def diff_resource(source: str, address: str, max_items: int = 14, max_tokens: int = DEFAULT_TOKENS) -> str:
    """리소스 하나의 속성 diff — 목록 안쪽(보안 그룹 규칙 등)까지 짝지어 보여 준다.

    address: `aws_db_instance.main` 처럼. list_changes 의 주소를 그대로 쓰면 된다.
    민감 표시된 값은 «민감» 으로 가린다.
    """
    try:
        plan = load_plan(source, base_dir=_root())
        return _finish(report.diff(plan, address, max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def risk_report(source: str, severity: str = "", max_items: int = 14, max_tokens: int = DEFAULT_TOKENS) -> str:
    """apply 전에 봐야 할 것 — 판정(보류/주의/통과), 근거 값, 고치는 방법.

    severity: 치명 | 심각 | 보통 | 참고 — 그 등급 이상만 보여 준다.
    """
    try:
        plan = load_plan(source, base_dir=_root())
        return _finish(report.risk(plan, severity=severity, max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def apply_order(source: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """적용·삭제 순서와 참조 — 지우는 리소스를 아직 살아 있는 것이 참조하는지."""
    try:
        plan = load_plan(source, base_dir=_root())
        return _finish(report.order(plan), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rollback_plan(source: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """되돌리기 계획 — apply 전 백업, 실패했을 때, 끝났을 때. 명령은 제안이고 실행은 사람이 한다."""
    try:
        plan = load_plan(source, base_dir=_root())
        return _finish(report.rollback(plan), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_plans(before: str, after: str, max_items: int = 12, max_tokens: int = DEFAULT_TOKENS) -> str:
    """plan 두 개 비교 — 고친 뒤 무엇이 약해졌고 무엇이 남았는지(치명 3 → 0 같은 변화)."""
    try:
        a = load_plan(before, base_dir=_root())
        b = load_plan(after, base_dir=_root())
        return _finish(compare(a, b).render(max_items=int(max_items)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def redact_plan(source: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """민감값을 «민감» 으로 가린 공유용 사본(JSON)을 만든다 — 이슈·채팅에 plan 을 붙이기 전에.

    원본 파일은 건드리지 않는다. provider 가 sensitive 로 표시하지 않은 값은 가려지지 않는다.
    """
    try:
        import json

        plan = load_plan(source, base_dir=_root())
        raw = json.loads(Path(plan.source).read_text(encoding="utf-8")) if plan.source else json.loads(source)
        redacted, masked = redact_document(raw)
        text = f"# 민감값 {masked}개를 «민감» 으로 가렸습니다 (원본은 그대로).\n" + to_json(redacted)
        return _finish(text, max_tokens)
    except PlanError as exc:
        return _fail(exc)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog() -> str:
    """규칙 목록과 이 도구가 판정하지 않는 것 — 결과를 해석하기 전에 읽으세요."""
    lines = [f"# 규칙 {len(risks.CATALOG)}종"]
    for rule in risks.CATALOG:
        lines.append(f"- {rule.severity} · {rule.rule_id} — {rule.title}: {rule.why}")
    lines.append("")
    lines.append("## 판정하지 않는 것")
    lines.append("- 비용 변화(요금표 없음) · 실제 데이터 크기와 소요 시간")
    lines.append("- apply 시점에 정해지는 값(plan 에 '(적용 후 결정)' 으로 표시)")
    lines.append("- provider 가 sensitive 표시를 하지 않은 비밀값")
    lines.append("- 이미 있던 위험(바뀐 것만 봅니다) · refresh 없는 plan 의 drift")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="plan-guard MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="plan 파일 기준 디렉터리 (PLAN_GUARD_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["PLAN_GUARD_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
