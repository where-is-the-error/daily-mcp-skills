"""관대한 HTML → 트리 (표준 라이브러리 html.parser 만 사용).

브라우저가 없으므로 "브라우저가 할 법한" 파싱을 최소한만 흉내 낸다:
  - 빈 요소(br·img·input …)는 닫지 않는다
  - `<li>` 안의 `<li>`, `<p>` 뒤의 블록, `<td>` 뒤의 `<td>` 같은 흔한 암묵적 닫힘
  - 짝이 안 맞는 닫는 태그는 무시 (예외를 던지지 않는다)
  - `<script>`·`<style>` 안의 `<` 는 마크업이 아니라 글자로 본다 (html.parser 가 처리)
  - 각 요소에 **원본 파일의 줄 번호**를 남긴다 — 정적 분석이라서 줄 번호를 줄 수 있다

정확한 DOM 이 아니다. 목적은 접근성 트리를 만드는 것 하나뿐이고,
그 밖의 용도(레이아웃·CSS·JS)는 이 모듈의 일이 아니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

__all__ = [
    "Node",
    "Document",
    "parse",
    "parse_file",
    "decode_bytes",
    "VOID",
    "RAW_TEXT",
    "norm",
]

VOID = frozenset(
    "area base br col embed hr img input keygen link meta param source track wbr".split()
)
RAW_TEXT = frozenset("script style".split())
# 트리에는 남기지만 접근성 트리·이름 계산에서는 내용을 보지 않는 요소
HEAD_ONLY = frozenset("script style template noscript meta link title base".split())

_BLOCK = frozenset(
    """address article aside blockquote details div dl fieldset figcaption figure footer form
    h1 h2 h3 h4 h5 h6 header hgroup hr main nav ol p pre section table ul""".split()
)

# 새 태그를 만났을 때 스택 위쪽에서 암묵적으로 닫아야 하는 태그들
_AUTO_CLOSE: dict[str, frozenset[str]] = {
    "li": frozenset({"li"}),
    "dt": frozenset({"dt", "dd"}),
    "dd": frozenset({"dt", "dd"}),
    "tr": frozenset({"tr", "td", "th"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "thead": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "tbody": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "tfoot": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "option": frozenset({"option"}),
    "optgroup": frozenset({"optgroup", "option"}),
    "p": frozenset({"p"}),
    "a": frozenset({"a"}),
}
for _tag in _BLOCK:
    _AUTO_CLOSE.setdefault(_tag, frozenset())
    _AUTO_CLOSE[_tag] = _AUTO_CLOSE[_tag] | frozenset({"p"})

_WS = re.compile(r"\s+")


def norm(text: str | None) -> str:
    """공백을 하나로 접고 앞뒤를 자른다 (접근성 이름·텍스트 비교의 기본형)."""
    return _WS.sub(" ", text or "").strip()


@dataclass
class Node:
    tag: str = ""  # "" 이면 텍스트 노드
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None
    line: int = 0
    order: int = 0  # 문서 순서 (0부터)
    text: str = ""  # 텍스트 노드일 때의 내용

    # ---------------------------------------------------------------- 조회
    @property
    def is_text(self) -> bool:
        return self.tag == ""

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def has(self, name: str) -> bool:
        return name in self.attrs

    def elements(self) -> list["Node"]:
        return [n for n in self.walk() if not n.is_text]

    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()

    def descendants(self, *tags: str):
        wanted = {t.lower() for t in tags}
        return [n for n in self.walk() if n.tag in wanted]

    def ancestors(self):
        node = self.parent
        while node is not None and node.tag != "#document":
            yield node
            node = node.parent

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        label = self.tag or "#text"
        attrs = "".join(f" {k}={v!r}" for k, v in sorted(self.attrs.items()))
        return f"<{label}{attrs} L{self.line}>"


@dataclass
class Document:
    root: Node  # tag == "#document"
    path: str = ""
    source: str = ""
    doctype: str = ""
    duplicates: dict[str, int] = field(default_factory=dict)  # id -> 등장 횟수

    def elements(self) -> list[Node]:
        return [n for n in self.root.walk() if not n.is_text]

    def by_tag(self, *tags: str) -> list[Node]:
        wanted = {t.lower() for t in tags}
        return [n for n in self.elements() if n.tag in wanted]

    def first(self, *tags: str) -> Node | None:
        found = self.by_tag(*tags)
        return found[0] if found else None

    def id_index(self) -> dict[str, Node]:
        index: dict[str, Node] = {}
        for node in self.elements():
            ident = node.get("id").strip()
            if ident and ident not in index:
                index[ident] = node
        return index


class _Builder(HTMLParser):
    def __init__(self, path: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="#document", line=1)
        self.stack: list[Node] = [self.root]
        self.doctype = ""
        self._order = 0
        self.path = path

    # ------------------------------------------------------------------
    def _next_order(self) -> int:
        self._order += 1
        return self._order

    def _open(self, tag: str, attrs, line: int) -> None:
        # 암묵적 닫힘
        closers = _AUTO_CLOSE.get(tag)
        if closers:
            while len(self.stack) > 1 and self.stack[-1].tag in closers:
                self.stack.pop()
        node = Node(tag=tag, attrs={}, parent=self.stack[-1], line=line, order=self._next_order())
        for name, value in attrs:
            key = name.lower()
            if key not in node.attrs:  # 중복 속성은 첫 번째가 이긴다
                node.attrs[key] = "" if value is None else value
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    # ------------------------------------------------------------------
    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype"):
            self.doctype = decl

    def handle_starttag(self, tag, attrs) -> None:
        line, _ = self.getpos()
        self._open(tag.lower(), attrs, line)

    def handle_startendtag(self, tag, attrs) -> None:
        line, _ = self.getpos()
        tag = tag.lower()
        self._open(tag, attrs, line)
        if tag not in VOID and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag) -> None:
        tag = tag.lower()
        if tag in VOID:
            return
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return
        # 짝이 없는 닫는 태그는 버린다

    def handle_data(self, data) -> None:
        if not data:
            return
        line, _ = self.getpos()
        parent = self.stack[-1]
        # 앞 텍스트와 이어 붙이기 (엔티티·CDATA 분할 대비)
        if parent.children and parent.children[-1].is_text:
            parent.children[-1].text += data
            return
        parent.children.append(
            Node(tag="", text=data, parent=parent, line=line, order=self._next_order())
        )

    def handle_comment(self, data) -> None:  # 주석은 트리에 넣지 않는다
        return

    def handle_pi(self, data) -> None:  # <?xml ...?>
        return


def parse(html: str, path: str = "") -> Document:
    builder = _Builder(path=path)
    builder.feed(html)
    builder.close()
    doc = Document(root=builder.root, path=path, source=html, doctype=builder.doctype)
    counts: dict[str, int] = {}
    for node in doc.elements():
        ident = node.get("id").strip()
        if ident:
            counts[ident] = counts.get(ident, 0) + 1
    doc.duplicates = counts
    return doc


_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w\-]+)""", re.I)


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """바이트 → 글자. 인코딩 이름을 함께 돌려준다.

    한국 사이트는 아직 euc-kr/cp949 가 흔하다. BOM → meta charset → utf-8 → cp949 순서.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", "replace"), "utf-16"
    match = _META_CHARSET.search(raw[:4096])
    if match:
        declared = match.group(1).decode("ascii", "replace").lower()
        if declared in {"euc-kr", "euckr", "ks_c_5601-1987", "cp949", "x-windows-949"}:
            return raw.decode("cp949", "replace"), "cp949"
        try:
            return raw.decode(declared, "replace"), declared
        except LookupError:
            pass
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp949", "replace"), "cp949"


def parse_file(path: str | Path) -> Document:
    target = Path(path)
    raw = target.read_bytes()
    text, _encoding = decode_bytes(raw)
    doc = parse(text, path=str(target))
    return doc
