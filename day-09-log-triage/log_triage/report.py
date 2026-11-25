"""보고서 — 터미널과 MCP 응답에 그대로 나가는 글.

숫자만 늘어놓지 않는다. 각 줄은 '무엇을 봤는지 → 그래서 무엇을 할지' 순서로 쓴다.
판정하지 못한 것은 매번 함께 적는다(`LIMITS`). 도구가 아는 척하는 순간
사람은 그 도구를 못 믿게 된다.
"""

from __future__ import annotations

from collections import Counter

from .compare import Comparison, Row
from .rates import RateReport
from .redact import Redaction
from .rules import RULES, Finding
from .signature import Cluster
from .stack import StackReport
from .timeline import Timeline
from .types import LogFile, wall_dt

LIMITS = (
    "판정하지 않음: 로그 내용의 사실 여부 · 지표가 정상 범위인지 · 장애의 원인 · 배포/설정 이력. "
    "시각은 각 로그의 벽시계 기준으로 정렬합니다. 오프셋 없는 시각은 UTC로 가정합니다."
)

OVERVIEW = """\
log-triage — 로그 파일 하나로 '무엇이·언제부터·얼마나' 를 먼저 봅니다.

읽는 순서
  read_logs        파일을 읽어 인코딩·시각·레벨·구간을 확인하고 ref 를 받습니다
  signature_report 같은 메시지를 하나로 묶습니다 (숫자·ID·경로를 걷어낸 뼈대)
  rate_report      분당 개수·폭주·끊김·같은 초 반복
  compare_logs     before/after 를 분당 비율로 비교 — 새로 생긴 서명
  stack_report     스택에서 가장 안쪽 프레임과 예외 (Python/Java/Node/Go)
  timeline         첫 오류·직전 정상·에피소드
  find_text        문자열/정규식 검색 (앞뒤 줄 포함)
  redact_secrets   비밀·개인정보를 지운 사본 (지운 뒤 남은 것 0 확인)
  rule_catalog     규칙 25종의 '왜·어떻게'
  overview         이 설명

판정하지 않는 것
  로그 내용이 사실인지, 지표가 정상인지, 원인이 무엇인지, 배포 이력.
  파일은 읽기만 합니다. 원본을 고치지 않고, 마스킹본은 새 파일로 씁니다.
"""


# ------------------------------------------------------------------ helpers
def _clock(ts) -> str:
    if ts is None:
        return "—"
    return ts.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}초"
    if seconds < 5400:
        return f"{seconds / 60:.1f}분"
    return f"{seconds / 3600:.1f}시간"


def _bar(value: float, total: float, width: int = 12) -> str:
    if total <= 0:
        return "·" * width
    filled = max(1, min(width, int(round(width * value / total)))) if value else 0
    return "█" * filled + "·" * (width - filled)


def human_number(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}k"
    return f"{int(n):,}"


# ------------------------------------------------------------------ read_logs
def table_summary(log: LogFile, ref: str = "") -> str:
    first, last, seconds = log.span()
    lines = [f"📄 {log.path}"]
    if ref:
        lines.append(f"   ref {ref}")
    lines.append(
        f"   {log.encoding}(확신 {log.encoding_confidence:.2f})"
        f"{' · BOM' if log.encoding_bom else ''} · {log.total_lines:,}줄"
        f" → 레코드 {len(log.records):,}개"
    )
    if log.continuation_lines:
        detail = (f"   이어짐 {log.continuation_lines:,}줄"
                  f" · 첫 사건 앞 {len(log.orphans)}줄")
        lines.append(detail)
    if log.records:
        lines.append(
            f"   구간 {_clock(first)} ~ {_clock(last)} ({_minutes(seconds)})"
            f" · 분당 {len(log.records) / log.duration_minutes():.1f}건"
        )
        seen = log.level_counts()
        parts = [f"{name} {count:,}({100 * count / len(log.records):.1f}%)"
                 for name, count in seen.most_common()]
        lines.append("   레벨: " + " · ".join(parts))
        tz = log.tz_offsets()
        tz_text = ", ".join(("오프셋 없음" if k == "none" else f"UTC{int(k):+d}분") + f" {v:,}"
                            for k, v in tz.most_common(3))
        kinds = ", ".join(f"{k} {v:,}" for k, v in log.ts_kinds().most_common(3))
        lines.append(f"   시각: {kinds}" + (f" · {tz_text}" if tz else ""))
        errors = len(log.error_records())
        lines.append(f"   ERROR/CRITICAL {human_number(errors)}건"
                     f" ({100 * errors / len(log.records):.1f}%)")
    else:
        lines.append("   시각을 읽은 레코드가 없습니다 — 시각 없는 파일이거나 지원하지 않는 형식입니다.")
    if log.orphans:
        first_line, text = log.orphans[0]
        lines.append(f"   첫 사건 앞: {first_line}줄째 \"{text[:70]}\"")
    return "\n".join(lines)


# ------------------------------------------------------------------ signature
def signature_view(clusters: list[Cluster], log: LogFile, limit: int = 12) -> str:
    total = len(log.records) or 1
    head = f"🔎 서명 {len(clusters):,}종 · 레코드 {total:,}"
    lines = [head]
    for index, item in enumerate(clusters[:limit], start=1):
        share = 100 * item.count / total
        span = ""
        if item.first_ts is not None and item.last_ts is not None:
            first = item.first_ts.replace(tzinfo=None).strftime("%H:%M:%S")
            last = item.last_ts.replace(tzinfo=None).strftime("%H:%M:%S")
            span = f" · {first}~{last}"
        lines.append(
            f"  {index:>2}. {item.count:>6,}건 {share:5.1f}% {_bar(item.count, total, 8)} "
            f"{item.level:<8} {item.template[:96]}{span}"
        )
        if item.samples:
            lines.append(f"      └ {item.samples[0][:110]}")
    if len(clusters) > limit:
        rest = sum(c.count for c in clusters[limit:])
        lines.append(f"  … 남은 {len(clusters) - limit:,}종 {rest:,}건")
    return "\n".join(lines)


# ------------------------------------------------------------------ rate
def rate_view(rate: RateReport, log: LogFile) -> str:
    lines = [
        f"⏱ {rate.bucket_seconds}초 구간 {len(rate.buckets):,}개 · 한 구간 중앙값 {rate.median:.0f}건"
        f" · 최대 {rate.peak:,}건"
    ]
    if rate.error_bursts:
        lines.append(f"   오류 폭주 {len(rate.error_bursts)}곳 (평소 오류 {rate.error_median:.0f}건/"
                     f"{rate.bucket_seconds}초)")
        for burst in rate.error_bursts[:4]:
            lines.append(f"     {burst.start_dt.strftime('%m-%d %H:%M:%S')}  오류 {burst.count:,}건"
                         f" · {burst.ratio:.1f}배")
    elif rate.error_median:
        lines.append(f"   오류 {rate.error_median:.0f}건/{rate.bucket_seconds}초 안팎 — 몰린 구간 없음")
    if rate.bursts:
        lines.append(f"   폭주 {len(rate.bursts)}곳")
        for burst in rate.bursts[:4]:
            ratio = "중앙값 0" if rate.median == 0 else f"중앙값 {burst.ratio:.1f}배"
            lines.append(f"     {burst.start_dt.strftime('%m-%d %H:%M:%S')}  {burst.count:,}건"
                         f" (오류 {burst.errors:,}) · {ratio}")
    if rate.gaps:
        lines.append(f"   끊김 {len(rate.gaps)}곳")
        for gap in rate.gaps[:3]:
            lines.append(f"     {gap.start_dt.strftime('%m-%d %H:%M:%S')} → "
                         f"{gap.end_dt.strftime('%H:%M:%S')}  {_minutes(gap.seconds)} 없음")
    if rate.storms:
        lines.append("   같은 초 반복")
        for storm in rate.storms[:3]:
            template = storm.template or "(서명)"
            lines.append(f"     {storm.count}회 @ {wall_dt(storm.second).strftime('%H:%M:%S')}"
                         f" · {template[:80]}")
    if rate.out_of_order:
        lines.append(f"   시각이 뒤로 간 줄 {rate.out_of_order:,}개 — 여러 프로세스가 같은 파일에 쓰는지 확인")
    return "\n".join(lines)


# ------------------------------------------------------------------ compare
def _rate_text(value: float) -> str:
    return f"{value:.1f}/분" if value >= 0.05 else f"{value:.3f}/분"


def compare_view(cmp: Comparison, limit: int = 10) -> str:
    lines = [
        f"↔ {cmp.before_path} → {cmp.after_path}",
        f"   창 {cmp.before_minutes:.1f}분 → {cmp.after_minutes:.1f}분"
        f" · 레코드 {cmp.before_total:,} → {cmp.after_total:,}",
    ]
    ratio = cmp.error_rate_change
    ratio_text = "∞" if ratio == float("inf") else f"{ratio:.1f}배"
    lines.append(
        f"   ERROR/CRITICAL {cmp.before_errors:,} → {cmp.after_errors:,}"
        f" ({_rate_text(cmp.before_errors / max(cmp.before_minutes, 1e-9))} → "
        f"{_rate_text(cmp.after_errors / max(cmp.after_minutes, 1e-9))}, {ratio_text})"
    )
    tally = Counter(row.status for row in cmp.rows)
    order = ["new", "new-rare", "grew", "shrank", "gone", "gone-rare", "same"]
    labels = {"new": "새로 생김", "new-rare": "새로 생김(드묾)", "grew": "늘어남",
              "shrank": "줄어남", "gone": "사라짐", "gone-rare": "사라짐(드묾)", "same": "그대로"}
    lines.append("   " + " · ".join(f"{labels[k]} {tally[k]}" for k in order if tally.get(k)))
    if not cmp.rows:
        return "\n".join(lines)

    shown = 0
    for row in cmp.rows:
        if row.status == "same" or shown >= limit:
            continue
        shown += 1
        mark = {"new": "+", "new-rare": "·", "grew": "↑", "shrank": "↓",
                "gone": "−", "gone-rare": "·"}.get(row.status, " ")
        lines.append(
            f"   {mark} {row.label:<10} {row.before_count:>5,} → {row.after_count:>5,}"
            f"  ({_rate_text(row.after_rate)}"
            + (f", ×{row.ratio:.1f}" if row.status in ("grew", "shrank") and row.before_rate else "")
            + f")  {row.template[:74]}"
        )
        if row.status in ("new", "grew") and row.first_after:
            lines.append(f"       처음 {row.first_after[11:]}")
    remaining = len([r for r in cmp.rows if r.status not in ("same",)]) - shown
    if remaining > 0:
        lines.append(f"   … 남은 변화 {remaining}종")
    return "\n".join(lines)


# ------------------------------------------------------------------ stack
def stack_view(report: StackReport, log: LogFile, limit: int = 8) -> str:
    errors = len(log.error_records())
    lines = [f"🧵 스택이 붙은 레코드 {report.traced:,} · 스택 없는 ERROR {report.untraced_errors:,}/{errors:,}"]
    if report.languages:
        lines.append("   언어: " + ", ".join(f"{k} {v:,}" for k, v in report.languages.most_common()))
    for index, group in enumerate(report.groups[:limit], start=1):
        lines.append(
            f"  {index:>2}. {group.count:>5,}건 · {group.language} · {group.exception[:70] or '(예외 미상)'}"
        )
        where = group.location or "위치 미상"
        lines.append(f"      위치 {where} · 인과 {group.causes}단 · 서로 다른 스택 {group.distinct_stacks}개")
    if report.top_frames:
        lines.append("   프레임 상위: " + ", ".join(f"{where} {count:,}"
                                                     for where, count in report.top_frames.most_common(5)))
    return "\n".join(lines)


# ------------------------------------------------------------------ timeline
def timeline_view(timeline: Timeline, log: LogFile, limit: int = 6) -> str:
    if not timeline.has_errors:
        return f"🕒 ERROR 없음 — 레코드 {len(log.records):,}개, 첫 줄 {_clock(timeline.first_record.ts if timeline.first_record else None)}"
    first = timeline.first_error
    lines = [f"🕒 첫 오류 {first.clock()} ({first.level}) · 줄 {first.line_no:,}"]
    if timeline.last_healthy is not None:
        lines.append(f"   직전 정상 {timeline.last_healthy.clock()} · {timeline.last_healthy.snippet(80)}")
    else:
        lines.append("   직전 정상 줄 없음 — 파일이 오류로 시작합니다")
    if timeline.last_error is not None:
        span = (timeline.last_error.sort_key - first.sort_key) / 60.0
        lines.append(f"   마지막 오류 {timeline.last_error.clock()} · 오류 구간 {span:.1f}분")
    lines.append(f"   에피소드 {len(timeline.episodes)}개")
    for episode in timeline.episodes[:limit]:
        templates = ", ".join(f"{count}× {template[:60]}" for template, count in episode.signatures[:2])
        lines.append(f"     {episode.start_dt.strftime('%m-%d %H:%M:%S')} ~ "
                     f"{episode.end_dt.strftime('%H:%M:%S')}  {episode.count:,}건 · {templates[:100]}")
    if len(timeline.episodes) > limit:
        lines.append(f"     … {len(timeline.episodes) - limit}개 더")
    if timeline.first_seen:
        lines.append("   처음 등장 순서")
        for template, clock, level in timeline.first_seen[:6]:
            lines.append(f"     {clock[11:]} {level:<7} {template[:80]}")
    if timeline.new_signatures:
        lines.append(f"   기준선에 없던 ERROR 서명 {len(timeline.new_signatures)}종")
    return "\n".join(lines)


# ------------------------------------------------------------------ problems
def problems_view(findings: list[Finding], limit: int = 12) -> str:
    if not findings:
        return "✅ 걸리는 것 없음"
    lines = [f"🚨 규칙 위반 {len(findings)}종"]
    for index, finding in enumerate(findings[:limit], start=1):
        spec = RULES.get(finding.rule)
        title = spec.title if spec else finding.rule
        where = f" · 줄 {', '.join(str(n) for n in finding.lines)}" if finding.lines else ""
        lines.append(f"  {index:>2}. [{finding.label}] {title} — {finding.count:,}건{where}")
        lines.append(f"      {finding.detail}")
        if spec:
            lines.append(f"      → {spec.fix}")
    if len(findings) > limit:
        lines.append(f"  … {len(findings) - limit}종 더")
    return "\n".join(lines)


def fix_order(findings: list[Finding]) -> str:
    order = [f for f in findings if f.severity == "critical"]
    order += [f for f in findings if f.severity == "warn"]
    order += [f for f in findings if f.severity == "info"]
    if not order:
        return "고칠 것 없음"
    lines = ["고치는 순서"]
    for index, finding in enumerate(order[:8], start=1):
        spec = RULES.get(finding.rule)
        lines.append(f"  {index}. [{finding.label}] {spec.fix if spec else finding.rule}")
    return "\n".join(lines)


# ------------------------------------------------------------------ redact
def redact_view(redaction: Redaction, preview: list[tuple[int, str]] | None = None,
                out: str = "", checked_lines: int = 0) -> str:
    kinds = ", ".join(f"{k} {v:,}" for k, v in sorted(redaction.counts.items(), key=lambda kv: -kv[1]))
    lines = [f"🕶 지운 값 {redaction.total:,}개 · 바뀐 줄 {redaction.lines_changed:,}/{checked_lines:,}"
             + (f" · {kinds}" if kinds else "")]
    lines.append(f"   남은 것: {redaction.residual_total}개"
                 + (" (0 확인)" if redaction.residual_total == 0 else " — 재검사 필요"))
    lines.append(f"   길이 {redaction.chars_before:,}자 → {redaction.chars_after:,}자"
                 + (f" · 저장 {out}" if out else ""))
    if preview:
        lines.append("   미리보기")
        for number, text in preview[:6]:
            lines.append(f"     {number:>6}: {text[:110]}")
    return "\n".join(lines)


# ------------------------------------------------------------------ catalog
def catalog_view(rule_id: str = "") -> str:
    if rule_id:
        spec = RULES.get(rule_id)
        if spec is None:
            known = ", ".join(sorted(RULES))
            return f"그런 규칙이 없습니다: {rule_id}\n있는 규칙: {known}"
        return (f"[{severity_label(spec.severity)}] {spec.id} — {spec.title}\n"
                f"  왜: {spec.why}\n  고치기: {spec.fix}\n  묶음: {spec.group}")
    by_group: dict[str, list] = {}
    for spec in RULES.values():
        by_group.setdefault(spec.group, []).append(spec)
    lines = [f"규칙 {len(RULES)}종"]
    for group, specs in by_group.items():
        lines.append(f"  [{group}]")
        for spec in specs:
            lines.append(f"    {spec.id:<20} {severity_label(spec.severity):<3} {spec.title}")
    return "\n".join(lines)


def severity_label(name: str) -> str:
    return {"critical": "치명", "warn": "주의", "info": "참고"}.get(name, name)
