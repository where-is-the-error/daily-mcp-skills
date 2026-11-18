"""URL 검사 · robots · 크기/형식 상한."""

from __future__ import annotations

import socket

import pytest

from web_memo import fetch


# ------------------------------------------------------------------ normalize
def test_normalize_adds_https() -> None:
    assert fetch.normalize_url("example.com/a") == "https://example.com/a"


def test_normalize_strips_fragment_and_default_port() -> None:
    assert fetch.normalize_url("https://example.com:443/a#part") == "https://example.com/a"


def test_normalize_keeps_query() -> None:
    assert fetch.normalize_url("https://example.com/a?x=1") == "https://example.com/a?x=1"


def test_normalize_rejects_empty() -> None:
    with pytest.raises(fetch.FetchRefused):
        fetch.normalize_url("   ")


def test_normalize_rejects_other_schemes() -> None:
    for url in ("file:///etc/passwd", "ftp://example.com/x", "data:text/html,hi"):
        with pytest.raises(fetch.FetchRefused):
            fetch.normalize_url(url)


# ------------------------------------------------------------------ private nets
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "10.1.2.3", "192.168.0.7", "169.254.169.254", "::1", "0.0.0.0"],
)
def test_private_hosts_are_detected(host: str) -> None:
    assert fetch.is_private_host(host) is True


def test_public_host_is_not_private() -> None:
    assert fetch.is_private_host("8.8.8.8") is False


def test_localhost_name_resolves_to_loopback(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("127.0.0.1", 0))]
    )
    assert fetch.is_private_host("localhost") is True


def test_private_url_is_refused_before_network(monkeypatch) -> None:
    def boom(*args, **kwargs):  # pragma: no cover - 호출되면 실패
        raise AssertionError("사설망인데 네트워크를 건드렸습니다")

    monkeypatch.setattr(fetch, "http_get", boom)
    with pytest.raises(fetch.FetchRefused):
        fetch.fetch_page("http://127.0.0.1:8000/admin")


def test_allow_private_lets_local_through(monkeypatch) -> None:
    monkeypatch.setattr(
        fetch, "http_get", lambda url, **kw: (200, "text/html; charset=utf-8", b"<html><body><p>local</p></body></html>")
    )
    page = fetch.fetch_page("http://127.0.0.1:8000/", allow_private=True, respect_robots=False)
    assert "local" in page.text


# ------------------------------------------------------------------ robots
def _router(page_html: bytes = b"<html><body><p>hello world</p></body></html>"):
    def http_get(url, *, user_agent=fetch.DEFAULT_USER_AGENT, timeout=20, max_bytes=fetch.MAX_BYTES):
        if url.endswith("/robots.txt"):
            return 200, "text/plain", b"User-agent: *\nDisallow: /private\n"
        return 200, "text/html; charset=utf-8", page_html

    return http_get


def test_robots_disallow_blocks(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "http_get", _router())
    with pytest.raises(fetch.FetchRefused) as excinfo:
        fetch.fetch_page("https://example.com/private/secret")
    assert "robots" in str(excinfo.value)


def test_robots_allow_lets_through(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "http_get", _router())
    page = fetch.fetch_page("https://example.com/docs")
    assert "hello world" in page.text
    assert "robots.txt 허용" in page.robots_url


def test_missing_robots_is_treated_as_allowed(monkeypatch) -> None:
    def http_get(url, **_):
        if url.endswith("/robots.txt"):
            raise fetch.FetchError("없음")
        return 200, "text/html", b"<html><body><p>ok</p></body></html>"

    monkeypatch.setattr(fetch, "http_get", http_get)
    page = fetch.fetch_page("https://example.com/x")
    assert "ok" in page.text
    assert "허용" in page.robots_url


def test_robots_cache_is_reused(monkeypatch) -> None:
    calls: list[str] = []

    def http_get(url, **kw):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 200, "text/plain", b"User-agent: *\nAllow: /\n"
        return 200, "text/html", b"<html><body><p>page</p></body></html>"

    monkeypatch.setattr(fetch, "http_get", http_get)
    cache = fetch.RobotsCache()
    fetch.fetch_page("https://example.com/a", robots=cache)
    fetch.fetch_page("https://example.com/b", robots=cache)
    assert sum(1 for url in calls if url.endswith("/robots.txt")) == 1


# ------------------------------------------------------------------ limits
def test_non_document_content_type_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "http_get", lambda url, **kw: (200, "application/pdf", b"%PDF-1.7"))
    with pytest.raises(fetch.FetchRefused):
        fetch.fetch_page("https://example.com/file.pdf")


def test_oversized_response_is_refused(monkeypatch) -> None:
    def http_get(url, **kw):
        raise fetch.FetchRefused("응답이 5.0MB 상한을 넘습니다")

    monkeypatch.setattr(fetch, "http_get", http_get)
    with pytest.raises(fetch.FetchRefused):
        fetch.fetch_page("https://example.com/huge")


def test_max_chars_truncates_text(monkeypatch) -> None:
    body = "<html><body>" + "".join(f"<p>줄 {i} 내용입니다</p>" for i in range(400)) + "</body></html>"
    monkeypatch.setattr(fetch, "http_get", _router(body.encode()))
    page = fetch.fetch_page("https://example.com/long", max_chars=500)
    assert page.truncated is True
    assert len(page.text) < 800


def test_http_error_becomes_fetch_error(monkeypatch) -> None:
    def http_get(url, **kw):
        raise fetch.FetchError("HTTP 404 — https://example.com/gone")

    monkeypatch.setattr(fetch, "http_get", http_get)
    with pytest.raises(fetch.FetchError):
        fetch.fetch_page("https://example.com/gone")


def test_charset_from_header_is_used(monkeypatch) -> None:
    body = "<html><body><p>한글 문서</p></body></html>".encode("euc-kr")
    monkeypatch.setattr(fetch, "http_get", lambda url, **kw: (200, "text/html; charset=euc-kr", body))
    page = fetch.fetch_page("https://example.com/kr", respect_robots=False)
    assert "한글 문서" in page.text


def test_plain_text_page_has_no_html_parsing(monkeypatch) -> None:
    monkeypatch.setattr(
        fetch, "http_get", lambda url, **kw: (200, "text/plain; charset=utf-8", "제목\n본문".encode())
    )
    page = fetch.fetch_page("https://example.com/raw.txt", respect_robots=False)
    assert page.text == "제목\n본문"


# ------------------------------------------------------------------ robots rules
def test_allow_root_does_not_override_longer_disallow() -> None:
    """`Allow: /` 뒤에 `Disallow: /admin` — 긴 패턴이 이긴다."""
    rules = fetch.RobotsRules(["User-agent: *", "Allow: /", "Disallow: /admin"])
    assert rules.allows("https://e.com/index.html") is True
    assert rules.allows("https://e.com/admin/secret") is False


def test_longer_allow_wins_over_disallow() -> None:
    rules = fetch.RobotsRules(
        ["User-agent: *", "Disallow: /docs", "Allow: /docs/public"]
    )
    assert rules.allows("https://e.com/docs/private") is False
    assert rules.allows("https://e.com/docs/public/x") is True


def test_wildcard_and_end_anchor() -> None:
    rules = fetch.RobotsRules(["User-agent: *", "Disallow: /*.pdf$"])
    assert rules.allows("https://e.com/a/file.pdf") is False
    assert rules.allows("https://e.com/a/file.pdf.html") is True


def test_specific_user_agent_group_wins() -> None:
    rules = fetch.RobotsRules(
        [
            "User-agent: *",
            "Disallow: /",
            "",
            "User-agent: web-memo",
            "Allow: /",
            "Disallow: /private",
        ],
        user_agent="web-memo/0.1 (+https://example.com)",
    )
    assert rules.allows("https://e.com/docs") is True
    assert rules.allows("https://e.com/private/x") is False


def test_empty_disallow_means_allow_all() -> None:
    rules = fetch.RobotsRules(["User-agent: *", "Disallow:"])
    assert rules.allows("https://e.com/anything") is True


def test_no_matching_group_allows() -> None:
    rules = fetch.RobotsRules(["User-agent: googlebot", "Disallow: /"])
    assert rules.allows("https://e.com/") is True


def test_comments_are_ignored() -> None:
    rules = fetch.RobotsRules(["User-agent: *  # 모두", "Disallow: /tmp  # 임시"])
    assert rules.allows("https://e.com/tmp/a") is False
