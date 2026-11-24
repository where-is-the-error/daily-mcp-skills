"""MCP 배선 — 아홉 툴.

    SHEET_GUARD_ROOT=/path/to/data python -m sheet_guard.server

MCP 클라이언트 설정:

    {"mcpServers": {"sheet-guard": {
      "command": "python", "args": ["-m", "sheet_guard.server"],
      "env": {"SHEET_GUARD_ROOT": "/Users/me/data"}}}}
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import report
from .apply import apply_plan as _apply, write_changelog, write_csv, write_quarantine
from .compare import compare
from .markdown import to_markdown as _to_markdown
from .plan import build_plan
from .rules import check, counts
from .store import STORE, file_fingerprint
from .table import load_table
from .types import KIND_LABELS

DEFAULT_TOKENS = 1500
CHARS_PER_TOKEN = 4

mcp = MCPServer(
    name="sheet-guard",
    title="sheet-guard",
    version="0.1.0",
    instructions=(
        "표(CSV·엑셀)를 읽고, LLM에 넣거나 엑셀에서 쓰기 전에 깨질 곳을 먼저 알려 주는 서버입니다. "
        "read_table 로 파일을 읽어 ref를 받고, find_problems 로 문제 목록을, clean_plan 으로 고칠 순서를 봅니다. "
        "apply_plan 은 원본을 건드리지 않고 정리본 CSV와 바뀐 곳 기록(changelog)을 새로 씁니다. "
        "판정하지 않는 것: 값의 의미·통계적 이상값, 엑셀 수식의 재계산, 셀 서식. "
        "앞자리 0 복원은 자릿수 추정이므로 확신도가 낮게 표시됩니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("SHEET_GUARD_ROOT")
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


def _load(path: str, sheet: str = ""):
    resolved = _path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일이 없습니다: {resolved}")
    table = load_table(resolved, sheet=sheet or None)
    ref = STORE.put(table, file_fingerprint(resolved))
    return table, ref


@mcp.tool()
def read_table(path: str, sheet: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """표 파일을 읽어 인코딩·머리글·열 요약과 ref를 돌려준다.

    path: CSV/.xlsx 경로(SHEET_GUARD_ROOT 기준).
    sheet: 엑셀일 때 시트 이름(비우면 첫 시트).
    """
    try:
        table, ref = _load(path, sheet)
        header = f"[ref {ref}]"
        return _finish(report.table_summary(table).replace("📄", f"📄 {header}", 1), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def profile_columns(ref: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    """열마다 값의 종류·채움률·서로 다른 값 개수·예시."""
    try:
        table = STORE.get(ref)
        lines = [f"{ref} — {table.source} · {len(table.data_rows):,}행 × {table.width}열", ""]
        for stat in table.stats():
            data = stat.summary()
            kinds = ", ".join(f"{KIND_LABELS.get(k, k)} {v}" for k, v in data["kinds"].items())
            line = (f"{data['name']} [{data['kind']}] 채움 {data['fill'] * 100:.0f}% · {data['distinct']:,}종 · {kinds}")
            if data["date_patterns"]:
                line += " · 날짜 " + ", ".join(f"{p} {n}" for p, n in data["date_patterns"].items())
            if data["units"]:
                line += " · 단위 " + ", ".join(f"{u} {n}" for u, n in data["units"].items())
            if data["widths"]:
                line += " · 자릿수 " + ", ".join(f"{w}자리 {n}" for w, n in data["widths"].items())
            if data["numbers"]:
                low, high = data["numbers"]
                line += f" · 범위 {low:g}~{high:g}"
            example = data["examples"].get(data["kind"])
            if example:
                line += f" · 예: {example}"
            lines.append(line)
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_problems(ref: str, key: str = "", severity: str = "", max_items: int = 12,
                  max_tokens: int = DEFAULT_TOKENS) -> str:
    """규칙 위반 목록 — 행 참조와 고치기 종류까지.

    key: 키 열 이름을 주면 중복 키도 확인한다.
    severity: error|warn|info 중 하나만 보기.
    """
    try:
        table = STORE.get(ref)
        findings = check(table, key=key)
        text = report.problems_view(findings, max_items=int(max_items), severity=severity)
        tally = counts(findings)
        text += f"\n\n{report.LIMITS}"
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def clean_plan(ref: str, key: str = "", only: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """고칠 순서·확신도·이유. 실제로 쓰지는 않는다.

    only: 규칙 id 쉼표 목록(비우면 자동으로 고칠 수 있는 전부).
    """
    try:
        table = STORE.get(ref)
        findings = check(table, key=key)
        limit = tuple(x.strip() for x in only.split(",") if x.strip())
        plan = build_plan(table, findings, only=limit)
        return _finish(report.plan_view(plan), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def apply_plan(ref: str, out: str, changelog: str = "", key: str = "", only: str = "",
               max_tokens: int = DEFAULT_TOKENS) -> str:
    """정리본 CSV와 바뀐 곳 기록을 새로 쓴다 — 원본 파일은 건드리지 않는다.

    out: 정리본 경로. changelog: 바뀐 곳 기록 경로(비우면 out 옆 .changes.csv).
    """
    try:
        table = STORE.get(ref)
        findings = check(table, key=key)
        limit = tuple(x.strip() for x in only.split(",") if x.strip())
        plan = build_plan(table, findings, only=limit)
        applied = _apply(table, plan)
        out_path = write_csv(applied.table, _path(out))
        log_path = _path(changelog) if changelog else out_path.with_name(out_path.stem + ".changes.csv")
        write_changelog(applied, log_path)
        text = report.plan_view(plan) + "\n\n" + report.applied_view(applied, out_path=str(out_path))
        text += f"\n   바뀐 곳 기록: {log_path}"
        ragged = write_quarantine(applied, out_path.with_name(out_path.stem + ".ragged.csv"), table.column_names)
        if ragged:
            text += f"\n   격리한 행: {ragged}"
        clean_ref = STORE.put(applied.table, "")
        text += f"\n   정리본 ref: {clean_ref} (compare_tables 로 원본과 대조)"
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def to_markdown(ref: str, max_rows: int = 30, clean: bool = False, max_tokens: int = DEFAULT_TOKENS) -> str:
    """LLM에 넣기 좋은 마크다운 표로 바꾼다.

    clean: 정리 계획을 먼저 적용한 표로 출력.
    """
    try:
        table = STORE.get(ref)
        if clean:
            applied = _apply(table, build_plan(table, check(table)))
            table = applied.table
        return _finish(_to_markdown(table, max_rows=int(max_rows)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_tables(ref_a: str, ref_b: str, key: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """두 표를 행 참조(또는 key 열)로 짝지어 없어진 행·바뀐 칸·사라진 값을 센다."""
    try:
        before = STORE.get(ref_a)
        after = STORE.get(ref_b)
        return _finish(report.diff_view(compare(before, after, key=key or None)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog(rule: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """규칙 목록, 또는 규칙 하나의 설명(왜 문제인지·어떻게 고치는지)."""
    try:
        return _finish(report.catalog_view(rule), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def overview() -> str:
    """이 서버가 무엇을 하고 무엇을 판정하지 않는지."""
    return report.OVERVIEW


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sheet-guard MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="표 파일 기준 디렉터리 (SHEET_GUARD_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["SHEET_GUARD_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
