"""규칙 엔진 — 브라우저 없이 정적으로 판정할 수 있는 것만, WCAG 조항과 함께.

`a11y-debugging` 스킬(Chrome DevTools MCP)이 브라우저에서 확인하라고 하는 항목 중
**마크업만으로 판정 가능한 것**을 규칙으로 옮겼다:
제목 단계, 고아 입력(input↔label), 접근성 이름 없는 버튼·링크·이미지, 문서 언어,
`aria-hidden` 안의 포커스 요소, 표 머리글, 확대 금지 viewport.

판정 불가능한 것(색 대비·터치 타깃 크기·포커스 순서·키보드 함정)은 규칙으로 만들지 않았다.
계산한 척하는 규칙 하나가 없는 것보다 나쁘다 — `overview` 와 README 가 그 목록을 밝힌다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .accname import (
    KNOWN_ROLES,
    accessible_name,
    hidden_self_or_ancestor,
    is_focusable,
    is_hidden,
    label_text,
    name_source,
    selector_of,
    snippet,
    text_content,
)
from .htmltree import Document, Node, norm

__all__ = [
    "Rule",
    "Violation",
    "RULES",
    "IMPACT_ORDER",
    "IMPACT_WEIGHT",
    "audit_document",
    "rule_by_id",
    "fingerprint_of",
]

IMPACT_ORDER = {"critical": 0, "serious": 1, "moderate": 2}
IMPACT_WEIGHT = {"critical": 25, "serious": 12, "moderate": 4}
IMPACT_LABEL = {"critical": "치명", "serious": "심각", "moderate": "보통"}
IMPACT_KO = IMPACT_LABEL


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    wcag: str
    level: str
    impact: str
    why: str
    fix: str


@dataclass
class Violation:
    rule: Rule
    selector: str
    line: int
    snippet: str
    message: str
    fingerprint: str
    impact: str = ""
    file: str = ""

    @property
    def rank(self) -> int:
        return IMPACT_ORDER.get(self.impact or self.rule.impact, 9)


RULES: list[Rule] = [
    Rule(
        id="html-lang",
        title="문서 언어가 없습니다",
        wcag="3.1.1",
        level="A",
        impact="serious",
        why="화면 낭독기가 어떤 발음 규칙으로 읽을지 몰라, 한국어 문서를 영어 발음으로 읽는 일이 생깁니다.",
        fix='<html lang="ko">',
    ),
    Rule(
        id="document-title",
        title="페이지 제목이 없습니다",
        wcag="2.4.2",
        level="A",
        impact="serious",
        why="탭 목록과 화면 낭독기 첫 안내가 비어, 여러 탭 중 어디인지 알 수 없습니다.",
        fix="<head><title>로그인 – 사이트 이름</title></head>",
    ),
    Rule(
        id="image-alt",
        title="이미지에 대체텍스트가 없습니다",
        wcag="1.1.1",
        level="A",
        impact="critical",
        why="화면 낭독기는 파일 이름을 읽거나 아무것도 읽지 않습니다. 정보가 담긴 이미지면 내용이 통째로 사라집니다.",
        fix='<img src="logo.png" alt="회사 이름">   또는 장식이면  <img src="line.png" alt="">',
    ),
    Rule(
        id="button-name",
        title="버튼에 이름이 없습니다",
        wcag="4.1.2",
        level="A",
        impact="critical",
        why="아이콘만 있는 버튼은 '버튼'이라고만 읽혀 무엇을 하는 버튼인지 알 수 없습니다.",
        fix='<button type="button" aria-label="검색"><svg aria-hidden="true">…</svg></button>',
    ),
    Rule(
        id="link-name",
        title="링크에 이름이 없습니다",
        wcag="2.4.4",
        level="A",
        impact="critical",
        why="링크 목록만 훑는 사용자는 이름 없는 링크를 고를 수 없습니다.",
        fix='<a href="/notice">공지사항</a>   또는  <a href="/notice" aria-label="공지사항">…</a>',
    ),
    Rule(
        id="link-vague",
        title="링크 이름이 '여기'·'더 보기' 뿐입니다",
        wcag="2.4.4",
        level="A",
        impact="moderate",
        why="링크만 모아 읽으면 전부 같은 이름이라 목적지를 구분할 수 없습니다. 조항 위반 여부는 문맥에 따라 판단이 필요합니다.",
        fix='<a href="/notice">11월 공지사항 보기</a>',
    ),
    Rule(
        id="form-label",
        title="입력칸에 연결된 레이블이 없습니다",
        wcag="3.3.2",
        level="A",
        impact="critical",
        why="이름이 없으면 화면 낭독기는 '편집'·'콤보 상자'라고만 읽습니다. placeholder 는 입력을 시작하면 사라지므로 레이블이 아닙니다.",
        fix='<label for="email">이메일</label><input id="email" type="email" autocomplete="email">',
    ),
    Rule(
        id="label-orphan",
        title="label 의 for 가 가리키는 칸이 없습니다",
        wcag="1.3.1",
        level="A",
        impact="serious",
        why="오타이거나 id 가 지워진 상태입니다. 레이블과 입력칸이 화면 낭독기에서 따로 놉니다.",
        fix='<label for="email">이메일</label><input id="email" type="email">   ← 두 id/for 를 맞춘다',
    ),
    Rule(
        id="heading-skip",
        title="제목 단계를 건너뛰었습니다",
        wcag="1.3.1",
        level="A",
        impact="moderate",
        why="제목으로 문서 구조를 훑는 사용자는 h2 다음 h4 를 만나면 단계가 하나 사라진 것으로 읽습니다.",
        fix="<h2>다음은 <h3> — 숫자를 하나씩만 올린다 (모양은 CSS 로)",
    ),
    Rule(
        id="heading-empty",
        title="빈 제목이 있습니다",
        wcag="1.3.1",
        level="A",
        impact="moderate",
        why="제목 목록에 이름 없는 항목이 생겨 구조를 훑기 어려워집니다.",
        fix="<h2>실제 제목</h2>   또는 제목이 아니면 <div> 로 바꾼다",
    ),
    Rule(
        id="duplicate-id",
        title="id 가 중복됩니다",
        wcag="4.1.1",
        level="A",
        impact="serious",
        why="label for·aria-labelledby·앵커 이동이 첫 번째 요소만 가리켜, 두 번째 요소는 영영 이름을 못 받습니다.",
        fix='<input id="email"> … <input id="email-2">   ← id 는 문서에서 하나',
    ),
    Rule(
        id="aria-hidden-focus",
        title="aria-hidden 안에 포커스 가능한 요소가 있습니다",
        wcag="4.1.2",
        level="A",
        impact="serious",
        why="Tab 키로는 닿는데 화면 낭독기는 읽지 않는 '보이지 않는 함정'이 됩니다.",
        fix='aria-hidden="true" 를 지우거나, 안쪽 요소에 tabindex="-1" 을 준다',
    ),
    Rule(
        id="tabindex-positive",
        title="tabindex 가 0 보다 큽니다",
        wcag="2.4.3",
        level="A",
        impact="moderate",
        why="Tab 순서가 DOM 순서와 어긋나, 화면에 보이는 순서와 키보드 이동 순서가 달라집니다.",
        fix='tabindex="0" (또는 속성 제거) — 순서는 DOM 으로 만든다',
    ),
    Rule(
        id="iframe-title",
        title="iframe 에 title 이 없습니다",
        wcag="4.1.2",
        level="A",
        impact="serious",
        why="화면 낭독기는 '프레임'이라고만 알려 줍니다. 무엇이 들어 있는지 알 수 없습니다.",
        fix='<iframe src="…" title="지도: 서울시청">',
    ),
    Rule(
        id="table-headers",
        title="표에 머리글 칸(th)이 없습니다",
        wcag="1.3.1",
        level="A",
        impact="serious",
        why="화면 낭독기는 셀을 읽을 때 머리글을 함께 읽어 주는데, 머리글이 없으면 '셀, 셀'만 들립니다.",
        fix='<tr><th scope="col">이름</th><th scope="col">금액</th></tr>',
    ),
    Rule(
        id="viewport-zoom",
        title="확대를 막고 있습니다",
        wcag="1.4.4",
        level="AA",
        impact="serious",
        why="저시력 사용자가 손가락으로 확대하지 못합니다. iOS 는 maximum-scale 도 무시하지만 안드로이드는 막힙니다.",
        fix='<meta name="viewport" content="width=device-width, initial-scale=1">',
    ),
    Rule(
        id="main-landmark",
        title="본문 영역(main)이 없습니다",
        wcag="1.3.1",
        level="A",
        impact="moderate",
        why="화면 낭독기의 '본문으로 건너뛰기'가 없어, 페이지마다 머리글·메뉴를 다시 지나가야 합니다.",
        fix="<main>본문</main>   또는  <div role=\"main\">",
    ),
    Rule(
        id="bad-aria-ref",
        title="aria-labelledby 가 없는 id 를 가리킵니다",
        wcag="4.1.2",
        level="A",
        impact="serious",
        why="이름이 비어 버튼이 '버튼', 입력칸이 '편집'으로만 읽힙니다.",
        fix='<span id="hint">비밀번호는 8자 이상</span> … aria-labelledby="hint"',
    ),
    Rule(
        id="bad-aria-controls",
        title="aria-controls 가 없는 id 를 가리킵니다",
        wcag="4.1.2",
        level="A",
        impact="moderate",
        why="관계가 끊겨 있습니다. 다만 aria-controls 대상은 스크립트가 나중에 만드는 경우가 흔해, 렌더링된 화면에서 한 번 더 확인해야 합니다.",
        fix='<div id="panel">…</div> … aria-controls="panel"   ← 실제로 존재하는 id',
    ),
    Rule(
        id="invalid-role",
        title="role 값이 표준이 아닙니다",
        wcag="4.1.2",
        level="A",
        impact="moderate",
        why="브라우저가 무시하고 태그 기본 역할로 돌아가, 의도한 역할이 사라집니다.",
        fix='role="navigation" 처럼 ARIA 표준 값만 쓴다',
    ),
]

_RULE_BY_ID = {rule.id: rule for rule in RULES}
_EMAILISH = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_VAGUE = {
    "여기", "여기를 클릭", "여기 클릭", "클릭", "더 보기", "더보기", "자세히", "자세히 보기",
    "more", "read more", "click here", "here", "link", "this", "보기", "이동",
}
_ZOOM_BAD = re.compile(r"(user-scalable\s*=\s*(no|0))|(maximum-scale\s*=\s*(1(\.0+)?|0?\.\d+))", re.I)


def rule_by_id(rule_id: str) -> Rule | None:
    return _RULE_BY_ID.get(rule_id)


def _normalize_attrs_for_fingerprint(node: Node) -> str:
    keys = sorted(
        k for k in node.attrs if k not in {"style", "class", "href", "src", "for", "id", "width", "height"}
    )
    values = " ".join(
        f"{k}={norm(node.attrs[k])}" for k in keys if k in {"role", "type", "scope", "aria-hidden", "alt"}
    )
    text = norm(text_content(node))[:60]
    return f"{node.tag}|{values}|{text}"


def fingerprint_of(rule_id: str, node: Node | None) -> str:
    """같은 템플릿에서 반복되는 위반을 하나로 묶기 위한 지문.

    값이 아니라 **속성 이름과 의미 있는 값(role·type·scope·alt)** 만 본다.
    그래야 페이지마다 다른 링크 주소·id 가 지문을 갈라놓지 않는다.
    """
    signature = rule_id + "|" + (_normalize_attrs_for_fingerprint(node) if node is not None else "-")
    return "fp_" + hashlib.blake2b(signature.encode("utf-8"), digest_size=5).hexdigest()


@dataclass
class _Ctx:
    doc: Document
    ids: dict[str, Node] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ids:
            self.ids = self.doc.id_index()

    def visible(self) -> list[Node]:
        return [n for n in self.doc.elements() if not hidden_self_or_ancestor(n)]


def _make(rule: Rule | str, node: Node | None, message: str, impact: str = "") -> Violation:
    rule_obj = rule if isinstance(rule, Rule) else _RULE_BY_ID[rule]
    return Violation(
        rule=rule_obj,
        selector=selector_of(node) if node is not None else "(문서)",
        line=node.line if node is not None else 0,
        snippet=snippet(node) if node is not None else "",
        message=message,
        fingerprint=fingerprint_of(rule_obj.id, node),
        impact=impact or rule_obj.impact,
    )


# --------------------------------------------------------------------- 규칙들
def _html_lang(ctx: _Ctx) -> list[Violation]:
    html = ctx.doc.first("html")
    if html is None:
        return [_make("html-lang", None, "<html> 요소가 없어 문서 언어를 알 수 없습니다.")]
    lang = norm(html.get("lang"))
    if not lang:
        return [_make("html-lang", html, "lang 속성이 비어 있습니다.")]
    if not _EMAILISH.match(lang):
        return [_make("html-lang", html, f'lang="{lang}" 형식이 BCP 47 과 다릅니다 (예: ko, en-US).')]
    return []


def _document_title(ctx: _Ctx) -> list[Violation]:
    title = ctx.doc.first("title")
    if title is None:
        return [_make("document-title", None, "<title> 이 없습니다.")]
    if not text_content(title, skip_hidden=False):
        return [_make("document-title", title, "<title> 이 비어 있습니다.")]
    return []


def _image_alt(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if node.tag == "img":
            if not node.has("alt"):
                role = norm(node.get("role")).lower()
                if role in {"presentation", "none"}:
                    continue
                found.append(_make("image-alt", node, "alt 속성이 아예 없습니다."))
            elif norm(node.get("alt")) == "" and norm(node.get("role")).lower() not in {"presentation", "none"}:
                continue  # alt="" 는 장식 이미지로 본다 (의도적 선택)
        elif node.tag == "input" and norm(node.get("type")).lower() == "image":
            if not norm(node.get("alt")):
                found.append(_make("image-alt", node, "input type=image 에 alt 가 없습니다."))
        elif node.tag == "svg":
            role = norm(node.get("role")).lower()
            if role == "img" and not accessible_name(node, ctx.doc, ctx.ids):
                found.append(_make("image-alt", node, 'role="img" 인 svg 에 이름(aria-label 또는 <title>)이 없습니다.'))
    return found


def _button_name(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        kind = norm(node.get("type")).lower()
        is_button = (
            node.tag == "button"
            or (node.tag == "input" and kind in {"submit", "button", "reset"})
            or norm(node.get("role")).lower() == "button"
        )
        if not is_button:
            continue
        if node.tag == "input":
            name = norm(node.get("value")) or ("" if kind == "button" else {"submit": "Submit", "reset": "Reset"}.get(kind, ""))
        else:
            name = accessible_name(node, ctx.doc, ctx.ids)
        if name:
            if name_source(node, ctx.doc, ctx.ids) == "title":
                found.append(
                    _make("button-name", node, f"이름이 title 속성(\"{name}\") 뿐입니다 — 마우스 사용자에게만 보입니다.", impact="moderate")
                )
            continue
        found.append(_make("button-name", node, "접근성 이름이 없습니다 (아이콘만 있거나 빈 버튼)."))
    return found


def _link_name(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if node.tag != "a" or not node.has("href"):
            continue
        if norm(node.get("role")).lower() in {"presentation", "none"}:
            continue
        name = accessible_name(node, ctx.doc, ctx.ids)
        if not name:
            found.append(_make("link-name", node, "접근성 이름이 없습니다 (아이콘만 있거나 빈 링크)."))
        elif name_source(node, ctx.doc, ctx.ids) == "title":
            found.append(_make("link-name", node, f"이름이 title 속성(\"{name}\") 뿐입니다.", impact="moderate"))
    return found


def _link_vague(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if node.tag != "a" or not node.has("href"):
            continue
        name = accessible_name(node, ctx.doc, ctx.ids).strip(" .…>→")
        if name and name.lower() in _VAGUE:
            found.append(_make("link-vague", node, f'링크 이름이 "{name}" 뿐입니다.'))
    return found


def _form_label(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if node.tag not in {"input", "select", "textarea"}:
            continue
        kind = norm(node.get("type")).lower() if node.tag == "input" else ""
        if kind in {"hidden", "submit", "button", "reset", "image"}:
            continue
        if node.has("aria-hidden") and norm(node.get("aria-hidden")).lower() == "true":
            continue
        name = accessible_name(node, ctx.doc, ctx.ids)
        if name:
            continue
        placeholder = norm(node.get("placeholder"))
        message = "레이블·aria-label·aria-labelledby 가 모두 없습니다."
        if placeholder:
            message += f' placeholder("{placeholder}")만 있습니다 — placeholder 는 레이블이 아닙니다.'
        found.append(_make("form-label", node, message))
    return found


def _label_orphan(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if node.tag != "label":
            continue
        target = norm(node.get("for"))
        if not target:
            continue
        if target not in ctx.ids:
            found.append(_make("label-orphan", node, f'for="{target}" 에 해당하는 id 가 없습니다.'))
    return found


def _headings(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    previous = 0
    seen_h1 = 0
    for node in ctx.visible():
        if node.tag not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            continue
        level = int(node.tag[1])
        text = text_content(node)
        if not text:
            found.append(_make("heading-empty", node, f"h{level} 이 비어 있습니다."))
        if level == 1:
            seen_h1 += 1
        if previous and level > previous + 1:
            missing = ", ".join(f"h{n}" for n in range(previous + 1, level))
            found.append(_make("heading-skip", node, f"h{previous} 다음에 h{level} — {missing} 이(가) 빠졌습니다."))
        previous = level
    return found


def _duplicate_id(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for ident, count in ctx.doc.duplicates.items():
        if count < 2:
            continue
        occurrences = [n for n in ctx.doc.elements() if norm(n.get("id")) == ident]
        for node in occurrences[1:]:
            found.append(_make("duplicate-id", node, f'id="{ident}" 이 문서에 {count}번 있습니다.'))
    return found


def _aria_hidden_focus(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    focusables = [n for n in ctx.doc.elements() if is_focusable(n)]
    for node in ctx.doc.elements():
        if norm(node.get("aria-hidden")).lower() != "true":
            continue
        hidden_refs = {id(n) for n in [node, *node.walk()] if not n.is_text}
        inside = [f for f in focusables if id(f) in hidden_refs]
        if inside:
            found.append(
                _make(
                    "aria-hidden-focus",
                    node,
                    f"aria-hidden 안에 포커스 가능한 요소 {len(inside)}개 ({snippet(inside[0], 40)}).",
                )
            )
    return found


def _tabindex_positive(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        if not node.has("tabindex"):
            continue
        try:
            value = int(norm(node.get("tabindex")))
        except ValueError:
            continue
        if value > 0:
            found.append(_make("tabindex-positive", node, f"tabindex={value}"))
    return found


def _iframe_title(ctx: _Ctx) -> list[Violation]:
    return [
        _make("iframe-title", node, "title 속성이 없습니다.")
        for node in ctx.visible()
        if node.tag == "iframe" and not norm(node.get("title"))
    ]


def _table_headers(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for table in ctx.visible():
        if table.tag != "table":
            continue
        if norm(table.get("role")).lower() in {"presentation", "none"}:
            continue
        cells = [n for n in table.walk() if n.tag == "td"]
        headers = [n for n in table.walk() if n.tag == "th"]
        if len(cells) < 2 or headers:
            continue
        nested = any(n.tag == "table" for n in table.walk())
        has_caption = any(child.tag == "caption" for child in table.children if not child.is_text)
        message = f"td {len(cells)}개, th 0개."
        if nested or (not has_caption and len(cells) >= 12):
            message += ' 레이아웃용 표로 보입니다 — 데이터 표가 아니라면 role="presentation" 이 맞습니다.'
        found.append(_make("table-headers", table, message))
    return found


def _viewport_zoom(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.doc.by_tag("meta"):
        if norm(node.get("name")).lower() != "viewport":
            continue
        content = norm(node.get("content"))
        match = _ZOOM_BAD.search(content)
        if match:
            found.append(_make("viewport-zoom", node, f'content="{content}"'))
    return found


def _main_landmark(ctx: _Ctx) -> list[Violation]:
    for node in ctx.visible():
        if node.tag == "main" or norm(node.get("role")).lower() == "main":
            return []
    body = ctx.doc.first("body")
    return [
        _make(
            "main-landmark",
            body,
            "main 요소도 role=\"main\" 도 없습니다." if body is not None else "main 요소가 없습니다.",
        )
    ]


def _bad_aria_ref(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        for attr in ("aria-labelledby", "aria-describedby"):
            refs = norm(node.get(attr))
            if not refs:
                continue
            missing = [r for r in refs.split() if r not in ctx.ids]
            if missing:
                found.append(_make("bad-aria-ref", node, f'{attr}="{refs}" 중 없는 id: {", ".join(missing)}'))
    return found


def _bad_aria_controls(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        refs = norm(node.get("aria-controls"))
        if not refs:
            continue
        missing = [r for r in refs.split() if r not in ctx.ids]
        if missing:
            found.append(_make("bad-aria-controls", node, f'aria-controls="{refs}" 중 없는 id: {", ".join(missing)}'))
    return found


def _invalid_role(ctx: _Ctx) -> list[Violation]:
    found: list[Violation] = []
    for node in ctx.visible():
        raw = norm(node.get("role"))
        if not raw:
            continue
        for token in raw.split():
            if token.lower() not in KNOWN_ROLES:
                found.append(_make("invalid-role", node, f'role="{token}" 은 ARIA 표준 역할이 아닙니다.'))
                break
    return found


_CHECKS = (
    _html_lang,
    _document_title,
    _image_alt,
    _button_name,
    _link_name,
    _link_vague,
    _form_label,
    _label_orphan,
    _headings,
    _duplicate_id,
    _aria_hidden_focus,
    _tabindex_positive,
    _iframe_title,
    _table_headers,
    _viewport_zoom,
    _main_landmark,
    _bad_aria_ref,
    _bad_aria_controls,
    _invalid_role,
)


def audit_document(
    doc: Document,
    rules: set[str] | None = None,
    max_per_rule: int = 0,
    file: str = "",
) -> tuple[list[Violation], dict[str, int]]:
    """문서 하나를 규칙 전체로 검사한다. (위반 목록, 규칙별 잘라낸 개수)"""
    ctx = _Ctx(doc)
    selected = rules or set()
    found: list[Violation] = []
    for check in _CHECKS:
        for violation in check(ctx):
            if selected and violation.rule.id not in selected:
                continue
            violation.file = file or doc.path
            found.append(violation)
    found.sort(key=lambda v: (v.rank, v.rule.id, v.line))
    if max_per_rule and max_per_rule > 0:
        trimmed: list[Violation] = []
        counts: dict[str, int] = {}
        for violation in found:
            counts[violation.rule.id] = counts.get(violation.rule.id, 0) + 1
            if counts[violation.rule.id] <= max_per_rule:
                trimmed.append(violation)
        hidden = {rule: count - max_per_rule for rule, count in counts.items() if count > max_per_rule}
        return trimmed, hidden
    return found, {}
