"""마스킹 — 로그를 LLM·이슈 트래커로 옮기기 전에.

로그에는 비밀번호가 다섯 번 찍히는 게 정상이다(요청·응답·미들웨어·재시도·에러).
한 곳만 지우면 나머지 네 곳이 그대로 남는다. 그래서 여기서는 **줄 단위로 전체**를
훑고, 지운 뒤에 같은 탐지기를 한 번 더 돌려 '남은 것 0'을 확인한다.

탐지기는 넓게 잡되, 무엇을 지웠는지 종류와 개수를 남긴다. 값은 절대 돌려주지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = {
    "private_key": "개인 키 블록",
    "jwt": "JWT",
    "bearer": "Bearer 토큰",
    "aws_key": "AWS 액세스 키",
    "cloud_key": "클라우드 키 (sk-/ghp-/xox)",
    "password": "비밀번호 필드",
    "api_key": "API 키 필드",
    "cookie": "쿠키/세션",
    "card": "카드번호",
    "phone": "전화번호",
    "email": "이메일",
    "ip": "IP 주소",
    "url_token": "URL 안 토큰",
}

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("cloud_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{8,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bxox[baprs]-[A-Za-z0-9-]{8,}")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|pass)\b\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;&\"']{1,80})")),
    ("api_key", re.compile(r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token)\b\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;&\"']{6,120})")),
    ("cookie", re.compile(r"(?i)(?:\b(?:set-)?cookie\b\s*[:=]\s*[^\n]{6,200}|\bsession(?:id)?\s*[:=]\s*[A-Za-z0-9._\-]{8,})")),
    ("card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("phone", re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b|\+82[- ]?10[- ]?\d{4}[- ]?\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("url_token", re.compile(r"(?i)[?&](?:token|key|sig|signature|password|auth)=[^&\s\"']{4,}")),
    ("ip", re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")),
]

CARD_HINT = re.compile(r"\d{4}[ -]?\d{4}[ -]?\d{4}")

# 값 전체를 지우면 문장이 무너진다. 종류 이름만 남기고 값은 통째로 지운다.
MASK = "<redacted:{kind}>"


@dataclass(slots=True)
class Redaction:
    counts: dict[str, int] = field(default_factory=dict)
    lines_changed: int = 0
    chars_before: int = 0
    chars_after: int = 0
    residual: dict[str, int] = field(default_factory=dict)
    texts: list[tuple[int, str]] = field(default_factory=list)   # (줄 번호, 마스킹된 줄)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def residual_total(self) -> int:
        return sum(self.residual.values())


def _luhn(number: str) -> bool:
    digits = [int(ch) for ch in number if ch.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _candidates(line: str) -> set[str]:
    """값의 모양으로 먼저 거른다 — 13개 정규식을 모든 줄에 다 돌리면 10만 줄에서 4초."""
    lower = line.lower()
    found: set[str] = set()
    if "-----begin" in lower:
        found.add("private_key")
    if "eyj" in lower:
        found.add("jwt")
    if "bearer" in lower:
        found.add("bearer")
    if "akia" in lower or "asia" in lower:
        found.add("aws_key")
    if "sk_live" in line or "sk_test" in line or "ghp_" in line or "xox" in lower:
        found.add("cloud_key")
    if "password" in lower or "passwd" in lower or "pwd" in lower or "secret" in lower:
        found.add("password")
    if "key" in lower or "token" in lower or "auth" in lower:
        found.add("api_key")
    if "cookie" in lower or "session" in lower:
        found.add("cookie")
    if "@" in line:
        found.add("email")
    if CARD_HINT.search(line):
        found.add("card")
    if "010" in line or "+82" in line:
        found.add("phone")
    if "token=" in lower or "key=" in lower or "sig=" in lower or "auth=" in lower:
        found.add("url_token")
    if line.count(".") >= 3 and re.search(r"\d", line):
        found.add("ip")
    return found


def mask_line(line: str, counts: dict[str, int] | None = None) -> str:
    """한 줄 안의 비밀·식별자를 종류 이름으로 바꾼다."""
    counts = counts if counts is not None else {}
    text = line
    wanted = _candidates(line)
    for kind, pattern in PATTERNS:
        if kind not in wanted:
            continue
        if kind == "card":
            def card_sub(match: re.Match) -> str:
                if _luhn(match.group(0)):
                    counts[kind] = counts.get(kind, 0) + 1
                    return MASK.format(kind=kind)
                return match.group(0)
            text = pattern.sub(card_sub, text)
            continue
        if kind == "phone":
            def phone_sub(match: re.Match) -> str:
                counts[kind] = counts.get(kind, 0) + 1
                return MASK.format(kind=kind)
            text = pattern.sub(phone_sub, text)
            continue
        def sub(match: re.Match, kind=kind) -> str:
            counts[kind] = counts.get(kind, 0) + 1
            if kind in ("password", "api_key", "cookie", "url_token"):
                # `password=xxx` → `password=<redacted>`
                body = match.group(0)
                sep = re.search(r"[=:]\s*", body)
                if sep:
                    head = body[: sep.end()]
                    return head + MASK.format(kind=kind)
            return MASK.format(kind=kind)
        text = pattern.sub(sub, text)
    return text


def redact_text(text: str, first_line: int = 1) -> Redaction:
    # 여러 줄에 걸친 것(개인 키 블록)은 줄 단위로는 못 잡는다 — 먼저 통째로 지운다.
    counts0: dict[str, int] = {}
    for kind, pattern in PATTERNS:
        if kind != "private_key":
            continue
        def block_sub(match: re.Match, kind=kind) -> str:
            counts0[kind] = counts0.get(kind, 0) + 1
            return MASK.format(kind=kind) * max(1, match.group(0).count("\n") + 1)
        text = pattern.sub(block_sub, text)

    lines = text.splitlines()
    counts: dict[str, int] = dict(counts0)
    out: list[tuple[int, str]] = []
    changed = 0
    for offset, line in enumerate(lines):
        masked = mask_line(line, counts)
        if masked != line:
            changed += 1
        out.append((first_line + offset, masked))

    masked_text = "\n".join(line for _, line in out)
    residual: dict[str, int] = {}
    for kind, pattern in PATTERNS:
        found = [m.group(0) for m in pattern.finditer(masked_text)]
        # 방금 넣은 자리표시자(`password=<redacted:password>`)는 남은 값이 아니다.
        found = [f for f in found if "<redacted:" not in f]
        if kind == "card":
            found = [f for f in found if _luhn(f)]
        if found:
            residual[kind] = len(found)

    return Redaction(counts=counts, lines_changed=changed,
                     chars_before=len(text), chars_after=len(masked_text),
                     residual=residual, texts=out)


def redact_log(text: str) -> str:
    return "\n".join(line for _, line in redact_text(text).texts)
