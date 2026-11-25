"""규칙 — 로그를 넘기기 전에 걸리는 것들.

규칙마다 (1) 왜 문제인지, (2) 어떻게 고치는지를 붙였다. '위반'만 세고 끝내면
사용자는 무엇을 해야 할지 모른다. 그래서 보고서에는 항상 '고치는 순서'가 붙는다.

여기서 판정하지 않는 것: 로그 내용이 **사실인지**, 지표가 정상 범위인지,
장애의 원인이 무엇인지. 도구는 '모양'만 본다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .rates import analyze as analyze_rates
from .redact import redact_text
from .signature import cluster, template_share
from .stack import stack_report
from .types import LogFile, Record

SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}
SEVERITY_LABELS = {"critical": "치명", "warn": "주의", "info": "참고"}

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MOJIBAKE = re.compile(r"[□]|Ã[\x80-\xbf]|â€|ìŠ|ëŠ")


@dataclass(slots=True)
class Rule:
    id: str
    severity: str
    title: str
    why: str
    fix: str
    group: str


@dataclass(slots=True)
class Finding:
    rule: str
    severity: str
    count: int
    detail: str
    lines: list[int] = field(default_factory=list)

    @property
    def label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, self.severity)


RULES: dict[str, Rule] = {
    r.id: r
    for r in [
        Rule("no-timestamp", "critical", "시각을 하나도 못 읽음",
             "시각이 없으면 순서도 구간도 비교도 만들 수 없다. 다른 로그와 맞춰 볼 수도 없다.",
             "로그 포맷에 ISO 8601 시각과 오프셋을 넣는다. 이미 있으면 형식을 이 도구에 알려 준다.",
             "parse"),
        Rule("partial-timestamp", "warn", "시각 없는 레코드",
             "일부 레코드(주로 JSON)에 시각이 없어 구간 계산에서 빠진다.",
             "구조적 로그에 `@timestamp`/`ts` 를 필수 필드로 만든다.",
             "parse"),
        Rule("orphan-lines", "info", "첫 사건 앞의 줄",
             "첫 레코드 앞줄은 앞 사건이 없어 붙일 곳이 없다. 배너·헤더면 문제없다.",
             "배너를 지우거나, 파일 첫 줄부터 시각이 오게 한다.",
             "parse"),
        Rule("no-timezone", "info", "오프셋 없는 시각",
             "오프셋이 없으면 서머타임·서버 이전·다중 리전에서 순서가 어긋난다.",
             "ISO 8601 에 `Z` 또는 `+09:00` 을 붙인다.",
             "time"),
        Rule("mixed-timezones", "warn", "한 파일에 여러 오프셋",
             "UTC 와 로컬 시각이 섞이면 9시간 차이가 나서 장애 순서가 뒤집힌다.",
             "모든 로거를 UTC 로 통일하고, 표시만 로컬로 바꾼다.",
             "time"),
        Rule("out-of-order", "warn", "시각이 뒤로 가는 줄",
             "여러 프로세스가 같은 파일에 쓰거나 버퍼가 늦게 비워지면 순서가 뒤집힌다.",
             "한 줄씩 즉시 flush 하고, 프로세스별 파일로 나눈 뒤 수집기에서 합친다.",
             "time"),
        Rule("future-timestamp", "info", "현재보다 미래의 시각",
             "서버 시계가 앞서 있거나 연도가 잘못 읽혔을 수 있다.",
             "NTP 를 확인하고, 연도 없는 포맷이면 연도를 명시한다.",
             "time"),
        Rule("year-assumed", "info", "연도를 이어받아 읽음",
             "syslog·Android 처럼 연도가 없는 표기는 앞 레코드의 연도를 쓴다. 연말·연초에 하루가 어긋난다.",
             "연도를 포함한 형식으로 바꾸거나 수집 시 연도를 붙인다.",
             "time"),
        Rule("time-gap", "warn", "로그가 끊긴 구간",
             "끊긴 구간은 '조용했다'가 아니라 '아무도 못 들었다'일 수 있다(에이전트 다운, 디스크 풀).",
             "수집 에이전트의 하트비트를 따로 남겨 끊김과 무음을 구분한다.",
             "time"),
        Rule("unknown-level", "info", "레벨을 못 읽은 줄",
             "레벨이 없으면 ERROR 와 INFO 를 구분할 수 없어 심각도 집계가 틀어진다.",
             "`level=` 필드나 `[LEVEL]` 토큰을 일관되게 넣는다.",
             "level"),
        Rule("level-case-mixed", "info", "같은 레벨의 다른 표기",
             "`WARN`/`warning`/`W` 가 섞이면 집계가 쪼개진다. 사람이 보면 같은데 도구는 다르게 센다.",
             "로거 설정에서 레벨 문자열을 하나로 고정한다.",
             "level"),
        Rule("error-without-trace", "info", "스택 없는 ERROR",
             "파일·줄이 없으면 고칠 곳을 찾는 데 시간이 걸린다. (Java 는 스택 없는 ERROR 가 흔하다.)",
             "에러 로거에 스택을 붙인다. 민감 정보는 스택에 넣지 않는다.",
             "level"),
        Rule("trace-without-error", "info", "ERROR 아닌 줄에 붙은 스택",
             "INFO/WARN 에 스택이 붙으면 진짜 에러 수가 과소집계된다.",
             "스택이 있는 로그는 ERROR 로 올린다.",
             "level"),
        Rule("empty-message", "warn", "본문이 빈 줄",
             "시각·레벨만 있고 내용이 없으면 그 사건은 나중에 아무것도 알려 주지 않는다.",
             "최소한 무엇을 하다 실패했는지 한 문장을 남긴다.",
             "shape"),
        Rule("one-line-storm", "warn", "한 서명이 절반 이상",
             "한 가지 메시지가 로그를 덮으면 다른 사건이 묻힌다. 대개 재시도 폭주다.",
             "같은 서명을 세어 요약으로 남기고, 원본은 샘플링한다.",
             "shape"),
        Rule("retry-storm", "warn", "같은 초에 같은 서명 반복",
             "재시도·재연결 폭주는 뒷단을 더 망가뜨린다. 백오프가 없다는 신호다.",
             "지수 백오프와 서킷 브레이커를 넣고, 재시도 횟수를 로그에 남긴다.",
             "shape"),
        Rule("error-burst", "warn", "오류가 몰린 구간",
             "평소의 몇 배가 한 구간에 몰리면 배포·설정 변경·외부 장애가 시작된 시점이다.",
             "그 구간의 배포·설정 변경 이력을 확인하고, 첫 발생 서명부터 본다.",
             "shape"),
        Rule("long-line", "info", "2,000자를 넘는 줄",
             "긴 줄은 대개 본문·base64·SQL 전문이다. 컨텍스트를 먹고 비밀을 품기 쉽다.",
             "본문은 잘라 찍고(앞 512자), 해시로 원문을 찾을 수 있게 한다.",
             "shape"),
        Rule("control-chars", "warn", "제어 문자",
             "제어 문자가 있으면 터미널·뷰어가 깨지고, 로그 위조(CR/LF 주입)에도 쓰인다.",
             "사용자 입력을 로그에 넣기 전에 이스케이프한다.",
             "shape"),
        Rule("mojibake", "warn", "깨진 글자",
             "인코딩이 어긋난 흔적이다. 지금은 읽히지만 검색·집계가 빗나간다.",
             "로그 파이프라인 전체를 UTF-8 로 맞추고, 들어오는 쪽에서 변환한다.",
             "parse"),
        Rule("mixed-formats", "info", "시각 표기가 여러 가지",
             "한 파일에 표기가 섞이면 정렬·파싱이 표기별로 달라진다.",
             "수집 단계에서 한 형식으로 정규화한다.",
             "parse"),
        Rule("secret-in-log", "critical", "비밀번호·토큰이 찍힘",
             "로그는 넓게 복사된다(에러 리포트, 티켓, LLM). 한 번 찍히면 회수할 수 없다.",
             "찍지 않는다. 찍혀 있으면 즉시 키를 회전하고 이 파일을 마스킹해 넘긴다.",
             "leak"),
        Rule("pii-in-log", "warn", "개인정보로 보이는 값",
             "이메일·전화·카드·IP 는 개인정보일 수 있다. 보존 기간과 접근 권한이 필요하다.",
             "필드를 마스킹하거나 해시로 바꾸고, 보존 기간을 정한다.",
             "leak"),
        Rule("no-request-id", "info", "상관관계 ID 없음",
             "여러 서비스 로그를 한 요청으로 묶을 수 없으면 장애 추적이 사람 손에 남는다.",
             "`trace_id`/`request_id` 를 모든 줄에 넣는다.",
             "trace"),
        Rule("unparsed-stack", "info", "위치를 못 읽은 스택",
             "프레임 형식을 몰라 '어디서 터졌는지'를 비워 두었다.",
             "스택 형식을 README 에 적어 두거나, 언어별 로거 기본 형식을 쓴다.",
             "trace"),
    ]
}


def _sample_lines(records: list[Record], limit: int = 3) -> list[int]:
    return [r.line_no for r in records[:limit]]


def check(log: LogFile, now: datetime | None = None) -> list[Finding]:
    findings: list[Finding] = []
    total = len(log.records)

    def add(rule_id: str, count: int, detail: str, lines: list[int] | None = None) -> None:
        if count <= 0:
            return
        spec = RULES[rule_id]
        findings.append(Finding(rule=rule_id, severity=spec.severity, count=count,
                                detail=detail, lines=lines or []))

    # ---------------------------------------------------------------- parse/time
    if total == 0:
        add("no-timestamp", 1, f"{log.total_lines:,}줄에서 시각을 하나도 읽지 못했습니다")
        return findings

    missing_ts = [r for r in log.records if r.ts is None]
    add("partial-timestamp", len(missing_ts), f"{len(missing_ts)}/{total} 레코드에 시각 없음",
        _sample_lines(missing_ts))
    add("orphan-lines", len(log.orphans), f"{len(log.orphans)}줄이 첫 사건 앞에 있음",
        [line_no for line_no, _ in log.orphans[:3]])

    offsets = log.tz_offsets()
    known = {key for key in offsets if key != "none"}
    none_count = offsets.get("none", 0)
    add("no-timezone", none_count, f"{none_count}/{total} 레코드에 오프셋 없음")
    add("mixed-timezones", len(known) if len(known) > 1 else 0,
        "오프셋 " + ", ".join(sorted(known)))
    add("year-assumed", sum(1 for r in log.records if "year-assumed" in r.flags),
        "연도 없는 표기를 앞 레코드 연도로 읽음")
    kinds = [k for k, _ in log.ts_kinds().most_common(4)]
    if len(kinds) > 1:
        add("mixed-formats", len(kinds), "표기 " + ", ".join(kinds))

    clusters = cluster(log)
    rate = analyze_rates(log, templates={c.signature: c.template for c in clusters})
    add("out-of-order", rate.out_of_order, f"{rate.out_of_order}줄이 직전 시각보다 이릅니다")
    if now is not None:
        future = [r for r in log.records if r.ts is not None and _naive(r.ts) > now + timedelta(minutes=5)]
        add("future-timestamp", len(future), f"{len(future)}줄이 현재보다 미래", _sample_lines(future))
    add("time-gap", len(rate.gaps),
        ", ".join(f"{g.seconds / 60:.0f}분" for g in rate.gaps[:3]) + f" ({len(rate.gaps)}곳)"
        if rate.gaps else "")

    # ---------------------------------------------------------------- level
    unknown = [r for r in log.records if r.level is None]
    add("unknown-level", len(unknown), f"{len(unknown)}/{total} 레코드에 레벨 없음",
        _sample_lines(unknown))
    seen: Counter = Counter()
    for record in log.records:
        if record.level and record.level_raw:
            seen[(record.level, record.level_raw)] += 1
    per_level: Counter = Counter()
    for (level, _raw), count in seen.items():
        per_level[level] += 1
    mixed = sum(1 for level, variants in per_level.items() if variants > 1)
    if mixed:
        example = next((level for level, variants in per_level.items() if variants > 1), "")
        variants = sorted({raw for (level, raw) in seen if level == example})
        add("level-case-mixed", mixed, f"{example}: " + ", ".join(variants[:4]))

    errors = log.error_records()
    untraced = [r for r in errors if not r.trace]
    add("error-without-trace", len(untraced), f"{len(untraced)}/{len(errors)} ERROR 에 스택 없음",
        _sample_lines(untraced))
    weird = [r for r in log.records if r.trace and r.level not in ("ERROR", "CRITICAL")]
    add("trace-without-error", len(weird), f"{len(weird)}줄에 ERROR 아닌 스택",
        _sample_lines(weird))

    # ---------------------------------------------------------------- shape
    empty = [r for r in log.records if not r.message.strip()]
    add("empty-message", len(empty), f"{len(empty)}줄의 본문이 비어 있음", _sample_lines(empty))

    if clusters:
        top, share = template_share(clusters, log)
        if share >= 50.0 and top.count >= 10:
            add("one-line-storm", top.count, f"'{top.template[:60]}' 가 {share:.0f}%")
    if rate.storms:
        worst = rate.storms[0]
        add("retry-storm", sum(s.count for s in rate.storms),
            f"{len(rate.storms)}개 서명이 같은 초에 몰림 (최대 {worst.count}회)")
    busy = rate.error_bursts
    if busy:
        add("error-burst", len(busy),
            f"{len(busy)}개 구간에서 오류 폭주 (최대 {max(b.count for b in busy)}건/"
            f"{rate.bucket_seconds}초, 평소 {rate.error_median:.0f}건)")

    long_lines = [r.line_no for r in log.records if len(r.raw) > 2000]
    add("long-line", len(long_lines), f"{len(long_lines)}줄이 2,000자 초과", long_lines[:3])
    control = [r.line_no for r in log.records if CONTROL.search(r.raw)]
    add("control-chars", len(control), f"{len(control)}줄에 제어 문자", control[:3])
    mojibake = [r.line_no for r in log.records if MOJIBAKE.search(r.raw)]
    add("mojibake", len(mojibake), f"{len(mojibake)}줄에 깨진 글자", mojibake[:3])

    # ---------------------------------------------------------------- leak
    redaction = redact_text("\n".join(log.iter_lines()))
    secret_kinds = {k: v for k, v in redaction.counts.items()
                    if k in ("private_key", "jwt", "bearer", "aws_key", "cloud_key",
                             "password", "api_key", "cookie")}
    pii_kinds = {k: v for k, v in redaction.counts.items()
                 if k in ("card", "phone", "email", "ip", "url_token")}
    if secret_kinds:
        add("secret-in-log", sum(secret_kinds.values()),
            ", ".join(f"{k} {v}" for k, v in sorted(secret_kinds.items(), key=lambda kv: -kv[1]))[:120])
    if pii_kinds:
        add("pii-in-log", sum(pii_kinds.values()),
            ", ".join(f"{k} {v}" for k, v in sorted(pii_kinds.items(), key=lambda kv: -kv[1]))[:120])

    # ---------------------------------------------------------------- trace
    from .parse import has_trace_id
    if errors and not any(has_trace_id(r) for r in log.records):
        add("no-request-id", len(errors), "ERROR 가 있는데 trace_id/request_id 가 한 줄도 없음")
    stacks = stack_report(log, clusters)
    unknown_stacks = sum(1 for g in stacks.groups if g.language == "unknown")
    add("unparsed-stack", unknown_stacks,
        f"{unknown_stacks}개 서명의 스택 위치를 못 읽음")

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), -f.count))
    return findings


def _naive(ts: datetime) -> datetime:
    return ts.replace(tzinfo=None)


def counts(findings: list[Finding]) -> Counter:
    return Counter(f.severity for f in findings)


def worst(findings: list[Finding]) -> str:
    if any(f.severity == "critical" for f in findings):
        return "critical"
    if any(f.severity == "warn" for f in findings):
        return "warn"
    if findings:
        return "info"
    return "ok"


def catalog(rule_id: str = "") -> list[Rule]:
    if rule_id:
        rule = RULES.get(rule_id)
        return [rule] if rule else []
    return list(RULES.values())
