"""JS/TS 파일에서 import·export·테스트 선언을 정규식으로 읽는다.

AST 파서를 넣지 않는 이유: 이 툴은 '테스트가 도달하는가'만 보면 되고, 언어별 파서를
번들하면 설치가 무거워진다. 대신 못 읽는 형태(동적 require, 템플릿 문자열 경로)를
dynamic_import 로 표시해 '모른다'를 결과에 남긴다.
"""

from __future__ import annotations

import re

from .types import ImportRef, Module, Symbol, TestItem

JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

IMPORT_RE = re.compile(
    r"""^[ \t]*import\s+(?:type\s+)?(?:([\w*{}\s,$]+?)\s+from\s+)?["']([^"']+)["']""",
    re.MULTILINE,
)
NAMED_RE = re.compile(r"\{([^}]*)\}")
EXPORT_FROM_RE = re.compile(r"""^[ \t]*export\s+(?:\*|\{[^}]*\})\s+from\s+["']([^"']+)["']""", re.MULTILINE)
REQUIRE_RE = re.compile(r"""require\(\s*["']([^"']+)["']\s*\)""")
DESTRUCT_REQUIRE_RE = re.compile(
    r"""(?:const|let|var)\s+\{([^}]+)\}\s*=\s*require\(\s*["']([^"']+)["']\s*\)""")
DEFAULT_REQUIRE_RE = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\(\s*["']([^"']+)["']\s*\)""")
DYNAMIC_RE = re.compile(r"""(?:require|import)\(\s*(?!["'])[^)]*\)""")
FUNCTION_RE = re.compile(
    r"""^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)""", re.MULTILINE)
CLASS_RE = re.compile(r"""^[ \t]*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)""", re.MULTILINE)
CONST_FN_RE = re.compile(
    r"""^[ \t]*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?\(""", re.MULTILINE)
EXPORT_LIST_RE = re.compile(r"""^[ \t]*export\s*\{([^}]*)\}""", re.MULTILINE)
EXPORT_DECL_RE = re.compile(
    r"""^[ \t]*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)""",
    re.MULTILINE)

TEST_DECL_RE = re.compile(
    r"""^[ \t]*(x?test|x?it|x?specify|x?describe)(\.(?:only|skip|todo|each\([^)]*\)))?\s*\(\s*(['"`])(.+?)\3""",
    re.MULTILINE)


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def is_js(path: str) -> bool:
    return path.endswith(JS_SUFFIXES)


def parse_module(path: str, source: str) -> Module:
    module = Module(path=path, name=path, language="javascript", source=source)
    module.lines = source.count("\n") + (0 if source.endswith("\n") else 1)
    module.dynamic_import = bool(DYNAMIC_RE.search(source))

    refs: list[ImportRef] = []
    for match in IMPORT_RE.finditer(source):
        clause = (match.group(1) or "").strip()
        names: tuple[str, ...] = ()
        named = NAMED_RE.search(clause)
        if named:
            parts = [part.strip().split(" as ")[0].strip() for part in named.group(1).split(",")]
            names = tuple(part for part in parts if part)
        refs.append(ImportRef(module=match.group(2), names=names, lineno=_line_of(source, match.start())))
    for match in EXPORT_FROM_RE.finditer(source):
        refs.append(ImportRef(module=match.group(1), lineno=_line_of(source, match.start())))
    for match in DESTRUCT_REQUIRE_RE.finditer(source):
        names = tuple(part.strip().split(":")[-1].strip() for part in match.group(1).split(",") if part.strip())
        refs.append(ImportRef(module=match.group(2), names=names, lineno=_line_of(source, match.start())))
    for match in REQUIRE_RE.finditer(source):
        if any(ref.lineno == _line_of(source, match.start()) for ref in refs):
            continue
        refs.append(ImportRef(module=match.group(1), lineno=_line_of(source, match.start())))

    seen: set[tuple[str, int]] = set()
    unique_refs: list[ImportRef] = []
    for ref in refs:
        key = (ref.module, ref.lineno)
        if key in seen:
            continue
        seen.add(key)
        unique_refs.append(ref)
    unique_refs.sort(key=lambda ref: (ref.lineno, ref.module))
    module.imports = unique_refs

    symbols: list[Symbol] = []
    for pattern, kind in ((FUNCTION_RE, "function"), (CLASS_RE, "class"), (CONST_FN_RE, "function")):
        for match in pattern.finditer(source):
            name = match.group(1)
            symbols.append(
                Symbol(
                    name=name,
                    qualname=name,
                    kind=kind,
                    lineno=_line_of(source, match.start()),
                    end_lineno=_line_of(source, match.start()),
                    is_public=not name.startswith("_"),
                )
            )
    module.symbols = sorted(symbols, key=lambda symbol: (symbol.lineno, symbol.name))

    exports: list[str] = [match.group(1) for match in EXPORT_DECL_RE.finditer(source)]
    for match in EXPORT_LIST_RE.finditer(source):
        for part in match.group(1).split(","):
            name = part.strip().split(" as ")[-1].strip()
            if name:
                exports.append(name)
    module.exports = tuple(dict.fromkeys(exports))
    module.strings = {ref.module for ref in module.imports if "." in ref.module or "/" not in ref.module}
    return module


def test_items(path: str, source: str) -> list[TestItem]:
    items: list[TestItem] = []
    for match in TEST_DECL_RE.finditer(source):
        kind, modifier, _, title = match.groups()
        title = title.strip()
        if not title:
            continue
        qualifier = (modifier or "").strip(".")
        skip = qualifier in ("skip", "todo") or kind.startswith("x")
        kind = kind.lstrip("x")
        items.append(
            TestItem(
                path=path,
                name=title if kind == "describe" else title,
                lineno=_line_of(source, match.start()),
                skip=skip,
                xfail=False,
            )
        )
    return items
