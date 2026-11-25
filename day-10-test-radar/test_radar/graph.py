"""저장소를 모듈 그래프로 읽는다 — import 를 파일 사이의 간선으로.

Python 은 ast, JS/TS 는 정규식. 해석하지 못한 import 는 '밖(external)'으로 두고
동적 import 가 있으면 그 사실을 남긴다. 간선은 방향이 있다: importer → imported.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import jsimports, pyast
from .types import ImportRef, Module, Symbol, TestFile, TestItem

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "coverage", "htmlcov", ".idea", ".vscode", ".terraform",
    "site-packages", "vendor", "third_party", ".eggs",
}

TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")
JS_TEST_RE = re.compile(r"(\.test\.|\.spec\.|/__tests__/)")
SKIP_FILE_RE = re.compile(r"(^|/)(setup\.py|conftest\.py|noxfile\.py)$")
MAX_BYTES = 2_000_000


@dataclass
class Repo:
    root: str = "."
    modules: dict[str, Module] = field(default_factory=dict)   # path -> Module (테스트 포함)
    tests: dict[str, TestFile] = field(default_factory=dict)   # path -> TestFile
    name_index: dict[str, list[str]] = field(default_factory=dict)
    hidden: list[str] = field(default_factory=list)            # 해석 못 한 import 이름
    skipped: list[str] = field(default_factory=list)
    package_markers: set[str] = field(default_factory=set)     # __init__.py 있는 디렉터리

    # ---------------------------------------------------------------- 조회
    def module(self, path: str) -> Module | None:
        return self.modules.get(path)

    def test(self, path: str) -> TestFile | None:
        return self.tests.get(path)

    def is_test(self, path: str) -> bool:
        return path in self.tests

    def all_tests(self) -> list[TestFile]:
        return sorted(self.tests.values(), key=lambda test: test.path)

    def total_items(self) -> int:
        return sum(len(test.items) for test in self.tests.values())

    def importers_of(self, path: str, include_tests: bool = True) -> set[str]:
        """path 를 직접 import 하는 파일들."""
        out: set[str] = set()
        for other in self.modules.values():
            if other.path == path:
                continue
            if path in other.resolved:
                if not include_tests and other.path in self.tests:
                    continue
                out.add(other.path)
        return out

    def importers_of_name(self, module_name: str, include_tests: bool = True) -> set[str]:
        """이름으로 import 하는 파일 — 파일이 이미 사라져 그래프에 간선이 없을 때 쓴다."""
        out: set[str] = set()
        if not module_name:
            return out
        for other in self.modules.values():
            if not include_tests and other.path in self.tests:
                continue
            for ref in other.imports:
                if ref.level:
                    continue
                if ref.module == module_name:
                    out.add(other.path)
                    break
        return out

    def fan_in(self, path: str) -> int:
        return len(self.importers_of(path, include_tests=False))

    def transitive_importers(self, path: str, depth: int = 2) -> dict[str, int]:
        """path 를 (전이적으로) import 하는 파일 → 거리(1..depth)."""
        found: dict[str, int] = {}
        frontier = [path]
        seen = {path}
        for level in range(1, max(1, depth) + 1):
            next_frontier: list[str] = []
            for target in frontier:
                for importer in self.importers_of(target):
                    if importer in seen:
                        continue
                    seen.add(importer)
                    found[importer] = level
                    next_frontier.append(importer)
            frontier = next_frontier
            if not frontier:
                break
        return found

    def tests_reaching(self, path: str, depth: int = 3) -> set[str]:
        """이 모듈에 (전이로) 도달하는 테스트 파일들."""
        importers = self.transitive_importers(path, depth=depth)
        return {candidate for candidate in importers if candidate in self.tests}

    def package_of(self, path: str) -> str:
        return str(Path(path).parent).replace("\\", "/")

    def summary(self) -> dict:
        languages = {"python": 0, "javascript": 0}
        for module in self.modules.values():
            languages[module.language] = languages.get(module.language, 0) + 1
        return {
            "root": self.root,
            "modules": len([m for m in self.modules.values() if m.path not in self.tests]),
            "files": len(self.modules),
            "tests": len([test for test in self.tests.values() if not test.is_conftest]),
            "conftests": len([test for test in self.tests.values() if test.is_conftest]),
            "test_items": self.total_items(),
            "python": len([m for m in self.modules.values() if m.language == "python"]),
            "javascript": len([m for m in self.modules.values() if m.language == "javascript"]),
            "unresolved": len(self.hidden),
            "parse_errors": len([m for m in self.modules.values() if m.parse_error]),
            "skipped": len(self.skipped),
        }


# ------------------------------------------------------------------ 만들기
def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load(root: str | Path, max_files: int = 20000, include: list[str] | None = None) -> Repo:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"저장소 경로가 없습니다: {root_path}")
    repo = Repo(root=str(root_path))
    count = 0
    for current, dirs, files in os.walk(root_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git"))
        rel_dir = os.path.relpath(current, root_path).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        if include is not None and rel_dir and not any(rel_dir.startswith(prefix) for prefix in include):
            dirs[:] = []
            continue
        for name in sorted(files):
            if not (name.endswith(".py") or jsimports.is_js(name)):
                continue
            count += 1
            if count > max_files:
                repo.skipped.append("max_files")
                break
            rel = f"{rel_dir}/{name}" if rel_dir else name
            text = _read(Path(current) / name)
            if text == "":
                repo.skipped.append(rel)
                continue
            if name.endswith(".py"):
                module = pyast.parse_module(rel, text, pyast.module_name(rel, root_path, rel.endswith("__init__.py")), root_path)
                if rel.endswith("__init__.py"):
                    repo.package_markers.add(rel_dir)
            else:
                module = jsimports.parse_module(rel, text)
            repo.modules[rel] = module
        if count > max_files:
            break
    _index_names(repo)
    for module in list(repo.modules.values()):
        _resolve(repo, module)
    _collect_tests(repo)
    return repo


def _index_names(repo: Repo) -> None:
    for path, module in repo.modules.items():
        keys = {module.name}
        if module.name.startswith(("src.", "lib.")):
            keys.add(module.name.split(".", 1)[1])
        for key in keys:
            repo.name_index.setdefault(key, []).append(path)
        if path.endswith("__init__.py"):
            package = path[: -len("/__init__.py")] if "/__init__.py" in path else ""
            if package:
                repo.name_index.setdefault(package.replace("/", "."), []).append(path)
                if package.startswith("src/"):
                    repo.name_index.setdefault(package[4:].replace("/", "."), []).append(path)
    for key in repo.name_index:
        repo.name_index[key] = sorted(set(repo.name_index[key]))


def _python_candidates(repo: Repo, module: Module, ref: ImportRef) -> list[str]:
    if ref.level:
        parts = module.name.split(".")
        package = parts if module.is_package else parts[:-1]
        up = max(0, ref.level - 1)
        base_parts = package[: len(package) - up] if up else package
        if ref.module:
            base_parts = base_parts + ref.module.split(".")
        base = ".".join(base_parts)
    else:
        base = ref.module
    if not base:
        return []
    found: list[str] = []
    exact = repo.name_index.get(base, [])
    found.extend(exact)
    if ref.level == 0:
        # `pkg.mod` 를 저장소 루트가 아니라 하위 디렉터리 패키지로 둔 경우
        suffix = "." + base
        for name, paths in repo.name_index.items():
            if name.endswith(suffix):
                found.extend(paths)
    for name in ref.names:
        for path in repo.name_index.get(f"{base}.{name}", []):
            found.append(path)
    return sorted(set(found))


def _js_candidates(repo: Repo, module: Module, ref: ImportRef) -> list[str]:
    spec = ref.module
    if not spec.startswith(".") and not spec.startswith("@/") and not spec.startswith("~/"):
        return []
    if spec.startswith("@/"):
        base = "src/" + spec[2:]
    elif spec.startswith("~/"):
        base = spec[2:]
    else:
        base = str((Path(module.path).parent / spec))
    base = os.path.normpath(base).replace("\\", "/")
    if base.startswith("../"):
        return []
    candidates: list[str] = []
    if base in repo.modules:
        candidates.append(base)
    for suffix in jsimports.JS_SUFFIXES:
        if base + suffix in repo.modules:
            candidates.append(base + suffix)
    for suffix in jsimports.JS_SUFFIXES:
        index = f"{base}/index{suffix}"
        if index in repo.modules:
            candidates.append(index)
    if not candidates:
        for path in repo.modules:
            if path.rsplit(".", 1)[0] == base:
                candidates.append(path)
    return candidates


def _resolve(repo: Repo, module: Module) -> None:
    for ref in module.imports:
        if module.language == "python":
            candidates = _python_candidates(repo, module, ref)
        else:
            candidates = _js_candidates(repo, module, ref)
        if not candidates:
            if ref.module and not ref.module.startswith((".", "@", "~")) or ref.level:
                if ref.module not in repo.hidden:
                    repo.hidden.append(ref.module)
            continue
        for path in candidates:
            module.resolved.add(path)
            names = set(module.imported_symbols.get(path, set()))
            if ref.names:
                names.update(ref.names)
            if ref.is_star:
                names.add("*")
            module.imported_symbols[path] = names


def _test_decorators(symbol: Symbol) -> tuple[bool, bool, bool]:
    skip = any("skip" in dec for dec in symbol.decorators)
    xfail = any("xfail" in dec for dec in symbol.decorators)
    parametrized = any("parametrize" in dec for dec in symbol.decorators)
    return skip, xfail, parametrized


def _collect_tests(repo: Repo) -> None:
    for path, module in repo.modules.items():
        name = Path(path).name
        is_conftest = Path(path).name == "conftest.py"
        is_py_test = (bool(TEST_FILE_RE.search(path)) and path.endswith(".py")) or is_conftest
        is_js_test = jsimports.is_js(path) and bool(JS_TEST_RE.search(path))
        if not (is_py_test or is_js_test):
            continue
        test = TestFile(
            path=path,
            language="python" if path.endswith(".py") else "javascript",
            resolved=set(module.resolved),
            imported_symbols={key: set(value) for key, value in module.imported_symbols.items()},
            string_refs={text for text in module.strings},
            identifiers=set(re.findall(r"[A-Za-z_]\w*", module.source)),
            is_conftest=is_conftest,
            parse_error=module.parse_error,
        )
        if is_py_test and name != "conftest.py":
            items: list[TestItem] = []
            for symbol in module.symbols:
                if symbol.kind == "function" and symbol.name.startswith("test") and not symbol.parent:
                    skip, xfail, parametrized = _test_decorators(symbol)
                    items.append(TestItem(path=path, name=symbol.name, lineno=symbol.lineno,
                                          skip=skip, xfail=xfail, parametrized=parametrized))
                elif symbol.kind == "class" and symbol.name.startswith("Test"):
                    for inner in module.symbols:
                        if inner.parent == symbol.qualname and inner.name.startswith("test"):
                            skip, xfail, parametrized = _test_decorators(inner)
                            items.append(TestItem(path=path, name=f"{symbol.name}::{inner.name}",
                                                  lineno=inner.lineno, skip=skip, xfail=xfail,
                                                  parametrized=parametrized))
            module_mark = any("skip" in dec for symbol in module.symbols for dec in symbol.decorators)
            if module_mark and not items:
                items.append(TestItem(path=path, name="(module skip)", skip=True))
            test.items = items
        elif is_js_test:
            test.items = jsimports.test_items(path, module.source)
        repo.tests[path] = test


def load_sources(files: dict[str, str], root: str = ".") -> Repo:
    """디스크 없이 소스 사전으로 그래프를 만든다(테스트용·미리보기용)."""
    repo = Repo(root=root)
    for rel, text in files.items():
        rel = rel.replace("\\", "/").lstrip("./")
        if rel.endswith(".py"):
            module = pyast.parse_module(rel, text, pyast.module_name(rel, root, rel.endswith("__init__.py")), root)
            if rel.endswith("__init__.py"):
                repo.package_markers.add(str(Path(rel).parent).replace("\\", "/"))
        elif jsimports.is_js(rel):
            module = jsimports.parse_module(rel, text)
        else:
            continue
        repo.modules[rel] = module
    _index_names(repo)
    for module in list(repo.modules.values()):
        _resolve(repo, module)
    _collect_tests(repo)
    return repo
