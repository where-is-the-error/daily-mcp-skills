"""URL 하나를 안전하게 가져와 읽을 수 있는 텍스트로 만든다.

Fetch MCP에서 가져온 설계
- **robots.txt를 먼저 본다** (호스트별 캐시, RFC 9309 longest-match)
- **길이 상한**을 두고 자른다 (Fetch MCP의 `max_length`/`start_index` 자리)
- 문서가 아닌 응답(text/* 가 아닌 것)은 거부한다

여기서 더한 것
- **사설망 차단**: `localhost`, `127.0.0.1`, `10.x`, `169.254.x` … 로 향하는 URL은
  DNS 해석 결과까지 확인해 거부한다. 에이전트가 사내망을 찍는 사고를 막는다.
- 스킴은 `http`/`https`만. `file:`·`data:`·`ftp:`는 애초에 열지 않는다.
- 본문 바이트 상한(5 MB)과 타임아웃(20초).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import extract as extractor

__all__ = [
    "Page",
    "FetchError",
    "FetchRefused",
    "DEFAULT_USER_AGENT",
    "normalize_url",
    "is_private_host",
    "fetch_page",
    "RobotsCache",
]

DEFAULT_USER_AGENT = (
    "web-memo/0.1 (+https://github.com/where-is-the-error/daily-mcp-skills)"
)
MAX_BYTES = 5_000_000
DEFAULT_TIMEOUT = 20.0
ROBOTS_MAX_BYTES = 512_000
DOCUMENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
)


class FetchError(Exception):
    """가져오지 못했다 (네트워크·HTTP 오류)."""


class FetchRefused(FetchError):
    """정책상 가져오지 않는다 (스킴·사설망·robots·MIME·크기)."""


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    status: int
    title: str
    text: str
    content_type: str
    size_bytes: int
    fetched_at: datetime
    truncated: bool = False
    robots_url: str = ""
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------- URL
def normalize_url(url: str) -> str:
    """스킴·호스트 검사와 정규화. 같은 페이지는 같은 키가 되게 만든다."""
    raw = (url or "").strip()
    if not raw:
        raise FetchRefused("URL이 비어 있습니다.")
    scheme_hint = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", raw)
    if scheme_hint and scheme_hint.group(1).lower() not in ("http", "https"):
        raise FetchRefused(
            f"{scheme_hint.group(1)}: 스킴은 지원하지 않습니다. http/https만 됩니다."
        )
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchRefused(f"{scheme}: 스킴은 지원하지 않습니다. http/https만 됩니다.")
    if not parsed.hostname:
        raise FetchRefused("호스트가 없습니다.")
    host = parsed.hostname.lower()
    if ":" in host:  # IPv6
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError as exc:
        raise FetchRefused(f"포트가 올바르지 않습니다 — {raw}") from exc
    # 기본 포트는 떼어 같은 페이지가 같은 키가 되게 한다
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def is_private_host(host: str) -> bool:
    """루프백·사설·링크로컬·예약 대역인가 (DNS 해석 결과까지 확인)."""
    candidates: list[str] = []
    literal = host.strip("[]")
    try:
        candidates.append(str(ipaddress.ip_address(literal)))
    except ValueError:
        try:
            infos = socket.getaddrinfo(literal, None)
        except socket.gaierror:
            return False  # 해석 불가 → 아래 http 단계에서 오류로 처리
        candidates = sorted({info[4][0] for info in infos})

    for ip_text in candidates:
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


# --------------------------------------------------------------------- HTTP
def _decode(body: bytes, content_type: str) -> str:
    charset = ""
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
    if not charset:
        head = body[:2048].decode("ascii", "ignore").lower()
        if "charset=" in head:
            charset = head.split("charset=")[-1].split('"')[0].split("'")[0].split(">")[0]
            charset = charset.strip().strip(';').split()[0] if charset.strip() else ""
    for candidate in (charset, "utf-8"):
        if not candidate:
            continue
        try:
            return body.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def http_get(
    url: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BYTES,
) -> tuple[int, str, bytes]:
    """(status, content_type, body). 실패는 FetchError로 올린다."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Language": "ko,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            content_type = response.headers.get("Content-Type", "")
            body = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} — {url}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"연결 실패 — {url} ({exc.reason})") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FetchError(f"시간 초과({timeout:.0f}s) — {url}") from exc
    if len(body) > max_bytes:
        raise FetchRefused(
            f"응답이 {max_bytes / 1_000_000:.1f}MB 상한을 넘습니다 — {url}"
        )
    return status, content_type, body


# --------------------------------------------------------------------- robots
@dataclass(frozen=True)
class _Rule:
    pattern: str
    allow: bool


def _path_matches(pattern: str, path: str) -> bool:
    """RFC 9309 경로 매칭 — `*` 와 끝의 `$` 를 지원한다."""
    if not pattern:
        return True
    if "*" in pattern or pattern.endswith("$"):
        body = pattern[:-1] if pattern.endswith("$") else pattern
        regex = "^" + re.escape(body).replace(r"\*", ".*")
        if pattern.endswith("$"):
            regex += "$"
        return re.match(regex, path) is not None
    return path.startswith(pattern)


class RobotsRules:
    """robots.txt 규칙 — **가장 긴 패턴이 이긴다** (같으면 Allow 우선).

    표준 라이브러리 `urllib.robotparser`는 규칙을 **파일에 적힌 순서대로** 처음
    맞는 것만 보기 때문에, `Allow: /` 다음에 `Disallow: /admin`이 오면 admin을
    막지 못한다. 실제 robots.txt에 흔한 모양이라 직접 구현했다.
    """

    def __init__(self, lines: list[str], user_agent: str = DEFAULT_USER_AGENT) -> None:
        groups: list[tuple[list[str], list[_Rule]]] = []
        agents: list[str] = []
        rules: list[_Rule] = []
        in_rules = False
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if in_rules:
                    groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(value.lower())
            elif key in ("allow", "disallow") and agents:
                in_rules = True
                rules.append(_Rule(value, key == "allow"))
        if agents:
            groups.append((agents, rules))

        self.rules: list[_Rule] = []
        ua = (user_agent or "").lower()
        best_len = 0
        for group_agents, group_rules in groups:
            for agent in group_agents:
                token = agent.split("/")[0].strip()
                if token and token != "*" and token in ua and len(token) > best_len:
                    self.rules, best_len = group_rules, len(token)
        if not self.rules:
            for group_agents, group_rules in groups:
                if any(a.strip() == "*" for a in group_agents):
                    self.rules = group_rules
                    break

    def allows(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        verdict = True
        best = -1
        for rule in self.rules:
            if not rule.pattern:
                continue  # 빈 Disallow: 는 "전부 허용"
            if _path_matches(rule.pattern, path):
                if len(rule.pattern) > best:
                    best, verdict = len(rule.pattern), rule.allow
                elif len(rule.pattern) == best:
                    verdict = verdict or rule.allow
        return verdict


class RobotsCache:
    """호스트별 robots.txt 판정. 한 번 읽고 기억한다."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, ttl: float = 3600.0) -> None:
        self.user_agent = user_agent
        self.ttl = ttl
        self._cache: dict[str, tuple[float, RobotsRules | None]] = {}

    def rules_for(self, url: str) -> RobotsRules | None:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        now = time.monotonic()
        cached = self._cache.get(origin)
        if cached and now - cached[0] < self.ttl:
            return cached[1]
        robots_url = f"{origin}/robots.txt"
        try:
            _, content_type, body = http_get(
                robots_url, user_agent=self.user_agent, max_bytes=ROBOTS_MAX_BYTES
            )
            rules: RobotsRules | None = RobotsRules(_decode(body, content_type).splitlines(), self.user_agent)
        except FetchError:
            rules = None  # 없거나 못 읽으면 표준 관례대로 허용
        self._cache[origin] = (now, rules)
        return rules

    def allowed(self, url: str) -> tuple[bool, str]:
        """(허용 여부, 근거)."""
        rules = self.rules_for(url)
        if rules is None:
            return True, "robots.txt 없음/읽기 실패 → 허용"
        if rules.allows(url):
            return True, "robots.txt 허용"
        return False, "robots.txt 가 이 경로를 막습니다"


# --------------------------------------------------------------------- fetch
def fetch_page(
    url: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    max_chars: int = 12_000,
    respect_robots: bool = True,
    allow_private: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    now: datetime | None = None,
    robots: RobotsCache | None = None,
) -> Page:
    """URL → Page. 정책 위반은 FetchRefused, 통신 실패는 FetchError."""
    target = normalize_url(url)
    host = urllib.parse.urlsplit(target).hostname or ""
    if not allow_private and is_private_host(host):
        raise FetchRefused(
            f"사설망·루프백 주소는 열지 않습니다 ({host}). 로컬 테스트는 allow_private=True."
        )

    robots = robots or RobotsCache(user_agent)
    robots_url = ""
    if respect_robots:
        allowed, why = robots.allowed(target)
        robots_url = why
        if not allowed:
            raise FetchRefused(f"{why} — {target}")

    status, content_type, body = http_get(target, user_agent=user_agent, timeout=timeout)
    base_type = content_type.split(";")[0].strip().lower()
    if base_type and not any(base_type.startswith(t) for t in DOCUMENT_TYPES):
        raise FetchRefused(f"문서가 아닙니다 ({base_type}) — {target}")

    raw = _decode(body, content_type)
    if base_type in ("text/plain", "text/markdown") or not base_type:
        text = extractor.collapse(raw)
        title = extractor._first_heading(text)
    else:
        doc = extractor.extract(raw)
        text, title = doc.text, doc.title

    text, truncated = extractor.truncate(text, max_chars)
    return Page(
        url=target,
        final_url=target,
        status=status,
        title=title,
        text=text,
        content_type=base_type or "text/plain",
        size_bytes=len(body),
        fetched_at=now or datetime.now(timezone.utc),
        truncated=truncated,
        robots_url=robots_url,
    )
