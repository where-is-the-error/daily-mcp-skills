"""툴 응답을 마크다운으로 조립한다.

모든 응답은 마지막에 `budget`(추정 토큰)으로 잘린다 — 페이지를 통째로 넘기는
대신 바뀐 줄만 넘긴다는 이 서버의 약속이 툴 응답에도 그대로 적용된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import diff as diffmod
from .graph import AnnotationResult, neighbors, observations
from .pages import PageRow, RememberResult, Snapshot
from .search import Hit
from .tokens import estimate, trim_to_tokens

__all__ = [
    "finish",
    "render_remember",
    "render_changes",
    "render_recall",
    "render_annotate",
    "render_overview",
    "short_time",
]


def short_time(stamp: str) -> str:
    if not stamp:
        return "—"
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def finish(text: str, budget: int | None) -> str:
    """토큰 예산에 맞춰 자른다."""
    if budget is None or budget <= 0:
        return text
    trimmed, cut = trim_to_tokens(text, budget)
    if not cut:
        return text
    return trimmed + "\n\n… (응답이 토큰 예산에 맞춰 잘렸습니다)"


def _status_line(result: RememberResult) -> str:
    if result.status == "new":
        return "새로 기억함 · 첫 스냅샷"
    if result.status == "unchanged":
        return "변경 없음 · 스냅샷을 늘리지 않았습니다"
    assert result.diff is not None
    return f"변경됨 · +{result.diff.added}줄 / -{result.diff.removed}줄"


def _head(title: str, url: str, snap: Snapshot | None, status: str) -> list[str]:
    lines = [f"# web-memo · {title}", f"> `{url}`", f"- 상태: {status}"]
    if snap is not None:
        lines.append(
            f"- 본문 {snap.chars:,}자 · 추정 {snap.tokens:,} 토큰 · 스냅샷 #{snap.id} "
            f"({short_time(snap.fetched_at)})"
        )
    return lines


def render_remember(
    result: RememberResult,
    *,
    pages: int = 0,
    robots_note: str = "",
    diff_lines: int = 60,
) -> str:
    lines = _head(result.title or result.url, result.url, result.snapshot, _status_line(result))
    if robots_note:
        lines.append(f"- {robots_note}")

    if result.status == "unchanged":
        lines.append(
            f"- 같은 내용이라 이번엔 아무것도 저장하지 않았습니다 "
            f"(이 페이지 본문 {result.tokens_saved:,} 토큰을 다시 넘기지 않아도 됩니다)"
        )
    elif result.status == "changed" and result.diff is not None:
        delta = result.diff
        diff_tokens = estimate(delta.render())
        full_tokens = result.snapshot.tokens
        if diff_tokens < full_tokens:
            lines.append(
                f"- 이번 응답은 바뀐 부분만: 약 {diff_tokens:,} 토큰 "
                f"(전체 {full_tokens:,} 토큰 대신 {full_tokens - diff_tokens:,} 토큰 절약)"
            )
        else:
            lines.append(
                f"- 바뀐 줄은 약 {diff_tokens:,} 토큰 — 이 페이지는 전문이 {full_tokens:,} 토큰이라 "
                "짧습니다. 큰 문서일수록 차이가 커집니다."
            )
        lines += ["", "## 바뀐 부분"]
        lines.append("```diff")
        lines.append(delta.render(max_lines=diff_lines))
        lines.append("```")
    else:
        lines.append("- 이 페이지를 처음 기억했습니다. 다음에 다시 부르면 바뀐 줄만 돌려줍니다.")
        preview = (result.snapshot.text if result.snapshot else "").split("\n")
        preview = [line for line in preview if line.strip()][:3]
        if preview:
            lines += ["", "## 앞부분"] + [f"> {line[:120]}" for line in preview]

    if pages:
        lines.append(f"- 기억 중인 페이지 {pages}개")
    lines += [
        "",
        "## 다음",
        f"- 바뀐 기록을 다시 보려면 `page_changes(url=\"{result.url}\")`",
        f"- 이 페이지에 메모를 달려면 `annotate(target=\"{result.url}\", note=\"...\")`",
    ]
    return "\n".join(lines)


def render_changes(
    url: str,
    diff: diffmod.DiffResult,
    now_snap: Snapshot | None,
    old_snap: Snapshot | None,
    *,
    lines_cap: int = 80,
) -> str:
    head = ["# web-memo · page_changes", f"> `{url}`"]
    if old_snap and now_snap:
        head.append(
            f"- 비교: 스냅샷 #{old_snap.id} ({short_time(old_snap.fetched_at)}) → "
            f"#{now_snap.id} ({short_time(now_snap.fetched_at)})"
        )
    else:
        head.append("- 비교할 이전 스냅샷이 없습니다. `remember_page`를 두 번 이상 불러 주세요.")
        return "\n".join(head)

    if not diff.changed:
        head.append("- 두 스냅샷의 본문이 같습니다.")
        return "\n".join(head)

    head += [
        f"- +{diff.added}줄 / -{diff.removed}줄 · 바뀐 부분만 {estimate(diff.render()):,} 토큰",
        "",
        "## 차이",
        "```diff",
        diff.render(max_lines=lines_cap),
        "```",
    ]
    return "\n".join(head)


def render_recall(query: str, hits: list[Hit], *, total_pages: int) -> str:
    if not hits:
        return (
            f"# web-memo · recall\n> `{query}`\n\n"
            "- 걸리는 기억이 없습니다. `remember_page`로 페이지를 먼저 기억시키거나 "
            "다른 단어로 다시 불러 보세요."
        )
    lines = ["# web-memo · recall", f"> `{query}` · 기억 {total_pages}개 중 {len(hits)}건", ""]
    for index, hit in enumerate(hits, 1):
        tag = "페이지" if hit.kind == "page" else hit.kind
        lines.append(f"## {index}. {hit.title or hit.name}  ── {tag} · 점수 {hit.score}")
        lines.append(f"- `{hit.name}`")
        if hit.matched:
            lines.append(f"- 걸린 곳: {', '.join(hit.matched)}")
        if hit.last_seen:
            lines.append(f"- 마지막 확인: {short_time(hit.last_seen)} · {hit.tokens:,} 토큰")
        for note in hit.notes:
            lines.append(f"- 메모: {note}")
        for piece in hit.snippets:
            lines.append(f"> {piece}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_annotate(result: AnnotationResult) -> str:
    lines = ["# web-memo · annotate", f"> `{result.target}`"]
    if result.created_entity:
        lines.append("- 기억에 새 엔티티를 만들었습니다.")
    if result.added_note:
        lines.append("- 메모를 한 줄 남겼습니다.")
    elif not result.created_entity:
        lines.append("- 이미 같은 메모가 있어 새로 쌓지 않았습니다.")
    if result.tags:
        lines.append(f"- 태그: {', '.join('#' + t for t in result.tags)}")
    if result.notes:
        lines += ["", "## 이 대상에 쌓인 메모"]
        for note in result.notes[:8]:
            lines.append(f"- {note.text}  ({short_time(note.created)})")
    return "\n".join(lines)


def render_overview(
    *,
    page_stats: dict[str, int],
    graph_stats: dict[str, int],
    recent: list[PageRow],
    stale: list[PageRow],
    stale_days: int,
) -> str:
    lines = [
        "# web-memo · overview",
        f"- 기억한 페이지 {page_stats.get('pages', 0)}개 · 스냅샷 "
        f"{page_stats.get('snapshots', 0)}개 · 바뀐 적 있는 페이지 "
        f"{page_stats.get('changed_pages', 0)}개",
        f"- 스냅샷 본문 합계 추정 {page_stats.get('tokens', 0):,} 토큰",
        f"- 기억 그래프: 엔티티 {graph_stats.get('entities', 0)} · 관찰 "
        f"{graph_stats.get('observations', 0)} · 관계 {graph_stats.get('relations', 0)}",
    ]
    if recent:
        lines += ["", "## 최근 확인한 페이지"]
        for row in recent[:8]:
            flag = " · 바뀐 적 있음" if row.changes else ""
            lines.append(
                f"- {row.title or row.url}\n  `{row.url}` — {short_time(row.last_seen)} "
                f"· 확인 {row.checks}회{flag} · 스냅샷 {row.snapshots}개"
            )
    else:
        lines += ["", "아직 기억한 페이지가 없습니다. `remember_page(url=\"...\")`로 시작하세요."]

    if stale:
        lines += ["", f"## {stale_days}일 넘게 안 본 페이지"]
        for row in stale[:8]:
            lines.append(f"- `{row.url}` — 마지막 {short_time(row.last_seen)}")
    return "\n".join(lines)


def render_node(conn, name: str) -> str:
    """엔티티 하나의 관찰 + 관계(디버깅·CLI용)."""
    notes = observations(conn, name)
    rels = neighbors(conn, name)
    lines = [f"# web-memo · {name}"]
    for note in notes:
        lines.append(f"- {note.text}")
    for kind, other, arrow in rels:
        lines.append(f"- {arrow} {other} ({kind})")
    return "\n".join(lines)
