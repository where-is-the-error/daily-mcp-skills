"""MCP 배선 — 열 툴.

    LOG_TRIAGE_ROOT=/path/to/logs python -m log_triage.server

MCP 클라이언트 설정:

    {"mcpServers": {"log-triage": {
      "command": "python", "args": ["-m", "log_triage.server"],
      "env": {"LOG_TRIAGE_ROOT": "/Users/me/logs"}}}}

읽기 전용이다. 파일을 고치지 않고, 마스킹본만 새 경로에 쓴다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import report
from .compare import compare
from .parse import load_log, read_whole
from .rates import analyze as analyze_rates
from .redact import redact_text
from .rules import RULES, catalog as rule_catalog, check, counts
from .search import find
from .signature import cluster
from .stack import stack_report as build_stack_report
from .store import STORE
from .timeline import build as build_timeline

DEFAULT_TOKENS = 1600
CHARS_PER_TOKEN = 4

mcp = MCPServer(
    name="log-triage",
    title="log-triage",
    version="0.1.0",
    instructions=(
        "로그 파일 하나로 '무엇이·언제부터·얼마나' 를 먼저 봅니다. "
        "read_logs 로 파일을 읽어 ref 를 받고, signature_report 로 같은 메시지를 묶고, "
        "rate_report 로 폭주·끊김을, compare_logs 로 before/after 를 분당 비율로 비교하고, "
        "stack_report 로 터진 위치를, timeline 으로 첫 오류를 봅니다. "
        "redact_secrets 는 비밀·개인정보를 지운 사본을 만들고 남은 것 0을 확인합니다. "
        "판정하지 않는 것: 로그 내용의 사실 여부, 지표가 정상인지, 장애의 원인, 배포 이력. "
        "파일은 읽기만 합니다."
    ),
)


def _root() -> Path | None:
    root = os.environ.get("LOG_TRIAGE_ROOT")
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


def _load(path: str, assume_year: int = 2026):
    resolved = _path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일이 없습니다: {resolved}")
    if not resolved.is_file():
        raise IsADirectoryError(f"파일이 아닙니다: {resolved}")
    log = load_log(resolved, assume_year=assume_year)
    return log, STORE.put(log)


def _get(ref: str):
    log = STORE.get(ref)
    return log


def _check_stale(ref: str) -> str:
    if STORE.source_changed(ref):
        return "   ⚠️ 파일이 읽은 뒤에 바뀌었습니다 — read_logs 로 다시 읽으세요.\n"
    return ""


@mcp.tool()
def read_logs(path: str, assume_year: int = 2026, max_tokens: int = DEFAULT_TOKENS) -> str:
    """로그 파일을 읽어 인코딩·시각·레벨·구간과 ref 를 돌려준다.

    path: 로그 파일 경로(LOG_TRIAGE_ROOT 기준).
    assume_year: 연도가 없는 표기(syslog 등)에 쓸 연도.
    """
    try:
        log, ref = _load(path, assume_year)
        text = report.table_summary(log, ref=ref)
        clusters = cluster(log)
        text += "\n\n" + report.signature_view(clusters, log, limit=5)
        text += f"\n\n{report.LIMITS}"
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def signature_report(ref: str, limit: int = 12, max_tokens: int = DEFAULT_TOKENS) -> str:
    """같은 메시지를 하나로 묶어 개수·비율·처음/마지막 시각을 보여 준다."""
    try:
        log = _get(ref)
        return _finish(_check_stale(ref) + report.signature_view(cluster(log), log, limit=int(limit)),
                       max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rate_report(ref: str, bucket_seconds: int = 60, max_tokens: int = DEFAULT_TOKENS) -> str:
    """구간별 개수·폭주·끊김·같은 초 반복·시각 역행.

    bucket_seconds: 구간 길이(초). 60이면 분당.
    """
    try:
        log = _get(ref)
        clusters = cluster(log)
        rate = analyze_rates(log, bucket_seconds=int(bucket_seconds),
                             templates={c.signature: c.template for c in clusters})
        return _finish(_check_stale(ref) + report.rate_view(rate, log), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def compare_logs(ref_before: str, ref_after: str, limit: int = 10,
                 max_tokens: int = DEFAULT_TOKENS) -> str:
    """두 창을 분당 비율로 비교 — 새로 생긴/사라진/늘어난 서명."""
    try:
        before = _get(ref_before)
        after = _get(ref_after)
        return _finish(report.compare_view(compare(before, after), limit=int(limit)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def stack_report(ref: str, limit: int = 8, max_tokens: int = DEFAULT_TOKENS) -> str:
    """스택에서 가장 안쪽 프레임·예외 종류·인과 깊이 (Python/Java/Node/Go)."""
    try:
        log = _get(ref)
        return _finish(_check_stale(ref) + report.stack_view(
            build_stack_report(log, cluster(log)), log, limit=int(limit)), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def timeline(ref: str, baseline_ref: str = "", gap_minutes: float = 5.0,
             limit: int = 6, max_tokens: int = DEFAULT_TOKENS) -> str:
    """첫 오류·직전 정상 줄·오류 에피소드·처음 등장 순서.

    baseline_ref: 기준선 파일의 ref (있으면 '기준선에 없던 서명'을 표시).
    """
    try:
        log = _get(ref)
        baseline = _get(baseline_ref) if baseline_ref else None
        view = build_timeline(log, gap_minutes=float(gap_minutes), clusters=cluster(log),
                              baseline=baseline)
        return _finish(_check_stale(ref) + report.timeline_view(view, log, limit=int(limit)),
                       max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_text(ref: str, pattern: str, context: int = 2, regex: bool = False,
              ignore_case: bool = True, max_matches: int = 20,
              max_tokens: int = DEFAULT_TOKENS) -> str:
    """문자열/정규식 검색 — 원본 줄 번호와 앞뒤 줄.

    regex: 정규식으로 해석. ignore_case: 대소문자 무시.
    """
    try:
        log = _get(ref)
        result = find(log, pattern, context=int(context), regex=bool(regex),
                      ignore_case=bool(ignore_case), max_matches=int(max_matches))
        if result.error:
            return _fail(ValueError(result.error))
        lines = [f"🔍 '{result.pattern}' — {result.total:,}줄 일치 (훑은 줄 {result.scanned:,})"]
        for match in result.matches:
            for line_no, text in match.before:
                lines.append(f"  {line_no:>7}   {text[:160]}")
            lines.append(f"  {match.line_no:>7} > {match.text[:160]}")
            for line_no, text in match.after:
                lines.append(f"  {line_no:>7}   {text[:160]}")
        if result.total > len(result.matches):
            lines.append(f"  … {result.total - len(result.matches):,}줄 더 (max_matches)")
        return _finish("\n".join(lines), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def redact_secrets(ref: str, out: str = "", preview: int = 5,
                   max_tokens: int = DEFAULT_TOKENS) -> str:
    """비밀·개인정보를 지운 사본 — 지운 뒤 남은 것 0을 확인한다.

    out: 마스킹본을 쓸 경로(비우면 미리보기만, 파일은 만들지 않음).
    """
    try:
        log = _get(ref)
        _, text = read_whole(log.path)
        result = redact_text(text)
        original = text.splitlines()
        out_path = ""
        if out:
            out_path = str(_path(out))
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_text("\n".join(line for _, line in result.texts) + "\n",
                                      encoding="utf-8")
        changed = [(number, line) for number, line in result.texts
                   if number - 1 < len(original) and line != original[number - 1]]
        return _finish(report.redact_view(result, preview=changed[: int(preview)],
                                          out=out_path, checked_lines=len(original)),
                       max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def rule_catalog(rule: str = "", max_tokens: int = DEFAULT_TOKENS) -> str:
    """규칙 목록, 또는 규칙 하나의 설명(왜 문제인지·어떻게 고치는지)."""
    try:
        if rule and rule not in RULES:
            known = ", ".join(sorted(RULES))
            raise KeyError(f"그런 규칙이 없습니다: {rule} (있는 규칙: {known})")
        return _finish(report.catalog_view(rule), max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def find_problems(ref: str, now: str = "", limit: int = 12,
                  max_tokens: int = DEFAULT_TOKENS) -> str:
    """규칙 위반 목록과 고치는 순서 (치명·주의·참고).

    now: ISO 시각. 주면 '미래 시각' 규칙을 켠다.
    """
    try:
        from datetime import datetime
        log = _get(ref)
        moment = datetime.fromisoformat(now) if now else None
        findings = check(log, now=moment)
        text = _check_stale(ref) + report.problems_view(findings, limit=int(limit))
        text += "\n\n" + report.fix_order(findings)
        text += f"\n\n{report.LIMITS}"
        return _finish(text, max_tokens)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def overview() -> str:
    """이 서버가 무엇을 하고 무엇을 판정하지 않는지."""
    return report.OVERVIEW


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="log-triage MCP 서버 (stdio)")
    parser.add_argument("--root", default=None, help="로그 파일 기준 디렉터리 (LOG_TRIAGE_ROOT)")
    args = parser.parse_args(argv)
    if args.root:
        os.environ["LOG_TRIAGE_ROOT"] = args.root
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
