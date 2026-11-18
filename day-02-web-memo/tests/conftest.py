"""공통 픽스처."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from web_memo import db
from web_memo.fetch import Page

ARTICLES = {
    "guide": """
<!doctype html>
<html lang="ko">
<head><title>MCP 서버 만들기 · 가이드</title></head>
<body>
  <header><a href="/">로고</a><a href="/login">로그인</nav></header>
  <nav><a href="/docs">문서</a><a href="/api">API</a></nav>
  <main>
    <h1>MCP 서버 만들기</h1>
    <p>MCP 서버는 tools·resources·prompts 세 가지를 노출할 수 있습니다.</p>
    <p>stdio 전송을 쓰면 클라이언트가 프로세스를 직접 띄웁니다.</p>
    <ul><li>툴 정의는 짧게</li><li>에러는 문자열로</li></ul>
  </main>
  <aside>광고 배너</aside>
  <footer>© 2026 어딘가</footer>
  <script>console.log("추적 코드")</script>
</body>
</html>
""",
}


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    connection = db.connect(tmp_path / "memo.db")
    yield connection
    connection.close()


@pytest.fixture
def guide_html() -> str:
    return ARTICLES["guide"]


def make_page(url: str = "https://example.com/docs/guide",
              title: str = "MCP 서버 만들기",
              text: str | None = None,
              when: str = "2026-11-18T01:00:00+00:00") -> Page:
    body = text if text is not None else "\n".join(
        f"문단 {i}: MCP 서버는 툴을 노출합니다." for i in range(1, 6)
    )
    return Page(
        url=url,
        final_url=url,
        status=200,
        title=title,
        text=body,
        content_type="text/html",
        size_bytes=len(body),
        fetched_at=datetime.fromisoformat(when),
    )
