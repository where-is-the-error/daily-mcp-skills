"""MCP 배선 — 일곱 툴: 접근성 트리 스냅샷 + 정적 검사 + 고치기 순서 + 전후 비교.

stdio 로 실행:

    A11Y_LENS_ROOT=/path/to/site python -m a11y_lens.server

MCP 클라이언트 설정:

    {"mcpServers": {"a11y-lens": {
      "command": "python", "args": ["-m", "a11y_lens.server"],
      "env": {"A11Y_LENS_ROOT": "/Users/me/project"}}}}
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import store
from .audit import (
    LIMITS,
    load_document,
)
from .audit import (
    audit_page as run_page_audit,
    audit_site as run_site_audit,
    payload_json,
    render_page,
    render_plan,
    render_site,
)
from .rules import IMPACT_LABEL, IMPACT_ORDER, RULES
from .snapshot import build
from .tokens import trim_to_tokens

DEFAULT_BUDGET = 1400

mcp = MCPServer(
    name="a11y-lens",
    title="a11y-lens",
    version="0.1.0",
    instructions=(
        "브라우저 없이 HTML 을 접근성 트리로 바꿔 보여 주고, WCAG 조항에 붙여 위반을 짚는 서버입니다. "
        "snapshot_page 로 구조를 보고, audit_page/audit_site 로 위반을 모으고, "
        "fix_plan 으로 고치는 순서를 받고, verify_fixes 로 고친 뒤 없어진 것·남은 것·새로 생긴 것을 확인하세요. "
        "색 대비·터치 타깃·키보드 순서는 정적으로 판정하지 않습니다 — 그건 브라우저 도구의 일입니다."
    ),
)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _budget(value: int | None) -> int:
    return DEFAULT_BUDGET if value is None else int(value)


def _finish(text: str, max_tokens: int) -> str:
    trimmed, cut = trim_to_tokens(text, max_tokens)
    if cut:
        trimmed += f"\n\n… ({max_tokens} 토큰에서 잘랐습니다)"
    return trimmed


def _root() -> Path | None:
    root = os.environ.get("A11Y_LENS_ROOT")
    return Path(root) if root else None


def _rule_ids(spec: str) -> list[str]:
    if not spec or not spec.strip():
        return []
    return [part.strip() for part in re.split(r"[,\s]+", spec) if part.strip()]


@mcp.tool()
def snapshot_page(
    source: str,
    depth: int = 0,
    max_nodes: int = 200,
    ref: str = "",
    show_source: bool = True,
) -> str:
    """HTML 을 접근성 트리(화면 낭독기가 보는 구조)로 보여 준다. ref·줄 번호가 붙는다.

    source: 파일 경로 또는 HTML 문자열. depth=0 은 무제한, depth=2 면 두 단계까지.
    ref="e7" 을 주면 그 요소 하위만 본다. 화면(픽셀)이 아니라 의미 구조라는 점이 스크린샷과 다르다.
    """
    try:
        doc = load_document(source, base_dir=_root())
        view = build(doc, depth=int(depth), max_nodes=int(max_nodes), root_ref=ref)
        return view.render(show_source=bool(show_source))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_in_snapshot(source: str, text: str = "", regex: str = "", max_results: int = 10) -> str:
    """스냅샷 안에서 글자·정규식으로 노드를 찾는다 — 전체를 다 읽지 않고 위치만 볼 때.

    돌려주는 것은 `ref` 와 루트부터의 경로다. 그 ref 로 snapshot_page(ref="e12") 를 부르면
    그 부분만 다시 볼 수 있다(토큰 절약).
    """
    if not text and not regex:
        return "⚠️ text 또는 regex 중 하나를 주세요."
    try:
        pattern = re.compile(regex, re.I) if regex else None
    except re.error as exc:
        return _fail(ValueError(f"정규식이 올바르지 않습니다: {exc}"))
    try:
        doc = load_document(source, base_dir=_root())
        view = build(doc, max_nodes=5000)
    except Exception as exc:
        return _fail(exc)

    needle = text.lower()
    matches = []
    for entry in view.entries:
        haystack = f"{entry.role} {entry.name}".lower()
        hit = pattern.search(haystack) if pattern is not None else (needle in haystack)
        if hit:
            matches.append(entry)
    if not matches:
        return f'"{text or regex}" 에 해당하는 노드가 없습니다. (노드 {len(view.entries)}개를 뒤졌습니다)'
    lines = [f"# {len(matches)}개 중 {min(len(matches), max_results)}개"]
    for entry in matches[: max(1, int(max_results))]:
        path = " > ".join(entry.path[-3:]) if entry.path else "document"
        lines.append(f"- ref={entry.ref} · {entry.label()} · L{entry.line}")
        lines.append(f"  경로: {path}")
    if len(matches) > max_results:
        lines.append(f"# … {len(matches) - max_results}개 더 (max_results 로 늘릴 수 있습니다)")
    return "\n".join(lines)


@mcp.tool()
def audit_page(source: str, rules: str = "", max_per_rule: int = 30, format: str = "markdown") -> str:
    """한 페이지를 정적 규칙으로 검사한다 — WCAG 조항·원본 줄 번호·고치는 방법까지.

    rules: 쉼표로 규칙 id 만 골라 검사 (예: "image-alt,form-label"). 비우면 전체.
    format="json" 이면 기계가 읽는 형태.
    """
    try:
        audit = audit_page_fn(source, rules, max_per_rule)
    except Exception as exc:
        return _fail(exc)
    if format.lower() == "json":
        return payload_json(audit)
    return render_page(audit, max_per_rule=max(0, int(max_per_rule)))


def audit_page_fn(source: str, rules: str = "", max_per_rule: int = 30):
    return run_page_audit(
        source,
        rule_ids=_rule_ids(rules),
        max_per_rule=int(max_per_rule),
        base_dir=_root(),
    )


@mcp.tool()
def audit_site(directory: str, pattern: str = "**/*.html", max_pages: int = 40, max_groups: int = 15) -> str:
    """폴더 전체를 검사한다. 같은 템플릿에서 반복되는 위반은 하나로 묶어 '몇 쪽에서 나는지'를 보여 준다.

    directory: 폴더 경로 (상대 경로면 A11Y_LENS_ROOT 기준).
    """
    try:
        target = Path(directory)
        if not target.is_absolute() and _root() is not None and (_root() / directory).exists():
            target = _root() / directory
        site = run_site_audit(target, pattern=pattern, max_pages=int(max_pages))
        return render_site(site, max_groups=int(max_groups))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def fix_plan(source: str, max_steps: int = 8) -> str:
    """고치는 순서 — 치명 → 심각 → 보통, 같은 등급이면 여러 번 나온 것부터. 단계마다 확인 방법까지."""
    try:
        audit = audit_page_fn(source)
        if not audit.violations:
            return f"✅ {audit.path}: 정적으로 판정 가능한 위반이 없습니다. 점수 {audit.score}/100."
        return render_plan(audit, max_steps=int(max_steps))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def verify_fixes(source: str, baseline: str = "", mode: str = "check", format: str = "markdown") -> str:
    """고친 뒤 확인 — mode="save" 로 기준선을 저장하고, 고친 다음 mode="check" 로 비교한다.

    돌려주는 것: 없어진 위반 / 남은 위반 / **새로 생긴 위반**(고치다 망가뜨린 곳).
    baseline: 기준선 이름 (기본: 페이지 파일 이름). site=True 면 폴더 전체.
    """
    name = baseline or Path(source.strip()).stem or "baseline"
    try:
        audit = audit_page_fn(source)
        if mode.lower() == "save":
            path = store.save(name, audit)
            return (
                f"💾 기준선 저장: `{path}`\n"
                f"- {audit.path} · 위반 {len(audit.violations)}건 · 점수 {audit.score}/100\n"
                f"- 이제 고친 뒤 verify_fixes(mode=\"check\") 로 없어진 것/남은 것을 확인하세요."
            )
        data = store.load(name)
        result = store.compare(data, audit)
        if format.lower() == "json":
            payload = {
                "ok": result["ok"],
                "baseline_count": result["baseline_count"],
                "current_count": result["current_count"],
                "resolved": result["resolved"],
                "remaining": result["remaining"],
                "new": result["new"],
            }
            return payload_json(type("X", (), {"to_dict": lambda self: payload})())  # type: ignore[arg-type]
        return store.render_compare(result, data, title=audit.path)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def overview(max_tokens: int = 900) -> str:
    """이 서버가 무엇을 판정하고 무엇을 판정하지 않는지 — 규칙 목록과 한계."""
    rows = []
    for rule in RULES:
        rows.append(
            f"| `{rule.id}` | {rule.title} | {rule.wcag} {rule.level} | {IMPACT_LABEL.get(rule.impact, rule.impact)} |"
        )
    text = "\n".join(
        [
            "# a11y-lens — 브라우저 없이 접근성 트리와 위반을 본다",
            "",
            "**일곱 툴**: `snapshot_page` · `find_in_snapshot` · `audit_page` · `audit_site` · `fix_plan` · `verify_fixes` · `overview`",
            "",
            "## 왜 브라우저 없이",
            "정적 파서라서 **원본 줄 번호**와 **CSS 선택자**를 줄 수 있습니다. 브라우저 기반 도구는",
            "지금 화면의 스냅샷은 주지만 '어느 파일 몇 번째 줄'은 주지 못합니다. 대신 렌더링 결과는 못 봅니다.",
            "",
            "## 판정하는 것 (규칙 " + str(len(RULES)) + "종, WCAG 조항·등급 표기)",
            "| 규칙 | 내용 | WCAG | 등급 |",
            "|---|---|---|---|",
            *rows,
            "",
            "## 판정하지 않는 것 (계산한 척하지 않습니다)",
            "색 대비 · 터치 타깃 크기 · 포커스 순서/키보드 함정 · CSS 로 만든 글자(::before) ·",
            "shadow DOM · iframe 내부 · JS 로 그린 DOM. 이 항목은 브라우저 도구(예: Chrome DevTools MCP)의 몫입니다.",
            "",
            "## 한 번에 흐르는 순서",
            '1. `snapshot_page("index.html")` — 구조를 본다',
            '2. `audit_page("index.html")` — 위반을 모은다',
            '3. `fix_plan("index.html")` — 위에서부터 고친다',
            '4. 고치기 전에 `verify_fixes("index.html", mode="save")`, 고친 뒤 `verify_fixes("index.html")`',
            "",
            f"> {LIMITS}",
        ]
    )
    return _finish(text, _budget(max_tokens))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="a11y-lens-mcp", description=__doc__)
    parser.add_argument("--root", default=None, help="상대 경로의 기준 폴더 (기본: 현재 폴더)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["A11Y_LENS_ROOT"] = str(Path(args.root).resolve())
    mcp.run()


if __name__ == "__main__":
    main()


_ = IMPACT_ORDER
