"""캡션 읽기 — 첫 줄(훅)·해시태그·멘션·링크·길이·언어.

캡션을 고치지 않는다. 고치기 전에 무엇이 들어 있는지 세기만 한다.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .types import CaptionFacts

HASHTAG_RE = re.compile(r"#([^\s#.,!?;:)\]}\"'…]+)")
MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{2,})")
LINK_RE = re.compile(r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+)")
SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
URL_TRAIL = ".,!?;:)]}'\"…"
HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")

VAGUE_HASHTAGS = {
    "fyp", "foryou", "foryoupage", "fy", "viral", "trending", "explore",
    "love", "instagood", "photooftheday", "followme", "likeforlike", "l4l",
    "reels", "reelsvideo", "shorts", "shortvideo", "youtubeshorts", "추천",
    "떡상", "좋아요반사", "팔로우", "인기",
}


def _is_emoji(ch: str) -> bool:
    code = ord(ch)
    if code in (0x200D, 0xFE0F, 0x20E3):
        return False
    return (
        0x1F300 <= code <= 0x1FAFF
        or 0x1F000 <= code <= 0x1F2FF
        or 0x2600 <= code <= 0x27BF
        or 0x2B00 <= code <= 0x2BFF
    )


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def find_hashtags(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for match in HASHTAG_RE.finditer(text):
        tag = match.group(1).strip(URL_TRAIL)
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return tuple(out)


def find_mentions(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for match in MENTION_RE.finditer(text):
        handle = match.group(1).rstrip(".")
        key = handle.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(handle)
    return tuple(out)


def find_links(text: str) -> tuple[str, ...]:
    out: list[str] = []
    for match in LINK_RE.finditer(text):
        link = match.group(1).rstrip(URL_TRAIL)
        if link and link not in out:
            out.append(link)
    return tuple(out)


def emoji_count(text: str) -> int:
    return sum(1 for ch in text if _is_emoji(ch))


def detect_language(text: str) -> str:
    hangul = len(HANGUL_RE.findall(text))
    latin = len(LATIN_RE.findall(text))
    if hangul == 0 and latin == 0:
        return "unknown"
    total = hangul + latin
    if hangul / total >= 0.6:
        return "ko"
    if latin / total >= 0.9:
        return "en"
    return "mixed"


def body_without_hashtag_tail(text: str) -> str:
    lines = text.split("\n")
    while lines and lines[-1].strip() and HASHTAG_RE.search(lines[-1]):
        stripped = HASHTAG_RE.sub("", lines[-1])
        stripped = re.sub(r"[\s,·]+", " ", stripped).strip()
        if stripped:
            break
        lines.pop()
    return "\n".join(lines).strip()


def read_caption(text: str = "", path: str = "", hook: str = "", section: str = "") -> CaptionFacts:
    if not text and path:
        text = Path(path).expanduser().read_text(encoding="utf-8")
    text = normalize(text)
    if section:
        text = extract_section(text, section)
    lines = tuple(line for line in text.split("\n"))
    non_empty = [line.strip() for line in lines if line.strip()]
    first_line = non_empty[0] if non_empty else ""
    hook_text = normalize(hook).strip() if hook else first_line
    plain = SPACE_RE.sub("", text)
    hook_plain = SPACE_RE.sub("", hook_text)
    return CaptionFacts(
        text=text,
        first_line=first_line,
        hook=hook_text,
        hashtags=find_hashtags(text),
        mentions=find_mentions(text),
        links=find_links(text),
        lines=lines,
        chars=len(text),
        chars_nospace=len(plain),
        hook_chars=len(hook_text),
        hook_chars_nospace=len(hook_plain),
        emoji_count=emoji_count(text),
        language=detect_language(text),
    )


def split_sections(text: str) -> list[tuple[str, str]]:
    """`## 제목` 으로 나뉜 문서를 (제목, 본문) 목록으로."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return []
    out: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        out.append((match.group(1).strip(), text[match.end():end].strip()))
    return out


def extract_section(text: str, keyword: str = "auto") -> str:
    """캡션 파일에서 본문 구역만 꺼낸다.

    keyword 가 'auto' 면 '본문' 또는 '캡션'이 들어간 첫 제목을 쓰고, '해시태그' 구역이
    따로 있으면 뒤에 붙인다 — 실제로 붙여넣는 모양이 그렇다.
    해당 구역이 없으면 원문을 그대로 돌려준다 — 조용히 다른 글을 검사하지 않는다.
    """
    sections = split_sections(text)
    if not sections:
        return text
    if keyword.strip().lower() == "auto":
        body = None
        tags = None
        for heading, section_body in sections:
            if body is None and ("본문" in heading or "캡션" in heading):
                body = section_body
            elif tags is None and "해시태그" in heading:
                tags = section_body
        if body is None:
            return text
        return body + (("\n\n" + tags) if tags else "")
    needle = keyword.strip().lower()
    for heading, section_body in sections:
        if needle in heading.lower():
            return section_body
    return text


def golf_hashtags(tags: tuple[str, ...]) -> list[str]:
    return [tag for tag in tags if tag.lower() in VAGUE_HASHTAGS]


def keyword_position(text: str, keyword: str, window: int = 125) -> int:
    """키워드가 캡션 앞부분(기본 125자)에서 처음 나오는 위치. 없으면 -1."""
    if not keyword:
        return -1
    head = text[:window].lower()
    return head.find(keyword.strip().lower())


def display_width(text: str) -> int:
    """동아시아 넓은 글자는 2칸으로 세는 폭."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
