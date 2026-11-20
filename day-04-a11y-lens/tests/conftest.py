"""공통 픽스처 — 페이지 한 장짜리 HTML 조각들과 사이트 폴더."""

from __future__ import annotations

from pathlib import Path

import pytest

BAD_PAGE = """<!doctype html>
<html>
<head><title>로그인</title></head>
<body>
<header><nav><a href="/"><img src="user.png"></a></nav></header>
<main>
  <h1>로그인</h1>
  <h4>계정</h4>
  <form>
    <input id="pw" type="password" placeholder="비밀번호">
    <label for="nope">닉네임</label>
    <button type="submit"><svg></svg></button>
  </form>
  <p>도움이 필요하면 <a href="/help">여기</a> 를 누르세요.</p>
  <table><tr><td>이름</td><td>금액</td></tr></table>
  <iframe src="https://map.example"></iframe>
</main>
</body></html>
"""

GOOD_PAGE = """<!doctype html>
<html lang="ko">
<head>
  <title>공지사항 – 예제</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
<header>
  <nav aria-label="주요 메뉴"><a href="/">홈</a></nav>
</header>
<main>
  <h1>공지사항</h1>
  <section aria-label="목록">
    <h2>이번 주</h2>
    <ul>
      <li><a href="/n/1">11월 20일 점검 안내</a></li>
    </ul>
  </section>
  <form>
    <label for="email">이메일</label>
    <input id="email" type="email" autocomplete="email">
    <button type="submit">구독하기</button>
  </form>
  <img src="logo.png" alt="예제 회사 로고">
  <img src="line.png" alt="">
  <table>
    <tr><th scope="col">이름</th><th scope="col">금액</th></tr>
    <tr><td>김</td><td>1000</td></tr>
  </table>
  <iframe src="https://map.example" title="지도: 서울시청"></iframe>
</main>
<footer><p>© 예제</p></footer>
</body></html>
"""


@pytest.fixture
def bad_page() -> str:
    return BAD_PAGE


@pytest.fixture
def good_page() -> str:
    return GOOD_PAGE


@pytest.fixture
def site(tmp_path) -> Path:
    root = tmp_path / "site"
    (root / "sub").mkdir(parents=True)
    (root / "index.html").write_text(
        """<!doctype html><html lang="ko"><head><title>홈</title></head>
<body><main><h1>홈</h1><img src="a.png"><img src="b.png"></main></body></html>""",
        encoding="utf-8",
    )
    (root / "about.html").write_text(
        """<!doctype html><html lang="ko"><head><title>소개</title></head>
<body><main><h1>소개</h1><img src="c.png"></main></body></html>""",
        encoding="utf-8",
    )
    (root / "sub" / "deep.html").write_text(
        """<!doctype html><html lang="ko"><head><title>깊은 쪽</title></head>
<body><main><h1>깊은 쪽</h1><button></button></main></body></html>""",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def lens_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "lens-home"
    home.mkdir()
    monkeypatch.setenv("A11Y_LENS_HOME", str(home))
    return home
