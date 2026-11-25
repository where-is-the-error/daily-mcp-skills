"""MCP 배선 — 열 툴.

    TEST_RADAR_ROOT=/path/to/repo python -m test_radar.server

MCP 클라이언트 설정:

    {"mcpServers": {"test-radar": {
      "command": "python", "args": ["-m", "test_radar.server"],
      "env": {"TEST_RADAR_ROOT": "/path/to/repo"}}}}

읽기 전용이다. 저장소를 고치지 않고, 아무것도 실행하지 않는다 — 명령은 문자열로만 만든다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import diffparse, report, risk as risk_module
from .graph import load
from .plan import build as build_plan
from .select import build as build_set
from .store import STORE

DEFAULT_TOKENS = 1600
CHARS_PER_TOKEN = 4

LIMITS = (
    "판정하지 않음: 테스트가 실제로 통과하는지 · 실행 시간(모델) · 커버리지 % · "
    "동적 import 뒤의 간선 · 네이티브/설정 파일의 의미."
)

OVERVIEW = """test-radar — 바뀐 코드에 도달하는 테스트만 고른다.

1. open_repo 로 저장소를 읽습니다 (모듈·import 그래프·테스트 항목).
2. read_diff 로 unified diff 를 넣으면 변경집합 ref(cs-N) 를 돌려줍니다.
3. map_tests 로 도달하는 테스트를, impact_report 로 구멍·위험·계획을 한 번에 봅니다.
4. ci_plan 으로 CI 명령을, compare_selections 로 두 변경(PR 을 쪼갤 때)을 비교합니다.

읽는 것: 바뀐 파일, 파일 사이의 import, 테스트가 import 하는 심볼, 바뀐 줄이 속한 함수/클래스.
읽지 않는 것: 테스트 실행 결과, 커버리지 %, 동적 import 뒤의 간선, 설정 파일의 의미.

태도
· 근거가 있는 테스트만 '필수'로 고른다 — 직접 import · 심볼 참조 · 전이 import.
· 같은 디렉터리라는 이유만으로는 '참고'에만 넣는다.
· 확신이 없으면(테스트 설정 변경·파싱 실패·동적 import·선택 60% 초과) **전체 실행**을 권한다.
· 저장소를 고치지 않고, 명령을 실행하지 않는다. 명령은 문자열로만 만든다.

""" + LIMITS

mcp = MCPServer(
    name="test-radar",
    title="test-radar",
    version="0.1.0",
    instructions=(
        "바뀐 diff 로 '어디까지 테스트해야 하나'를 먼저 봅니다. "
        "open_repo 로 저장소를 읽어 ref(repo-N) 를 받고, read_diff 로 diff 를 넣어 변경집합(cs-N)을 만듭니다. "
        "map_tests 로 도달하는 테스트를, impact_report 로 테스트 근거 없는 변경과 위험을, "
        "ci_plan 으로 돌릴 명령을 봅니다. "
        "확신이 없으면 전체 실행을 권합니다. 저장소는 읽기만 하고 명령은 실행하지 않습니다. "
        "테스트가 통과하는지는 판정하지 않습니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("TEST_RADAR_ROOT")
    return Path(root) if root else None


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    root = _root()
    return (root / path) if root else path


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _finish(text: str, max_tokens: int | None) -> str:
    budget = DEFAULT_TOKENS if not max_tokens else max(1, int(max_tokens))
    limit = budget * CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n\n… ({budget} 토큰에서 잘랐습니다. max_tokens 를 늘리세요)"


@mcp.tool()
def open_repo(path: str = ".", max_tokens: int = DEFAULT_TOKENS) -> str:
    """저장소를 읽어 모듈·테스트·import 그래프를 만들고 ref(repo-N) 를 돌려준다.

    path: 저장소 루트(TEST_RADAR_ROOT 기준 상대경로 가능).
    """
    try:
        repo = load(_path(path))
        ref = STORE.add_repo(repo)
        info = repo.summary()
        lines = [
            f"📦 {info['root']}",
            f"   모듈 {info['modules']} (py {info['python']} · js/ts {info['javascript']})"
            f" · 테스트 {info['tests']}파일/{info['test_items']}항목",
            f"   ref: {ref}",
        ]
        if info["unresolved"]:
            lines.append(f"   해석 못 한 import 이름 {info['unresolved']}개 — 외부 패키지이거나 경로를 못 찾음")
        if info["parse_errors"]:
            lines.append(f"   ⚠️ 파싱 실패 {info['parse_errors']}개 — 그 파일의 간선은 비어 있습니다")
        if info["skipped"]:
            lines.append(f"   건너뜀 {info['skipped']}개")
        tests = repo.all_tests()
        if tests:
            preview = ", ".join(test.path for test in tests[:6])
            lines.append(f"   테스트 파일: {preview}{' …' if len(tests) > 6 else ''}")
        lines.append("다음: read_diff(diff=…) 로 변경집합을 만드세요.")
        lines.append(LIMITS)
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def read_diff(diff: str = "", path: str = "", repo_ref: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """unified diff 를 읽어 바뀐 파일·심볼과 변경집합 ref(cs-N) 를 돌려준다.

    diff: diff 본문. path: diff 파일 경로(diff 가 비었을 때). repo_ref: open_repo 가 준 ref.
    """
    try:
        if not diff and path:
            diff = _path(path).read_text(encoding="utf-8", errors="replace")
        if not diff.strip():
            raise ValueError("diff 가 비어 있습니다 — unified diff 본문이나 파일 경로를 주세요")
        repo = STORE.get_repo(repo_ref) if repo_ref else None
        if repo is None:
            raise ValueError("repo_ref 가 필요합니다 — open_repo 로 저장소를 먼저 읽으세요")
        parsed = diffparse.parse(diff)
        if not parsed.changes:
            raise ValueError("diff 에서 바뀐 파일을 읽지 못했습니다 — unified diff 인지 확인하세요")
        change_set = build_set(repo, parsed)
        ref = STORE.add_set(change_set)
        lines = [
            f"🧭 변경집합 {ref} · 파일 {len(change_set.views)}개",
            f"   +{sum(v.change.added_count() for v in change_set.views)}"
            f"/-{sum(v.change.removed_count() for v in change_set.views)}",
            "",
            report.change_lines(change_set),
            "",
            f"다음: map_tests('{ref}') · impact_report('{ref}') · ci_plan('{ref}')",
        ]
        if change_set.warnings:
            lines.insert(1, "   ⚠️ " + " / ".join(change_set.warnings[:3]))
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def list_changes(ref: str, include_hunks: bool = False, max_tokens: int = DEFAULT_TOKENS) -> str:
    """변경집합의 파일·바뀐 심볼·사라진 정의·인자 변경을 본다.

    ref: read_diff 가 준 변경집합 ref. include_hunks: 덩어리 원문까지.
    """
    try:
        change_set = STORE.get_set(ref)
        if not include_hunks:
            return _finish(report.change_lines(change_set), max_tokens)
        lines = [report.change_lines(change_set, include_hunks=True)]
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def map_tests(ref: str, limit: int = 40, max_tokens: int = DEFAULT_TOKENS) -> str:
    """바뀐 코드에 도달하는 테스트를 근거와 함께 고른다(L1 직접 · L2 전이 · L3 참고).

    ref: 변경집합 ref. limit: 보여줄 파일 수.
    """
    try:
        change_set = STORE.get_set(ref)
        text = "\n".join(report.summary_lines(change_set)) + "\n\n"
        text += report.tests_lines(change_set, limit=max(1, int(limit)))
        if change_set.fallback:
            text += "\n\n⚠️ 전체 실행 권고: " + " / ".join(change_set.fallback)
        text += "\n\n" + LIMITS
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def impact_report(ref: str, shards: int = 2, per_item_ms: int = 50,
                  max_tokens: int = DEFAULT_TOKENS) -> str:
    """선택·테스트 근거 없는 변경·위험 규칙·CI 계획을 한 장으로 본다.

    ref: 변경집합 ref. shards: 필수 테스트를 나눌 조각 수. per_item_ms: 시간 모델(항목당 ms).
    """
    try:
        change_set = STORE.get_set(ref)
        risks = risk_module.check(change_set)
        plan = build_plan(change_set, shards=shards, per_item_ms=per_item_ms)
        return _finish(report.impact_report(change_set, risks, plan), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def untested_surface(ref: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """바뀌었는데 어떤 테스트도 근거를 대지 못하는 파일·공개 심볼만 모아 본다.

    ref: 변경집합 ref.
    """
    try:
        change_set = STORE.get_set(ref)
        if not change_set.gaps:
            return "테스트 근거 없는 변경: 없음 (바뀐 파일마다 도달하는 테스트가 있습니다)"
        lines = [f"테스트 근거 없는 변경 {len(change_set.gaps)}건"]
        for gap in change_set.gaps:
            where = gap["path"] + (f":{gap['line']}" if gap.get("line") else "")
            lines.append(f"· {where} [{gap['kind']}] {gap['detail']}")
        lines.append("")
        lines.append("이 목록은 '테스트가 없다'는 뜻이지 '버그가 있다'는 뜻이 아닙니다. " + LIMITS)
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def ci_plan(ref: str, shards: int = 2, per_item_ms: int = 50,
            max_tokens: int = DEFAULT_TOKENS) -> str:
    """선택한 테스트를 CI 명령으로 바꾼다 — 조각·순서·전체 실행 대체안까지.

    ref: 변경집합 ref. shards: 조각 수(1~8). per_item_ms: 시간 모델(항목당 ms).
    """
    try:
        change_set = STORE.get_set(ref)
        plan = build_plan(change_set, shards=shards, per_item_ms=per_item_ms)
        lines = report.plan_lines(plan, change_set)
        lines.append("")
        lines.append("명령은 실행하지 않았습니다 — 문자열만 만들었습니다.")
        lines.append(LIMITS)
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_selections(ref_a: str, ref_b: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """두 변경집합의 테스트 선택을 비교한다 — PR 을 쪼갤 때 겹치는 테스트를 본다.

    ref_a · ref_b: 변경집합 ref.
    """
    try:
        first = STORE.get_set(ref_a)
        second = STORE.get_set(ref_b)
        a = set(first.selections)
        b = set(second.selections)
        both = sorted(a & b)
        lines = [
            f"↔ {ref_a} ({len(a)}파일) · {ref_b} ({len(b)}파일)",
            f"   겹침 {len(both)} · {ref_a}만 {len(a - b)} · {ref_b}만 {len(b - a)}",
        ]
        if both:
            lines.append("   겹침: " + ", ".join(both[:10]) + (" …" if len(both) > 10 else ""))
        only_a = sorted(a - b)
        only_b = sorted(b - a)
        if only_a:
            lines.append(f"   {ref_a}만: " + ", ".join(only_a[:8]))
        if only_b:
            lines.append(f"   {ref_b}만: " + ", ".join(only_b[:8]))
        union = a | b
        lines.append(f"   합쳐서 돌릴 테스트: {len(union)}파일 "
                     f"· {sum((first.repo.test(p).weight() if first.repo.test(p) else 1) for p in union)}항목")
        if first.fallback or second.fallback:
            lines.append("   ⚠️ 전체 실행 권고가 있는 변경집합이 있습니다: "
                         + ", ".join([ref for ref, cs in ((ref_a, first), (ref_b, second)) if cs.fallback]))
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog(rule: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """규칙 목록(22종)과 각 규칙이 무엇을 보는지. rule 을 주면 하나만.

    rule: 규칙 id (예: test-config-changed).
    """
    rows = risk_module.catalog(rule)
    if not rows:
        return f"⚠️ 그런 규칙이 없습니다: {rule}"
    lines = [f"규칙 {len(rows)}종"]
    for row in rows:
        lines.append(f"[{row['severity']}] {row['rule']} — {row['title']}")
        lines.append(f"    {row['doc']}")
    return _finish("\n".join(lines), max_tokens)


@mcp.tool()
def overview() -> str:
    """이 서버가 무엇을 하고 무엇을 판정하지 않는지."""
    return OVERVIEW


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="test-radar MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="저장소 기준 디렉터리 (TEST_RADAR_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["TEST_RADAR_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
