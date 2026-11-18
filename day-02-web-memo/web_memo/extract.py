"""HTML → 읽을 수 있는 텍스트.

브라우저 엔진을 쓰지 않는다. JS를 실행하지 않고 마크업만 훑는다는 뜻이고,
그래서 SPA 문서는 본문이 비어 나올 수 있다(README '한계' 참고).

Fetch MCP가 쓰는 readabilipy/HTML→Markdown 방향을 참고했지만,
의존성 없이 돌아가도록 표준 라이브러리 `html.parser`로 다시 작성했다.

규칙
- `script`/`style`/`nav`/`header`/`footer`/`aside`/`form` 등은 본문에서 뺀다.
- `hidden`·`aria-hidden="true"` 요소도 뺀다.
- `<main>`이나 `<article>`이 있고 그 안의 글이 충분히 길면 그쪽만 쓴다.
- 블록 태그는 줄바꿈, `<img alt>`는 `[alt]`로 남긴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

__all__ = ["Document", "extract", "truncate", "collapse"]

SKIP_TAGS = {
    "script", "style", "noscript", "template", "svg", "canvas", "iframe",
    "nav", "header", "footer", "aside", "form", "button", "select", "input",
    "dialog", "video", "audio", "figure", "figcaption",
}

BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "dl", "dt", "dd",
    "tr", "table", "thead", "tbody", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "br", "hr", "td", "th", "details", "summary",
}

_WS = re.compile(r"[ \t\u00a0\u200b]+")
_BOILERPLATE = re.compile(
    r"(^|[-_ ])(nav|navbar|navigation|sidebar|breadcrumb|footer|header|menu|toc|"
    r"related|banner|ads?|cookie|share|social|skip-link|sr-only)($|[-_ ])"
)
_MULTI_NL = re.compile(r"\n{3,}")

MIN_MAIN_CHARS = 200


@dataclass(frozen=True)
class Document:
    title: str
    text: str
    chars: int


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool, bool]] = []  # (tag, skip, main)
        self._skip = 0
        self._main = 0
        self._buf: list[str] = []
        self._main_text: list[str] = []
        self._everything: list[str] = []
        self._in_title = False
        self._title_buf: list[str] = []

    # ------------------------------------------------------------------ emitting
    def _emit(self, s: str) -> None:
        if not s:
            return
        self._everything.append(s)
        if self._main > 0:
            self._buf.append(s)

    # ------------------------------------------------------------------ parser
    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: D102
        tag = tag.lower()
        amap = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
            return

        hidden = "hidden" in amap or amap.get("aria-hidden", "").lower() == "true"
        marker = f"{amap.get('class', '')} {amap.get('id', '')}".strip().lower()
        boilerplate = bool(marker) and bool(_BOILERPLATE.search(marker))
        is_skip = tag in SKIP_TAGS or hidden or boilerplate
        is_main = tag in ("main", "article") or amap.get("role", "").lower() == "main"
        self._stack.append((tag, is_skip, is_main))

        if is_skip:
            self._skip += 1
            return

        if is_main:
            if self._main == 0:
                self._buf = []
            self._main += 1

        if tag in BLOCK_TAGS:
            self._emit("\n")
        if tag == "img":
            alt = amap.get("alt", "").strip()
            if alt:
                self._emit(f"[{alt}]")

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: D102
        tag = tag.lower()
        if tag in ("br", "hr"):
            if not self._skip:
                self._emit("\n")
        elif tag == "img":
            amap = {k.lower(): (v or "") for k, v in attrs}
            alt = amap.get("alt", "").strip()
            if alt and not self._skip:
                self._emit(f"[{alt}]")

    def handle_endtag(self, tag: str) -> None:  # noqa: D102
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if not any(t == tag for t, _, _ in self._stack):
            return  # 짝이 없는 닫힘 태그는 무시

        while self._stack:
            t, is_skip, is_main = self._stack.pop()
            if is_skip:
                self._skip = max(0, self._skip - 1)
            if is_main:
                if self._main > 0:
                    self._main -= 1
                if self._main == 0:
                    self._main_text = self._buf
                    self._buf = []
            if t == tag:
                break

        if tag in BLOCK_TAGS and not self._skip:
            self._emit("\n")

    def handle_data(self, data: str) -> None:  # noqa: D102
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._skip:
            return
        self._emit(data)

    # ------------------------------------------------------------------ result
    def finish(self) -> Document:
        title = collapse(" ".join(self._title_buf))
        main = collapse("".join(self._main_text))
        everything = collapse("".join(self._everything))
        text = main if len(main) >= MIN_MAIN_CHARS else everything
        if not title:
            title = _first_heading(text)
        return Document(title=title[:200].strip(), text=text, chars=len(text))


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if 8 <= len(line) <= 120:
            return line
    return ""


def collapse(text: str) -> str:
    """공백·줄바꿈을 정리해 비교 가능한 형태로 만든다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    return _MULTI_NL.sub("\n\n", "\n".join(out)).strip()


def extract(markup: str) -> Document:
    """HTML 문자열 → Document."""
    parser = _Extractor()
    parser.feed(markup)
    parser.close()
    return parser.finish()


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    """문자 상한으로 자른다. (텍스트, 잘렸는지)."""
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    space = cut.rfind(" ")  # 단어 중간에서 끊기지 않게
    if space > max_chars * 0.8:
        cut = cut[:space]
    return cut.rstrip() + "\n\n… (길이 제한으로 잘림)", True
