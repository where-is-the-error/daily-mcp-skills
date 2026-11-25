"""Python 파일 하나를 '모듈'로 읽는다 — import, 심볼, 문자열 참조, 최상위 실행 줄.

ast 를 쓰므로 파일을 실행하지 않는다. 읽지 못하면 parse_error 를 남기고 계속한다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .types import ImportRef, Module, Symbol

PY_SUFFIX = ".py"
DYNAMIC_RE = re.compile(r"(importlib\.import_module|importlib\.util\.spec_from_file_location|(?<![\w.])__import__\s*\()")
DOTTED_RE = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+$")


def _strip_src(parts: list[str]) -> list[str]:
    if parts and parts[0] in ("src", "lib"):
        return parts[1:]
    return parts


def module_name(path: str, root: str | Path, is_package_init: bool = False) -> str:
    """저장소 루트 기준 경로 → 점 이름. `pkg/__init__.py` → `pkg`."""
    root_path = Path(root).resolve()
    full = (root_path / path).resolve()
    try:
        rel = full.relative_to(root_path)
    except ValueError:
        rel = Path(path)
    parts = list(rel.with_suffix("").parts) if not is_package_init else list(rel.parent.parts)
    parts = _strip_src(parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(part for part in parts if part not in (".", ""))


def is_package_dir(directory: Path) -> bool:
    return (directory / "__init__.py").exists()


def package_dir_for(path: str, root: str | Path) -> str:
    """그 파일이 속한 패키지 디렉터리(저장소 상대) — conftest 범위 계산에 쓴다."""
    return str(Path(path).parent).replace("\\", "/")


def _signature(node: ast.AST) -> tuple[str, tuple[str, ...]]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "", ()
    try:
        args = node.args
        parts: list[str] = []
        positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
        defaults = list(args.defaults)
        first_default = len(positional) - len(defaults)
        for position, arg in enumerate(positional):
            text = arg.arg
            if position >= first_default:
                default = defaults[position - first_default]
                try:
                    text += "=" + ast.unparse(default)
                except Exception:
                    text += "=…"
            parts.append(text)
        if args.vararg:
            parts.append("*" + args.vararg.arg)
        elif args.kwonlyargs:
            parts.append("*")
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            text = arg.arg
            if default is not None:
                try:
                    text += "=" + ast.unparse(default)
                except Exception:
                    text += "=…"
            parts.append(text)
        if args.kwarg:
            parts.append("**" + args.kwarg.arg)
        params = tuple(part.split("=")[0].lstrip("*") for part in parts)
        return f"({', '.join(parts)})", tuple(name for name in params if name)
    except Exception:
        return "(…)", ()


def _decorator_names(node: ast.AST) -> tuple[str, ...]:
    out: list[str] = []
    for decorator in getattr(node, "decorator_list", []):
        try:
            out.append(ast.unparse(decorator))
        except Exception:
            out.append("?")
    return tuple(out)


def _walk_symbols(body: list[ast.stmt], prefix: str, out: list[Symbol], parent: str = "") -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signature, params = _signature(node)
            qualname = f"{prefix}{node.name}"
            out.append(
                Symbol(
                    name=node.name,
                    qualname=qualname,
                    kind="method" if parent else "function",
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    signature=signature,
                    decorators=_decorator_names(node),
                    is_public=not node.name.startswith("_"),
                    parent=parent,
                    params=params,
                )
            )
        elif isinstance(node, ast.ClassDef):
            qualname = f"{prefix}{node.name}"
            out.append(
                Symbol(
                    name=node.name,
                    qualname=qualname,
                    kind="class",
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    decorators=_decorator_names(node),
                    is_public=not node.name.startswith("_"),
                    parent=parent,
                )
            )
            _walk_symbols(node.body, prefix + node.name + ".", out, parent=qualname)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    constant = name.isupper() or name.startswith("__")
                    if constant:
                        out.append(
                            Symbol(
                                name=name,
                                qualname=f"{prefix}{name}",
                                kind="constant",
                                lineno=node.lineno,
                                end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                                is_public=not name.startswith("_"),
                                parent=parent,
                            )
                        )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name.isupper():
                out.append(
                    Symbol(
                        name=name,
                        qualname=f"{prefix}{name}",
                        kind="constant",
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        is_public=not name.startswith("_"),
                        parent=parent,
                    )
                )


def _top_level_exec_lines(tree: ast.Module) -> set[int]:
    """import·def·class·docstring 을 뺀, 읽자마자 실행되는 줄."""
    lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue                                     # 모듈 docstring
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start) or start
        lines.update(range(start, end + 1))
    return lines


def _string_literals(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip()
            if 2 < len(text) <= 200 and (DOTTED_RE.match(text) or "::" in text):
                out.add(text)
    return out


def _exports(tree: ast.Module) -> tuple[str, ...]:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    try:
                        value = ast.literal_eval(node.value)
                    except Exception:
                        return ()
                    if isinstance(value, (list, tuple)):
                        return tuple(str(item) for item in value)
    return ()


def parse_module(path: str, source: str, name: str = "", root: str | Path = ".") -> Module:
    module = Module(path=path, name=name or module_name(path, root), source=source)
    module.is_package = path.endswith("__init__.py")
    module.lines = source.count("\n") + (0 if source.endswith("\n") else 1)
    module.dynamic_import = bool(DYNAMIC_RE.search(source))
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        module.parse_error = f"{exc.__class__.__name__}: {exc.msg} (line {exc.lineno})"
        return module
    except ValueError as exc:
        module.parse_error = f"ValueError: {exc}"
        return module

    imports: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportRef(module=alias.name, names=(), lineno=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names = tuple(alias.name for alias in node.names)
            star = "*" in names
            imports.append(
                ImportRef(
                    module=base,
                    names=tuple(n for n in names if n != "*"),
                    lineno=node.lineno,
                    level=node.level or 0,
                    is_star=star,
                )
            )
    imports.sort(key=lambda ref: (ref.lineno, ref.module))
    module.imports = imports
    module.symbols = []
    _walk_symbols(tree.body, "", module.symbols)
    module.symbols.sort(key=lambda symbol: (symbol.lineno, symbol.name))
    module.top_level_lines = _top_level_exec_lines(tree)
    module.strings = _string_literals(tree)
    module.exports = _exports(tree)
    return module


def parse_file(path: str, root: str | Path) -> Module:
    full = Path(root) / path
    try:
        source = full.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = full.read_text(encoding="utf-8", errors="replace")
    return parse_module(path, source, module_name(path, root, path.endswith("__init__.py")), root)


def find_defs_in_text(text: str) -> list[str]:
    """'-def foo(' 처럼 diff 에서 사라진 정의 이름만 뽑는다(옛 파일 내용이 없을 때)."""
    out: list[str] = []
    for line in text.splitlines():
        if line[:1] in ("+", "-", " "):
            line = line[1:]
        match = re.match(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", line)
        if match:
            out.append(match.group(1))
    return out
