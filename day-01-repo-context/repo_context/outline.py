"""Symbol outlines — so a pack can point at "line 42" instead of pasting 400 lines.

Python goes through :mod:`ast` (exact line numbers, nested methods, docstring
hints). Everything else falls back to per-language declaration patterns, which
is lossy by design: an outline that is roughly right still saves a read.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

PYTHON = {".py", ".pyi"}
JAVASCRIPT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"}
GO = {".go"}
JVM = {".java", ".kt", ".kts", ".scala", ".cs"}
RUST = {".rs"}
RUBY = {".rb"}
PHP = {".php"}
CLIKE = {".c", ".h", ".cc", ".cpp", ".hpp"}

OUTLINE_EXTENSIONS = PYTHON | JAVASCRIPT | GO | JVM | RUST | RUBY | PHP | CLIKE

MAX_SYMBOLS = 80
MAX_NOTE = 64


@dataclass(frozen=True)
class Symbol:
    kind: str
    name: str
    line: int
    note: str = ""


def _trim(text: str | None) -> str:
    if not text:
        return ""
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first[:MAX_NOTE]


def _python_symbols(tree: ast.AST) -> list[Symbol]:
    symbols: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "def" if isinstance(node, ast.FunctionDef) else "async def"
            symbols.append(Symbol(kind, node.name, node.lineno, _trim(ast.get_docstring(node))))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol("class", node.name, node.lineno, _trim(ast.get_docstring(node))))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "method" if isinstance(child, ast.FunctionDef) else "async method"
                    symbols.append(
                        Symbol(kind, f"{node.name}.{child.name}", child.lineno, _trim(ast.get_docstring(child)))
                    )
    return symbols


def _python_outline(text: str) -> list[Symbol] | None:
    try:
        return _python_symbols(ast.parse(text))
    except (SyntaxError, ValueError):
        return None


_REGEX_RULES: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "js": [
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)")),
        ("arrow", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")),
    ],
    "go": [
        ("func", re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")),
        ("type", re.compile(r"^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)")),
    ],
    "jvm": [
        ("type", re.compile(r"^\s*(?:public|private|protected|internal|abstract|final|static|\s)*\b(?:class|interface|enum|record|object)\s+(\w+)")),
        ("method", re.compile(r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\],.? ]+\s+(\w+)\s*\(")),
    ],
    "rust": [
        ("fn", re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)")),
        ("type", re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)")),
        ("impl", re.compile(r"^\s*impl(?:<[^>]*>)?\s+([A-Za-z_][\w:<>]*)")),
    ],
    "ruby": [
        ("class", re.compile(r"^\s*class\s+([A-Z]\w*)")),
        ("module", re.compile(r"^\s*module\s+([A-Z]\w*)")),
        ("def", re.compile(r"^\s*def\s+(?:self\.)?([\w.!?=]+)")),
    ],
    "php": [
        ("class", re.compile(r"^\s*(?:final\s+|abstract\s+)?class\s+(\w+)")),
        ("function", re.compile(r"^\s*(?:public|private|protected|static|\s)*function\s+(\w+)")),
    ],
    "clike": [
        ("function", re.compile(r"^\s*(?:static\s+|inline\s+|extern\s+|const\s+)*[A-Za-z_][\w:<>\*&\s]*\s+\**([A-Za-z_]\w*)\s*\([^;]*$")),
        ("type", re.compile(r"^\s*(?:typedef\s+)?(?:struct|class|enum|union)\s+(\w+)")),
    ],
}


def _language(suffix: str) -> str:
    if suffix in JAVASCRIPT:
        return "js"
    if suffix in GO:
        return "go"
    if suffix in JVM:
        return "jvm"
    if suffix in RUST:
        return "rust"
    if suffix in RUBY:
        return "ruby"
    if suffix in PHP:
        return "php"
    return "clike"


def _regex_outline(text: str, suffix: str) -> list[Symbol]:
    rules = _REGEX_RULES[_language(suffix)]
    symbols: list[Symbol] = []
    seen: set[tuple[str, str]] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(("//", "#", "*", "/*")) and "function" not in line:
            continue
        for kind, pattern in rules:
            match = pattern.search(line)
            if match:
                name = match.group(1)
                key = (kind, name)
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(Symbol(kind, name, number))
                break
    return symbols


def outline(text: str, filename: str) -> list[Symbol]:
    """Declarations in ``text``, in file order. Empty list when unsupported."""
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix in PYTHON:
        symbols = _python_outline(text)
        if symbols is not None:
            return symbols[:MAX_SYMBOLS]
    if suffix in OUTLINE_EXTENSIONS:
        return _regex_outline(text, suffix)[:MAX_SYMBOLS]
    return []


def render_symbols(symbols: list[Symbol], limit: int = 12) -> list[str]:
    """Outline lines like ``- class Sandbox (L20)`` plus a docstring hint."""
    lines = []
    for symbol in symbols[:limit]:
        note = f" — {symbol.note}" if symbol.note else ""
        lines.append(f"- {symbol.kind} `{symbol.name}` (L{symbol.line}){note}")
    if len(symbols) > limit:
        lines.append(f"- … 심볼 {len(symbols) - limit}개 더 (file_outline으로 전체 확인)")
    return lines
