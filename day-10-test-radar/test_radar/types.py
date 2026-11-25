"""test-radar 의 자료형.

모든 값은 '읽은 그대로'를 담는다. 판정은 다른 모듈이 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


# --------------------------------------------------------------------- diff
@dataclass(frozen=True)
class Hunk:
    """unified diff 의 @@ 한 덩어리."""

    old_start: int
    old_len: int
    new_start: int
    new_len: int
    section: str = ""
    lines: tuple[str, ...] = ()          # 접두사(' ', '+', '-') 를 포함한 원문

    def added(self) -> list[tuple[int, str]]:
        """(새 파일 줄번호, 내용) — '+' 줄만. 새 줄번호는 1부터."""
        out: list[tuple[int, str]] = []
        number = self.new_start
        for line in self.lines:
            if not line:
                continue
            head, body = line[0], line[1:]
            if head == "+":
                out.append((number, body))
                number += 1
            elif head == " ":
                number += 1
            elif head == "\\":
                continue
        return out

    def removed(self) -> list[tuple[int, str]]:
        """(옛 파일 줄번호, 내용) — '-' 줄만."""
        out: list[tuple[int, str]] = []
        number = self.old_start
        for line in self.lines:
            if not line:
                continue
            head, body = line[0], line[1:]
            if head == "-":
                out.append((number, body))
                number += 1
            elif head == " ":
                number += 1
        return out

    def context(self) -> list[tuple[str, str]]:
        """(' '|'+'|'-', 내용) 순서 보존 목록."""
        out: list[tuple[str, str]] = []
        for line in self.lines:
            if not line:
                continue
            head, body = line[0], line[1:]
            if head == "\\":
                continue
            if head not in (" ", "+", "-"):
                body = line
                head = " "
            out.append((head, body))
        return out


@dataclass
class FileChange:
    path: str
    old_path: str = ""
    status: str = "modified"             # added | modified | deleted | renamed
    hunks: list[Hunk] = field(default_factory=list)
    binary: bool = False
    old_mode: str = ""
    new_mode: str = ""
    similarity: int | None = None

    @property
    def before_path(self) -> str:
        return self.old_path or self.path

    def added_lines(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for hunk in self.hunks:
            out.extend(hunk.added())
        return out

    def removed_lines(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for hunk in self.hunks:
            out.extend(hunk.removed())
        return out

    def added_count(self) -> int:
        return len(self.added_lines())

    def removed_count(self) -> int:
        return len(self.removed_lines())

    def added_text(self) -> str:
        return "\n".join(text for _, text in self.added_lines())

    def removed_text(self) -> str:
        return "\n".join(text for _, text in self.removed_lines())

    def is_executable_mode_change(self) -> bool:
        return bool(self.old_mode and self.new_mode and self.old_mode != self.new_mode
                    and not self.hunks)


@dataclass
class Diff:
    changes: list[FileChange] = field(default_factory=list)

    def by_path(self, path: str) -> FileChange | None:
        for change in self.changes:
            if change.path == path or change.old_path == path:
                return change
        return None

    def paths(self) -> list[str]:
        return [change.path for change in self.changes]


# ------------------------------------------------------------------- module
@dataclass(frozen=True)
class Symbol:
    name: str
    qualname: str
    kind: str                            # function | class | method | constant
    lineno: int
    end_lineno: int
    signature: str = ""
    decorators: tuple[str, ...] = ()
    is_public: bool = True
    parent: str = ""
    params: tuple[str, ...] = ()

    def covers(self, line: int) -> bool:
        return self.lineno <= line <= self.end_lineno


@dataclass(frozen=True)
class ImportRef:
    module: str                          # 해석 전 이름 (상대 import 는 점 포함)
    names: tuple[str, ...] = ()
    lineno: int = 0
    level: int = 0
    is_star: bool = False


@dataclass
class Module:
    path: str                            # 저장소 루트 기준 posix 경로
    name: str                            # 점으로 이은 모듈 이름
    language: str = "python"             # python | javascript
    imports: list[ImportRef] = field(default_factory=list)
    resolved: set[str] = field(default_factory=set)   # import 한 파일 경로
    imported_symbols: dict[str, set[str]] = field(default_factory=dict)  # path -> names
    symbols: list[Symbol] = field(default_factory=list)
    strings: set[str] = field(default_factory=set)
    exports: tuple[str, ...] = ()
    is_package: bool = False
    parse_error: str = ""
    dynamic_import: bool = False
    source: str = ""
    lines: int = 0
    top_level_lines: set[int] = field(default_factory=set)

    def symbol(self, name: str) -> Symbol | None:
        for symbol in self.symbols:
            if symbol.name == name or symbol.qualname == name or symbol.qualname.endswith("." + name):
                return symbol
        return None

    def symbol_at(self, line: int) -> Symbol | None:
        """그 줄을 감싸는 가장 안쪽 심볼."""
        best = None
        for symbol in self.symbols:
            if symbol.covers(line):
                if best is None or symbol.lineno >= best.lineno:
                    best = symbol
        return best


@dataclass(frozen=True)
class TestItem:
    path: str
    name: str                            # test_foo 또는 TestClass::test_bar
    lineno: int = 0
    skip: bool = False
    xfail: bool = False
    parametrized: bool = False


@dataclass
class TestFile:
    path: str
    language: str = "python"
    items: list[TestItem] = field(default_factory=list)
    resolved: set[str] = field(default_factory=set)
    imported_symbols: dict[str, set[str]] = field(default_factory=dict)
    string_refs: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)   # 소스에 나오는 이름(메서드 호출 등)
    is_conftest: bool = False
    parse_error: str = ""

    def weight(self) -> int:
        return max(1, len(self.items))


# ------------------------------------------------------------------ result
@dataclass
class Selection:
    path: str
    level: int                           # 0 테스트 자체 | 1 직접 | 2 전이 | 3 같은 패키지
    reason: str
    score: float = 0.0
    items: int = 0

    @property
    def mandatory(self) -> bool:
        return self.level <= 2


@dataclass
class Risk:
    rule: str
    severity: str                        # 치명 | 심각 | 주의 | 참고
    title: str
    detail: str
    where: str = ""


@dataclass
class Plan:
    commands: list[dict]                 # label, command, tests, weight, note
    fallback: dict
    assumed: dict = field(default_factory=dict)


def posix(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
