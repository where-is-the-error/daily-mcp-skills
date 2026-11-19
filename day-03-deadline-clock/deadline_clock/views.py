"""툴 응답을 마크다운으로 — 1080×1920 이 아니라 **폰 알림 한 화면**을 기준으로 짧게.

남은 시간·D-day·평일 수를 한 줄에 붙이고, 가정한 값(시간대·23:59)은 반드시 드러낸다.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from .clock import DeadlineStatus, bucket_label, weekday_kr, zone_clock
from .tokens import estimate, trim_to_tokens
from .timeparse import Parsed
from .zones import short_zone, zone_note

__all__ = [
    "finish",
    "render_add",
    "render_list",
    "render_status",
    "render_done",
    "render_overview",
    "render_preview",
    "line",
]

BUCKET_MARK = {
    "overdue": "🔴",
    "critical": "🟠",
    "today": "🟡",
    "soon": "🟢",
    "week": "🔵",
    "later": "⚪",
}
# 이모지는 응답(텍스트)에서만 쓴다. 릴스에서는 폰트에서 네모로 깨지므로 쓰지 않는다.


def finish(text: str, budget: int | None) -> str:
    if budget is None or budget <= 0:
        return text
    trimmed, cut = trim_to_tokens(text, budget)
    if not cut:
        return text
    return trimmed + "\n\n… (응답이 토큰 예산에 맞춰 잘렸습니다)"


def line(status: DeadlineStatus, show_id: bool = True) -> str:
    head = f"{BUCKET_MARK.get(status.bucket, '·')} **{status.dday}** · {status.human}"
    tail = f" — {status.title}"
    if status.business_days:
        tail += f" · 평일 {status.business_days}일"
    ident = f" `{status.id}`" if show_id else ""
    if status.done:
        head = "✅ 완료"
        tail = f" — {status.title}"
    return head + tail + ident


def _when_block(status: DeadlineStatus) -> list[str]:
    bits = [f"- 마감: **{status.wall_text}**", f"- 남은 시간: **{status.human}** ({bucket_label(status.bucket)})"]
    if status.business_days:
        bits.append(f"- 남은 평일: **{status.business_days}일** (월~금, 공휴일 미포함)")
    if status.tags:
        bits.append("- 태그: " + ", ".join(f"`{t}`" for t in status.tags))
    return bits


def render_add(
    *,
    title: str,
    status: DeadlineStatus,
    add_status: str,
    parsed: Parsed,
    now,
    zone: str,
    history: list[dict] | None = None,
) -> str:
    head = {
        "created": "새 마감을 등록했습니다",
        "duplicate": "이미 등록된 마감입니다 (같은 제목·같은 시각)",
        "revived": "완료했던 마감을 다시 열었습니다",
    }.get(add_status, add_status)
    lines = [f"# deadline-clock · {head}", f"> {line(status, show_id=False)}", ""]
    lines += _when_block(status)
    if status.note:
        lines.append(f"- 메모: {status.note}")
    if parsed.assumed:
        lines.append("- 가정: " + " · ".join(parsed.assumed))
    if parsed.ambiguous:
        second = parsed.instants[1]
        lines.append(
            f"- ⚠️ {parsed.note} 두 번째 순간: {second.astimezone(ZoneInfo(zone)):%Y-%m-%d %H:%M} "
            f"({zone_note(zone)})"
        )
    lines += ["", f"- id: `{status.id}` · 표시 시간대 {short_zone(zone)} ({zone_note(zone)})"]
    if history:
        lines.append(f"- 기록: {len(history)}건")
    return "\n".join(lines)


def render_list(
    statuses: list[DeadlineStatus],
    *,
    now,
    zone: str,
    window_label: str,
    tag: str | None = None,
    include_done: bool = False,
) -> str:
    if not statuses:
        return "\n".join(
            [
                "# deadline-clock · 예정된 마감 없음",
                f"> 지금 {zone_clock(now, zone)}",
                "",
                f"- {window_label} 안에 잡힌 마감이 없습니다.",
                "- 새로 넣으려면: add_deadline(title=\"공모전 제출\", when=\"내일 오후 6시\")",
            ]
        )
    overdue = [s for s in statuses if s.overdue and not s.done]
    lines = [
        "# deadline-clock · 마감 순서",
        f"> 지금 {zone_clock(now, zone)}",
        f"- 보기: {window_label}" + (f" · 태그 `{tag}`" if tag else "") + (" · 완료 포함" if include_done else ""),
    ]
    if overdue:
        lines.append(f"- ⚠️ 지난 마감 {len(overdue)}건 — 아래 맨 위")
    lines.append("")
    for status in statuses:
        lines.append(line(status))
    if statuses:
        nxt = next((s for s in statuses if not s.overdue and not s.done), None)
        if nxt:
            lines += ["", f"가장 급한 것: **{nxt.title}** — {nxt.human} ({nxt.wall_text})"]
    return "\n".join(lines)


def render_status(status: DeadlineStatus, history: list[dict] | None = None) -> str:
    lines = [f"# deadline-clock · {status.title}", f"> {line(status, show_id=False)}", ""]
    lines += _when_block(status)
    if status.note:
        lines.append(f"- 메모: {status.note}")
    lines.append(f"- id: `{status.id}`")
    lines.append(f"- 저장된 시간대: {status.zone} ({zone_note(status.zone, status.due_utc)})")
    if status.done:
        done_at = status.done_utc.astimezone(ZoneInfo(status.zone))
        lines.append(f"- 완료: {done_at:%Y-%m-%d %H:%M} ({status.zone})")
    if history:
        lines.append("")
        lines.append("## 기록")
        for item in history[:6]:
            stamp = item["at_utc"].replace("T", " ")[:16]
            lines.append(f"- {stamp} · {item['kind']}" + (f" — {item['detail']}" if item.get("detail") else ""))
    return "\n".join(lines)


def render_done(status: DeadlineStatus, outcome: str) -> str:
    if outcome == "already":
        return f"# deadline-clock · 이미 그 상태입니다\n> {line(status, show_id=False)}\n\n- `{status.id}` 는 {'완료' if status.done else '진행 중'} 상태입니다."
    verb = "완료로 표시했습니다" if status.done else "다시 진행 중으로 되돌렸습니다"
    lines = [f"# deadline-clock · {verb}", f"> {line(status, show_id=False)}", ""]
    if status.done:
        done_at = status.done_utc.astimezone(ZoneInfo(status.zone))
        lines.append(f"- 완료 시각: {done_at:%Y-%m-%d %H:%M} ({status.zone})")
    else:
        lines.append(f"- 남은 시간: **{status.human}**")
    return "\n".join(lines)


def render_overview(
    statuses: list[DeadlineStatus],
    *,
    db_stats: dict,
    now,
    zone: str,
    horizon_days: int = 14,
) -> str:
    open_rows = [s for s in statuses if not s.done]
    counts: dict[str, int] = {}
    for status in open_rows:
        counts[status.bucket] = counts.get(status.bucket, 0) + 1
    lines = [
        "# deadline-clock · 지금",
        f"> {zone_clock(now, zone)}",
        f"- 열린 마감 **{len(open_rows)}건** · 완료 {db_stats.get('done', 0)}건 · 전체 {db_stats.get('total', 0)}건",
    ]
    if counts:
        pieces = [f"{bucket_label(k)} {counts[k]}" for k in BUCKETS_ORDER if k in counts]
        lines.append("- 분포: " + " · ".join(pieces))
    lines.append("")
    if open_rows:
        lines.append(f"## 앞으로 {horizon_days}일")
        for status in open_rows[:8]:
            lines.append(line(status))
    else:
        lines += ["## 비어 있음", "- add_deadline 으로 첫 마감을 넣어 보세요."]
    if db_stats.get("total"):
        lines += ["", f"- db: `deadlines` {db_stats['total']} · `events` {db_stats.get('events', 0)} (한 파일, 읽기/쓰기 분리)"]
    return "\n".join(lines)


BUCKETS_ORDER = ("overdue", "critical", "today", "soon", "week", "later")


def render_preview(parsed: Parsed, *, now, zone: str) -> str:
    from .clock import bucket, humanize, remaining_seconds
    from .zones import tz

    secs = remaining_seconds(parsed.instant, now)
    wall_view = parsed.instant.astimezone(tz(zone)).replace(tzinfo=None)
    lines = [
        "# deadline-clock · 미리보기 (저장하지 않았습니다)",
        f"- 입력: `{parsed.raw}`",
        f"- 해석: **{wall_view:%Y-%m-%d}({weekday_kr(wall_view)}) {wall_view:%H:%M} {short_zone(zone)}**",
        f"- 남는다면: **{humanize(secs)}** ({bucket_label(bucket(secs))})",
        f"- UTC: {parsed.instant:%Y-%m-%dT%H:%M:%SZ}",
    ]
    if parsed.assumed:
        lines.append("- 가정: " + " · ".join(parsed.assumed))
    if parsed.kind == "ambiguous":
        second = parsed.instants[1].astimezone(tz(zone))
        lines.append(f"- ⚠️ {parsed.note} 두 번째: {second:%Y-%m-%d %H:%M} {short_zone(zone)}")
    if parsed.note and parsed.kind != "ambiguous":
        lines.append(f"- 참고: {parsed.note}")
    return "\n".join(lines)
