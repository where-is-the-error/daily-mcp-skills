"""접근성 이름(accessible name) 과 역할(role) 계산 — 축약형.

W3C accname 1.1 의 앞부분만 구현한다 (aria-labelledby → aria-label → 네이티브 → title).
계산하지 못하는 것은 계산한 척하지 않는다:

  - CSS 로 만든 이름(::before content, background-image 대체텍스트)은 보지 않는다
  - `display:none` 은 인라인 style·hidden 속성만 알아본다 (외부 CSS 는 읽지 않는다)
  - shadow DOM·iframe 내부 문서는 열지 않는다

이 셋은 README "한계"에 그대로 적혀 있고, `overview` 툴도 같은 말을 한다.
"""

from __future__ import annotations

from .htmltree import HEAD_ONLY, RAW_TEXT, Document, Node, norm

__all__ = [
    "role_of",
    "accessible_name",
    "name_source",
    "text_content",
    "is_hidden",
    "is_focusable",
    "label_text",
    "selector_of",
    "snippet",
    "LANDMARK_ONLY",
]

# 이름을 만들 때 글자로 세지 않는 자손
_SKIP_TEXT = frozenset({"script", "style", "template", "noscript"})

_BUTTON_INPUT = frozenset({"submit", "reset", "button"})
_TEXT_INPUT = frozenset(
    {"text", "email", "password", "search", "tel", "url", "number", "date", "datetime-local",
     "month", "week", "time", "color", "file"}
)
_SUBMITISH = _BUTTON_INPUT

ROLES = {
    "a": "link",
    "abbr": None,
    "address": None,
    "area": "link",
    "article": "article",
    "aside": "complementary",
    "b": None,
    "blockquote": "blockquote",
    "body": None,
    "br": None,
    "button": "button",
    "caption": "caption",
    "code": "code",
    "dd": "definition",
    "del": "deletion",
    "details": "group",
    "dfn": "term",
    "dialog": "dialog",
    "div": None,
    "dl": "list",
    "dt": "term",
    "em": "emphasis",
    "fieldset": "group",
    "figcaption": "caption",
    "figure": "figure",
    "footer": "contentinfo",
    "form": None,
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "header": "banner",
    "hr": "separator",
    "i": None,
    "iframe": "iframe",
    "img": "image",
    "input": None,
    "ins": "insertion",
    "label": None,
    "legend": None,
    "li": "listitem",
    "main": "main",
    "mark": "mark",
    "nav": "navigation",
    "ol": "list",
    "optgroup": "group",
    "option": "option",
    "output": "status",
    "p": "paragraph",
    "picture": None,
    "pre": "code",
    "progress": "progressbar",
    "q": "blockquote",
    "s": None,
    "section": "region",
    "select": "combobox",
    "small": None,
    "span": None,
    "strong": "strong",
    "summary": "button",
    "table": "table",
    "tbody": "rowgroup",
    "td": "cell",
    "textarea": "textbox",
    "tfoot": "rowgroup",
    "th": "columnheader",
    "thead": "rowgroup",
    "time": "time",
    "title": None,
    "tr": "row",
    "u": None,
    "ul": "list",
    "video": "video",
    "audio": "audio",
}

# role 속성으로 지정할 수 있는 값 (일부만 — 모르는 값은 invalid-role 로 잡는다)
KNOWN_ROLES = frozenset(
    """
    alert alertdialog application article banner blockquote button caption cell checkbox code
    columnheader combobox complementary contentinfo definition deletion dialog directory
    document emphasis feed figure form generic grid gridcell group heading img insertion link
    list listbox listitem log main mark marquee math menu menubar menuitem menuitemcheckbox
    menuitemradio meter navigation none note option paragraph presentation progressbar radio
    radiogroup region row rowgroup rowheader scrollbar search searchbox separator slider
    spinbutton status strong subscript suggestion superscript switch tab table tablist
    tabpanel term textbox time timer toolbar tooltip tree treegrid treeitem
    """.split()
)

LANDMARK_ONLY = frozenset({"banner", "navigation", "main", "complementary", "contentinfo", "region", "search"})

# 글자 자체가 이름이 되는 요소 (ARIA "name from content"). div·span·section·form 은 여기 없다.
NAME_FROM_CONTENT = frozenset(
    {
        "p", "li", "dt", "dd", "td", "th", "caption", "figcaption", "label", "legend", "summary",
        "blockquote", "code", "em", "strong", "mark", "time", "h1", "h2", "h3", "h4", "h5", "h6",
        "button", "a", "option", "output", "q", "ins", "del",
    }
)


def is_hidden(node: Node) -> bool:
    """숨김으로 볼 수 있는 것만 숨김으로 본다 (보수적으로)."""
    if node.is_text:
        return False
    if node.has("hidden"):
        return True
    if norm(node.get("aria-hidden")).lower() == "true":
        return True
    style = norm(node.get("style")).lower().replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if node.tag == "input" and norm(node.get("type")).lower() == "hidden":
        return True
    return False


def hidden_self_or_ancestor(node: Node) -> bool:
    current: Node | None = node
    while current is not None and current.tag not in {"#document", ""}:
        if is_hidden(current):
            return True
        current = current.parent
    return False


def aria_hidden_ancestor(node: Node) -> Node | None:
    current: Node | None = node.parent
    while current is not None and current.tag not in {"#document", ""}:
        if norm(current.get("aria-hidden")).lower() == "true":
            return current
        current = current.parent
    return None


def text_content(node: Node, skip_hidden: bool = True) -> str:
    parts: list[str] = []
    for child in node.children:
        if child.is_text:
            parts.append(child.text)
            continue
        if child.tag in _SKIP_TEXT:
            continue
        if skip_hidden and is_hidden(child):
            continue
        if child.tag == "img":
            alt = norm(child.get("alt"))
            if alt:
                parts.append(alt)
            continue
        if child.tag == "br":
            parts.append(" ")
            continue
        parts.append(text_content(child, skip_hidden=skip_hidden))
    return norm(" ".join(p for p in parts if p))


def _labelledby_text(node: Node, doc: Document, ids: dict[str, Node]) -> str:
    refs = norm(node.get("aria-labelledby"))
    if not refs:
        return ""
    parts = []
    for ref in refs.split():
        target = ids.get(ref)
        if target is None:
            continue
        parts.append(accessible_name(target, doc, ids=ids) or text_content(target))
    return norm(" ".join(p for p in parts if p))


def label_text(node: Node, doc: Document) -> tuple[str, str]:
    """폼 요소의 <label> — (텍스트, 방법). 방법은 for / wrap / none."""
    ident = norm(node.get("id"))
    if ident:
        for label in doc.by_tag("label"):
            if norm(label.get("for")) == ident:
                return text_content(label), "for"
    ancestor = node.parent
    while ancestor is not None and ancestor.tag not in {"#document", ""}:
        if ancestor.tag == "label":
            return text_content(ancestor), "wrap"
        ancestor = ancestor.parent
    return "", "none"


def _native_name(node: Node, doc: Document, ids: dict[str, Node]) -> tuple[str, str]:
    tag = node.tag
    if tag == "img":
        return norm(node.get("alt")), "alt" if node.has("alt") else "none"
    if tag == "area":
        return norm(node.get("alt")), "alt" if node.has("alt") else "none"
    if tag == "input":
        kind = norm(node.get("type")).lower() or "text"
        if kind == "hidden":
            return "", "none"
        if kind in _SUBMITISH:
            value = norm(node.get("value"))
            if value:
                return value, "value"
            return {"submit": "Submit", "reset": "Reset", "button": ""}.get(kind, ""), "default"
        if kind == "image":
            return norm(node.get("alt")), "alt" if node.has("alt") else "none"
        text, how = label_text(node, doc)
        return text, f"label:{how}" if text else "none"
    if tag in {"select", "textarea", "meter", "progress", "output"}:
        text, how = label_text(node, doc)
        return text, f"label:{how}" if text else "none"
    if tag == "button":
        return text_content(node), "text"
    if tag == "a":
        return text_content(node), "text"
    if tag == "summary":
        return text_content(node), "text"
    if tag == "iframe":
        return norm(node.get("title")), "title" if node.has("title") else "none"
    if tag == "table":
        caption = None
        for child in node.children:
            if not child.is_text and child.tag == "caption":
                caption = child
                break
        if caption is not None:
            return text_content(caption), "caption"
        return "", "none"
    if tag == "fieldset":
        for child in node.children:
            if not child.is_text and child.tag == "legend":
                return text_content(child), "legend"
        return "", "none"
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return text_content(node), "text"
    if tag in {"svg"}:
        return norm(node.get("aria-label")), "aria-label"
    return "", "none"


def accessible_name(node: Node, doc: Document, ids: dict[str, Node] | None = None) -> str:
    """축약 accname: labelledby → label → 네이티브 → title."""
    if node.is_text:
        return norm(node.text)
    ids = ids if ids is not None else doc.id_index()
    from_labelledby = _labelledby_text(node, doc, ids)
    if from_labelledby:
        return from_labelledby
    explicit = norm(node.get("aria-label"))
    if explicit:
        return explicit
    native, _how = _native_name(node, doc, ids)
    if native:
        return native
    title = norm(node.get("title"))
    if title:
        return title
    if node.tag in NAME_FROM_CONTENT:
        return text_content(node)
    return ""


def name_source(node: Node, doc: Document, ids: dict[str, Node] | None = None) -> str:
    """이름이 어디서 왔는지 — none / aria-labelledby / aria-label / label:for / alt / text / title …"""
    ids = ids if ids is not None else doc.id_index()
    if _labelledby_text(node, doc, ids):
        return "aria-labelledby"
    if norm(node.get("aria-label")):
        return "aria-label"
    native, how = _native_name(node, doc, ids)
    if native:
        return how if how.startswith("label:") else how
    if norm(node.get("title")):
        return "title"
    return "none"


def role_of(node: Node, doc: Document | None = None, ids: dict[str, Node] | None = None) -> str | None:
    """역할 — role 속성이 있으면 그것, 없으면 태그 기본값. None 이면 접근성 트리에 안 나온다."""
    explicit = norm(node.get("role")).lower().split(" ")[0] if node.get("role") else ""
    if explicit in KNOWN_ROLES:
        return explicit
    tag = node.tag
    if tag == "":
        return None
    if tag == "html":
        return "document"
    if tag in RAW_TEXT or tag in {"head", "meta", "link", "base", "param", "source", "track", "body", "title"}:
        return None
    if tag == "img":
        if node.has("alt") and norm(node.get("alt")) == "":
            return "presentation"
        return "image"
    if tag == "input":
        kind = norm(node.get("type")).lower() or "text"
        if kind == "hidden":
            return None
        return {
            "checkbox": "checkbox",
            "radio": "radio",
            "range": "slider",
            "number": "spinbutton",
            "search": "searchbox",
            "submit": "button",
            "reset": "button",
            "button": "button",
            "image": "button",
            "file": "button",
        }.get(kind, "textbox")
    if tag == "a":
        return "link" if node.has("href") else None
    if tag == "footer":
        # 기사/섹션 안의 footer 는 contentinfo 가 아니다
        for ancestor in node.ancestors():
            if ancestor.tag in {"article", "aside", "section", "nav"}:
                return None
        return "contentinfo"
    if tag == "header":
        for ancestor in node.ancestors():
            if ancestor.tag in {"article", "aside", "main", "nav", "section"}:
                return None
        return "banner"
    if tag == "th":
        return "rowheader" if norm(node.get("scope")).lower() == "row" else "columnheader"
    if tag == "section":
        name = accessible_name(node, doc, ids) if doc is not None else norm(node.get("aria-label"))
        return "region" if name else None
    if tag == "form":
        name = accessible_name(node, doc, ids) if doc is not None else norm(node.get("aria-label"))
        return "form" if name else None
    return ROLES.get(tag)


_FOCUSABLE_TAGS = frozenset({"a", "button", "input", "select", "textarea", "summary", "audio", "video", "details"})


def _hidden_from_focus(node: Node) -> bool:
    """렌더링에서 사라진 것만 포커스 불가로 본다. aria-hidden 은 Tab 순서를 막지 않는다."""
    current: Node | None = node
    while current is not None and current.tag not in {"#document", ""}:
        if current.has("hidden"):
            return True
        style = norm(current.get("style")).lower().replace(" ", "")
        if "display:none" in style or "visibility:hidden" in style:
            return True
        current = current.parent
    return False


def is_focusable(node: Node) -> bool:
    if node.is_text or _hidden_from_focus(node):
        return False
    if node.has("tabindex"):
        try:
            return int(norm(node.get("tabindex"))) >= 0
        except ValueError:
            return True
    if node.tag == "a":
        return node.has("href")
    if node.tag == "input":
        return norm(node.get("type")).lower() != "hidden" and not node.has("disabled")
    if node.tag in _FOCUSABLE_TAGS:
        return not node.has("disabled")
    if node.has("contenteditable") and norm(node.get("contenteditable")).lower() != "false":
        return True
    return False


def _nth_of_type(node: Node) -> int:
    if node.parent is None:
        return 1
    count = 0
    for sibling in node.parent.children:
        if sibling.is_text or sibling.tag != node.tag:
            continue
        count += 1
        if sibling is node:
            return count
    return 1


def selector_of(node: Node, max_depth: int = 6) -> str:
    """브라우저에서 그대로 쓸 수 있는 CSS 선택자 (id 가 있으면 거기서 끊는다)."""
    parts: list[str] = []
    current: Node | None = node
    while current is not None and current.tag not in {"#document", ""} and len(parts) < max_depth:
        ident = norm(current.get("id"))
        if ident and " " not in ident:
            parts.append(f"#{ident}")
            break
        piece = current.tag
        if current.tag in {"li", "tr", "td", "th", "option", "p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            piece += f":nth-of-type({_nth_of_type(current)})"
        parts.append(piece)
        current = current.parent
    return " > ".join(reversed(parts)) or node.tag


BOOLEAN_ATTRS = frozenset(
    "allowfullscreen async autofocus autoplay checked controls default defer disabled formnovalidate "
    "hidden inert ismap itemscope loop multiple muted nomodule novalidate open playsinline readonly "
    "required reversed selected".split()
)


def snippet(node: Node, limit: int = 120) -> str:
    """원본 마크업 한 줄 — 여는 태그만. 값이 빈 불리언 속성만 이름만 쓴다 (alt="" 는 그대로)."""
    if node.is_text:
        return norm(node.text)[:limit]
    attrs = "".join(
        f" {name}"
        if value == "" and name in BOOLEAN_ATTRS
        else f' {name}="{value}"'
        for name, value in sorted(node.attrs.items())
    )
    text = f"<{node.tag}{attrs}>"
    return text[:limit] + ("…" if len(text) > limit else "")


def visible_text(node: Node) -> str:  # pragma: no cover - 편의
    return text_content(node)


# HEAD_ONLY 는 다른 모듈에서 참조할 수 있도록 남겨 둔다
_ = HEAD_ONLY
