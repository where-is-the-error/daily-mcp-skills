"""접근성 트리 → 텍스트 스냅샷 (ref 붙은 형태).

Playwright MCP 의 스냅샷 규칙에서 가져온 것:
  - 화면(픽셀)이 아니라 **접근성 트리**를 글자로 보여 준다
  - 모든 노드에 `ref=e12` 를 달아, 뒤이어 오는 지시(고치기·다시 보기)가 같은 노드를 가리키게 한다
  - `depth` 로 깊이를 자르고, 자른 곳은 잘랐다고 말한다 (조용히 사라지지 않는다)

정적 파서라서 하나 더 얹은 것: `L18` — 원본 HTML 의 줄 번호. 브라우저 기반 도구는
줄 번호를 주지 못하고, 이 줄 번호가 "어느 파일 어느 줄을 고쳐야 하는가"를 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .accname import accessible_name, hidden_self_or_ancestor, is_hidden, role_of, text_content
from .htmltree import Document, Node, norm

__all__ = ["Entry", "Snapshot", "build", "canonical", "ref_target"]

_STATE_ATTRS = (
    "aria-expanded",
    "aria-checked",
    "aria-selected",
    "aria-pressed",
    "aria-current",
    "aria-disabled",
    "aria-required",
    "aria-invalid",
    "aria-haspopup",
    "aria-modal",
    "aria-live",
)
_FLAG_ATTRS = ("required", "disabled", "readonly", "multiple", "checked")
_SKIP_TAGS = frozenset({"script", "style", "template", "noscript", "head", "meta", "link", "base"})
# 자식 요소가 없으면 이름이 곧 글자이므로 텍스트 줄을 따로 찍지 않는다
_TEXTUAL = frozenset(
    {"heading", "link", "button", "paragraph", "caption", "cell", "listitem", "option", "term", "definition"}
)
_MAX_NAME = 90


@dataclass
class Entry:
    role: str
    name: str = ""
    ref: str = ""
    line: int = 0
    depth: int = 0
    extra: str = ""
    node: Node | None = None
    path: tuple[str, ...] = ()

    def label(self) -> str:
        head = f'{self.role} "{self.name}"' if self.name else self.role
        return f"{head} {self.extra}".strip()


@dataclass
class Snapshot:
    entries: list[Entry] = field(default_factory=list)
    refs: dict[str, Node] = field(default_factory=dict)
    title: str = ""
    lang: str = ""
    truncated: bool = False
    source: str = ""
    notes: list[str] = field(default_factory=list)

    def render(self, show_source: bool = True) -> str:
        lines: list[str] = []
        head = f'document "{self.title}"' if self.title else "document"
        if self.lang:
            head += f" lang={self.lang}"
        lines.append(head)
        for entry in self.entries:
            indent = "  " * (entry.depth + 1)
            tail = []
            if entry.ref:
                tail.append(f"ref={entry.ref}")
            if show_source and entry.line:
                tail.append(f"L{entry.line}")
            suffix = (" · " + " · ".join(tail)) if tail else ""
            lines.append(f"{indent}{entry.label()}{suffix}")
        for note in self.notes:
            lines.append(f"# {note}")
        return "\n".join(lines)

    def find(self, ref: str) -> Entry | None:
        for entry in self.entries:
            if entry.ref == ref:
                return entry
        return None


def _short(text: str, limit: int = _MAX_NAME) -> str:
    text = norm(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _extras(node: Node) -> str:
    bits: list[str] = []
    if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        bits.append(f"level={node.tag[1]}")
    if node.tag == "input":
        kind = norm(node.get("type")).lower() or "text"
        bits.append(f"type={kind}")
    if node.tag == "a" and norm(node.get("href")):
        bits.append(f'href="{norm(node.get("href"))[:40]}"')
    if node.tag == "th" and norm(node.get("scope")):
        bits.append(f"scope={norm(node.get('scope'))}")
    for attr in _STATE_ATTRS:
        if node.has(attr):
            bits.append(f'{attr}="{norm(node.get(attr))}"')
    for flag in _FLAG_ATTRS:
        if node.has(flag):
            bits.append(flag)
    return " ".join(bits)


def _title_of(doc: Document) -> str:
    for node in doc.elements():
        if node.tag == "title":
            return _short(text_content(node, skip_hidden=False), 70)
    return ""


def canonical(doc: Document, include_hidden: bool = False) -> list[tuple[Node, str]]:
    """문서 순서대로 (요소, 역할) — ref 번호의 기준.

    옵션(depth·max_nodes·root_ref)과 무관하게 같은 파일이면 같은 번호가 나온다.
    그래야 `ref=e12` 가 "아까 그 노드"로 계속 통한다 (Playwright uid 와 같은 약속).
    """
    found: list[tuple[Node, str]] = []

    def walk(node: Node) -> None:
        if node.is_text or node.tag in _SKIP_TAGS:
            return
        if node.tag == "html":
            for child in node.children:
                walk(child)
            return
        if not include_hidden and is_hidden(node):
            return
        role = role_of(node, doc)
        if role and role not in {"presentation", "none"}:
            found.append((node, role))
        for child in node.children:
            walk(child)

    for child in doc.root.children:
        walk(child)
    return found


def ref_target(doc: Document, ref: str, include_hidden: bool = False) -> Node | None:
    """`ref=e12` → 그 요소."""
    text = ref.strip()
    if text.startswith("ref="):
        text = text[4:]
    if not text.startswith("e") or not text[1:].isdigit():
        return None
    index = int(text[1:])
    items = canonical(doc, include_hidden=include_hidden)
    if 1 <= index <= len(items):
        return items[index - 1][0]
    return None


def build(
    doc: Document,
    depth: int = 0,
    max_nodes: int = 200,
    root_ref: str = "",
    include_hidden: bool = False,
) -> Snapshot:
    """문서 전체 또는 root_ref 하위의 접근성 스냅샷.

    depth=0 은 무제한, depth=n 은 n단계까지만 (자른 곳은 notes 에 적는다).
    """
    title = _title_of(doc)
    html = doc.first("html")
    lang = norm(html.get("lang")) if html is not None else ""
    snapshot = Snapshot(title=title, lang=lang, source=doc.path)

    out: list[Entry] = []
    state = {"truncated": False}
    refs = {id(node): f"e{index}" for index, (node, _role) in enumerate(canonical(doc, include_hidden), start=1)}

    def visit(node: Node, level: int, path: tuple[str, ...]) -> None:
        if node.is_text or node.tag in _SKIP_TAGS:
            return
        if node.tag == "html":
            # <html> 은 문서 머리줄이 이미 말한다 — 겹쳐 찍지 않고 안으로만 들어간다
            for child in node.children:
                visit(child, level, path)
            return
        if not include_hidden and is_hidden(node):
            return
        if state["truncated"] and level > 0:
            return
        if depth and level >= depth:
            return

        role = role_of(node, doc)
        skip_self = role is None or role in {"presentation", "none"}
        child_level = level
        child_path = path

        if not skip_self:
            if len(out) >= max_nodes:
                state["truncated"] = True
                return
            entry = Entry(
                role=role,
                name="" if role == "presentation" else _short(accessible_name(node, doc)),
                ref=refs.get(id(node), ""),
                line=node.line,
                depth=level,
                extra=_extras(node),
                node=node,
                path=path,
            )
            out.append(entry)
            child_level = level + 1
            child_path = path + (entry.label(),)
            has_element_child = any(not c.is_text for c in node.children)
            if role in _TEXTUAL and not has_element_child:
                return

        for child in node.children:
            if child.is_text:
                text = _short(child.text)
                if not text or node.tag in {"html", "body", "#document"}:
                    continue
                if len(out) >= max_nodes:
                    state["truncated"] = True
                    return
                out.append(
                    Entry(
                        role="text",
                        name=text,
                        ref="",
                        line=child.line,
                        depth=child_level,
                        node=child,
                        path=child_path,
                    )
                )
                continue
            visit(child, child_level, child_path)

    starts: list[Node] = list(doc.root.children)
    notes: list[str] = []
    if root_ref:
        target = ref_target(doc, root_ref)
        if target is not None:
            starts = [target]
        else:
            notes.append(f"{root_ref} 을(를) 찾지 못해 문서 전체를 보여 줍니다.")

    for start in starts:
        visit(start, 0, ())

    snapshot.entries = out
    snapshot.refs = {e.ref: e.node for e in out if e.node is not None}
    snapshot.truncated = state["truncated"]
    if state["truncated"]:
        notes.append(
            f"노드 {max_nodes}개에서 잘랐습니다 — max_nodes 를 올리거나 ref=eN 으로 하위만 보세요."
        )
    if not out:
        notes.append(
            "보이는 요소가 없습니다. JS 로 그리는 페이지라면 정적 HTML 에는 내용이 없습니다."
        )
    snapshot.notes = notes
    return snapshot
