"""바뀐 파일에서 '도달하는 테스트'를 고른다.

규칙은 하나다 — **근거가 있는 테스트만 고른다**. 직접 import, 바뀐 심볼 참조, 전이 import,
테스트 자신의 변경. 같은 패키지라는 이유만으로는 '선택(optional)'에만 넣는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .graph import Repo
from .types import Diff, FileChange, Selection, Symbol, TestFile

DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)\s*(\([^)]*\))?")
TEST_CONFIG_FILES = {
    "pytest.ini", "tox.ini", "setup.cfg", "noxfile.py", "conftest.py",
    "pyproject.toml", "package.json", "jest.config.js", "jest.config.ts",
    "vitest.config.ts", "vitest.config.js", "karma.conf.js", "phpunit.xml",
}
TEST_CONFIG_KEYS = ("tool.pytest", "tool:pytest", "[pytest]")


@dataclass
class FileView:
    change: FileChange
    module_path: str = ""
    module_name: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    removed_defs: list[str] = field(default_factory=list)
    signature_changes: list[tuple[str, str, str]] = field(default_factory=list)
    tests: list[Selection] = field(default_factory=list)

    @property
    def is_test(self) -> bool:
        return False


@dataclass
class ChangeSet:
    ref: str = ""
    repo: Repo = field(default_factory=Repo)
    diff: Diff = field(default_factory=Diff)
    views: list[FileView] = field(default_factory=list)
    selections: dict[str, Selection] = field(default_factory=dict)
    gaps: list[dict] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- 숫자
    def selected_paths(self, mandatory_only: bool = False) -> list[str]:
        rows = sorted(self.selections.values(), key=lambda sel: (sel.level, -sel.score, sel.path))
        return [row.path for row in rows if not mandatory_only or row.mandatory]

    def selected_items(self) -> int:
        total = 0
        for path in self.selections:
            test = self.repo.test(path)
            total += test.weight() if test else 1
        return total

    def total_items(self) -> int:
        return self.repo.total_items()

    def share(self) -> float:
        total = self.total_items()
        if total <= 0:
            return 0.0
        return round(self.selected_items() / total, 4)

    def test_config_touched(self) -> list[str]:
        out: list[str] = []
        for view in self.views:
            name = Path(view.change.path).name
            if name in TEST_CONFIG_FILES:
                out.append(view.change.path)
                continue
            if name in ("pyproject.toml", "setup.cfg") and any(
                key in view.change.added_text() for key in TEST_CONFIG_KEYS
            ):
                out.append(view.change.path)
        return out

    def changed_modules(self) -> list[str]:
        out: list[str] = []
        for view in self.views:
            if view.module_path and view.module_path not in self.repo.tests:
                out.append(view.module_path)
        return out

    def view_for(self, path: str) -> FileView | None:
        for view in self.views:
            if view.change.path == path or view.change.old_path == path:
                return view
        return None


def _removed_defs(view: FileView) -> list[str]:
    out: list[str] = []
    for _, text in view.change.removed_lines():
        match = DEF_RE.match(text)
        if match:
            out.append(match.group(1))
    return list(dict.fromkeys(out))


def _removed_signatures(view: FileView) -> dict[str, str]:
    out: dict[str, str] = {}
    for _, text in view.change.removed_lines():
        match = DEF_RE.match(text)
        if match and match.group(2):
            out[match.group(1)] = match.group(2).strip()
    return out


def normalize_signature(text: str) -> tuple[str, ...]:
    """'(a: int, b=2, *args)' → ('a', 'b', 'args') — 주석·기본값 표기 차이는 무시한다."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    parts: list[str] = []
    depth = 0
    current = ""
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current)
    names: list[str] = []
    for part in parts:
        head = part.split("=")[0].split(":")[0].strip().lstrip("*")
        if head:
            names.append(head)
    return tuple(names)


def _signature_changes(view: FileView, module) -> list[tuple[str, str, str]]:
    if module is None:
        return []
    removed = _removed_signatures(view)
    changes: list[tuple[str, str, str]] = []
    for name, old in removed.items():
        symbol = module.symbol(name)
        if symbol is None:
            continue
        if symbol.signature and normalize_signature(symbol.signature) != normalize_signature(old):
            changes.append((name, old, symbol.signature))
    return changes


def _strings_for(module, symbol: Symbol | None) -> set[str]:
    if module is None:
        return set()
    out = {module.name}
    if symbol is not None:
        out.add(f"{module.name}.{symbol.name}")
        out.add(symbol.name)
    return out


def _direct_hits(repo: Repo, path: str, module, changed_symbol_names: set[str],
                 old_path: str = "") -> tuple[dict[str, str], dict[str, str]]:
    """(직접 import 한 테스트 → 이유, 심볼 참조로 걸린 테스트 → 이유)."""
    direct: dict[str, str] = {}
    symbol_hits: dict[str, str] = {}
    targets = {path}
    if old_path and old_path != path:
        targets.add(old_path)
    module_name = module.name if module is not None else ""
    for test in repo.tests.values():
        matched = targets & test.resolved
        if matched:
            imported = set()
            for target in matched:
                imported.update(test.imported_symbols.get(target, set()))
            common = changed_symbol_names & imported
            if common:
                names = ", ".join(sorted(common)[:3])
                direct[test.path] = f"바뀐 심볼 `{names}` 를 직접 import"
            elif "*" in imported:
                direct[test.path] = "모듈 전체를 import"
            else:
                direct[test.path] = "바뀐 모듈을 직접 import"
            continue
        if not module_name:
            continue
        refs = test.string_refs
        if not refs:
            continue
        hits = set()
        for name in changed_symbol_names:
            for candidate in (f"{module_name}.{name}", f"{module_name}::{name}"):
                if candidate in refs:
                    hits.add(candidate)
        if hits:
            symbol_hits[test.path] = "문자열로 참조(monkeypatch/목 대상): " + ", ".join(sorted(hits)[:2])
    return direct, symbol_hits


def _same_package_tests(repo: Repo, path: str) -> list[str]:
    package = str(Path(path).parent).replace("\\", "/")
    out: list[str] = []
    for test in repo.tests.values():
        if str(Path(test.path).parent).replace("\\", "/") == package:
            out.append(test.path)
    return out


def build(repo: Repo, diff: Diff, ref: str = "", depth: int = 2) -> ChangeSet:
    change_set = ChangeSet(ref=ref, repo=repo, diff=diff)
    tests_changed = {change.path for change in diff.changes if change.path in repo.tests}
    test_paths = {change.path for change in diff.changes if change.path in repo.tests}

    def add(path: str, level: int, reason: str, score: float) -> None:
        target = repo.test(path)
        if target is not None and target.is_conftest:
            return                          # conftest 는 테스트가 아니라 범위를 정하는 파일
        existing = change_set.selections.get(path)
        test = repo.test(path)
        weight = test.weight() if test else 1
        if existing is not None:
            if level < existing.level or (level == existing.level and score > existing.score):
                change_set.selections[path] = Selection(path=path, level=level, reason=reason,
                                                        score=score, items=weight)
            return
        change_set.selections[path] = Selection(path=path, level=level, reason=reason,
                                                score=score, items=weight)

    for change in diff.changes:
        view = FileView(change=change)
        path = change.path
        module = repo.module(path)
        old_module = repo.module(change.old_path) if change.old_path else None
        if module is None:
            module = old_module
        if module is not None:
            view.module_path = path if repo.module(path) is not None else change.old_path
            view.module_name = module.name
        added_numbers = {number for number, _ in change.added_lines()}
        if module is not None:
            touched = [symbol for symbol in module.symbols
                       if any(symbol.covers(number) for number in added_numbers)]
            seen_symbols: dict[str, Symbol] = {}
            for symbol in touched:
                seen_symbols.setdefault(symbol.qualname, symbol)
            view.symbols = sorted(seen_symbols.values(), key=lambda symbol: symbol.lineno)
        view.removed_defs = _removed_defs(view) if module is not None else []
        view.signature_changes = _signature_changes(view, module)
        change_set.views.append(view)

        # 1) 테스트 파일 자체가 바뀐 경우
        if path in repo.tests or (change.old_path and change.old_path in repo.tests):
            test = repo.test(path) or repo.test(change.old_path)
            add(path if repo.test(path) else change.old_path, 0, "테스트 파일 자체가 바뀜", 100.0)
            if test is not None and test.is_conftest:
                _select_conftest(repo, add, path, change_set)
            continue
        # 2) conftest / 테스트 설정
        if Path(path).name == "conftest.py":
            _select_conftest(repo, add, path, change_set)
            _add_conftest_note(change_set, repo, path)
            continue
        if Path(path).name in TEST_CONFIG_FILES:
            change_set.notes.append(f"{path} 는 테스트 실행 설정 — 전체 실행 판단은 규칙이 한다")
            continue
        # 3) 텍스트가 아닌 변경
        if change.binary:
            change_set.notes.append(f"{path} 는 바이너리 — 테스트 도달 계산에서 뺌")
            continue
        if not change.hunks and change.is_executable_mode_change():
            change_set.notes.append(f"{path} 는 실행 권한만 바뀜")
            continue

        if module is not None and module.parse_error:
            change_set.warnings.append(f"{path} 를 읽지 못함: {module.parse_error}")

        changed_symbol_names = {symbol.name for symbol in view.symbols}
        changed_symbol_names |= set(view.removed_defs)
        direct, symbol_hits = _direct_hits(repo, path, module, changed_symbol_names,
                                           old_path=change.old_path)
        for test_path, reason in sorted(direct.items()):
            add(test_path, 1, reason, 90.0)
        for test_path, reason in sorted(symbol_hits.items()):
            add(test_path, 1, reason, 75.0)

        # 4) 전이 import (바뀐 모듈을 직접 import 하지 않는 테스트)
        targets = {path}
        if change.old_path and change.old_path != path:
            targets.add(change.old_path)
        for target in targets:
            for importer, distance in repo.transitive_importers(target, depth=max(1, depth)).items():
                if importer not in repo.tests:
                    continue
                if importer in direct or importer in symbol_hits:
                    continue
                level = 2 if distance <= 2 else 3
                reason = f"{distance}단계 전이 import (중간 모듈이 바뀐 모듈을 import)"
                add(importer, level, reason, 60.0 - 10 * (distance - 1))

        # 5) 같은 패키지 테스트 — 근거가 아니라 참고
        for test_path in _same_package_tests(repo, path):
            if test_path in change_set.selections:
                continue
            add(test_path, 3, "같은 디렉터리(근거 아님 · 참고)", 10.0)

        # 6) 새 '코드' 파일인데 그 모듈을 참조하는 테스트가 없으면 구멍으로 남긴다
        code_file = module is not None or path.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))
        if change.status == "added" and code_file:
            related = [sel for sel in change_set.selections.values()
                       if repo.test(sel.path) and path in repo.test(sel.path).resolved]
            if not related:
                change_set.gaps.append({
                    "kind": "new-module",
                    "path": path,
                    "detail": "새 모듈을 import 하거나 참조하는 테스트가 없습니다",
                })

    # 선택에서 빠진, 바뀐 모듈 — 구멍 (전이 도달까지 본다)
    for view in change_set.views:
        if not view.module_path or view.module_path in repo.tests:
            continue
        reaching = repo.tests_reaching(view.module_path)
        related = [sel for sel in change_set.selections.values() if sel.path in reaching]
        if related:
            continue
        change_set.gaps.append({
            "kind": "no-test",
            "path": view.change.path,
            "detail": "이 파일을 import 하는 테스트가 없습니다",
        })

    # 공개 심볼 중 아무 테스트도 이름을 대지 않는 것 (테스트 파일 자신은 뺀다)
    for view in change_set.views:
        module = repo.module(view.module_path) if view.module_path else None
        if module is None or repo.is_test(view.module_path):
            continue
        for symbol in view.symbols:
            if not symbol.is_public or symbol.kind not in ("function", "class", "method"):
                continue
            evidence = _symbol_evidence(repo, module, symbol)
            if evidence:
                continue
            change_set.gaps.append({
                "kind": "unreferenced-symbol",
                "path": view.change.path,
                "symbol": symbol.qualname,
                "line": symbol.lineno,
                "detail": f"공개 {symbol.kind} `{symbol.qualname}` 를 이름으로 참조하는 테스트가 없습니다",
            })

    _fallback_triggers(change_set)
    return change_set


def _symbol_evidence(repo: Repo, module, symbol: Symbol) -> list[str]:
    """테스트가 이 심볼을 '이름으로' 대는가 — import·문자열 참조·소스에 나오는 이름."""
    if not symbol.is_public or len(symbol.name) < 4:
        return ["(짧은 이름 — 이름 검사 생략)"]      # `add`, `get` 같은 이름은 우연히 다 나온다
    out: list[str] = []
    for test in repo.tests.values():
        names = test.imported_symbols.get(module.path, set())
        if symbol.name in names or "*" in names:
            out.append(test.path)
            continue
        if f"{module.name}.{symbol.name}" in test.string_refs:
            out.append(test.path)
            continue
        if symbol.name in test.identifiers:
            out.append(test.path)
            continue
        if symbol.name in test.string_refs:
            out.append(test.path)
    return out


def _select_conftest(repo: Repo, add, path: str, change_set: ChangeSet) -> None:
    directory = str(Path(path).parent).replace("\\", "/")
    if directory in ("", "."):
        scoped = [test.path for test in repo.tests.values()]
        reason = "루트 conftest.py 변경 — 전체 테스트"
    else:
        scoped = [test.path for test in repo.tests.values()
                  if test.path.startswith(directory + "/")]
        reason = f"{directory}/ 아래 fixture 변경"
    for test_path in scoped:
        test = repo.test(test_path)
        if test is None or test.is_conftest:
            continue
        add(test_path, 0, reason, 100.0)


def _add_conftest_note(change_set: ChangeSet, repo: Repo, path: str) -> None:
    directory = str(Path(path).parent).replace("\\", "/")
    scope = [test.path for test in repo.tests.values()
             if test.path.startswith(directory + "/")] if directory else list(repo.tests)
    change_set.notes.append(f"conftest.py 변경 → {directory or '루트'} 범위 테스트 {len(scope)}개 파일이 영향권")


def _fallback_triggers(change_set: ChangeSet) -> None:
    repo = change_set.repo
    if not repo.tests:
        change_set.fallback.append("테스트 파일을 하나도 찾지 못했습니다")
    for view in change_set.views:
        module = repo.module(view.module_path) if view.module_path else None
        if module is not None and module.parse_error:
            change_set.fallback.append(f"{view.change.path} 를 파싱하지 못해 그래프가 불완전합니다")
        if module is not None and module.dynamic_import:
            change_set.fallback.append(f"{view.change.path} 에 동적 import 가 있어 정적 그래프로는 다 못 따라갑니다")
    for path in change_set.test_config_touched():
        change_set.fallback.append(f"{path} 는 테스트 실행 방식 자체를 바꿉니다")
    total = repo.total_items()
    if total >= 10 and change_set.selected_items() >= total * 0.6:
        change_set.fallback.append(
            f"선택이 전체의 {change_set.share():.0%} — 줄이는 의미가 없습니다")
