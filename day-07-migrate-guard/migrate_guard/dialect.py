"""PostgreSQL 의 사실만 모아 둔 곳 — 타입 크기, 락 모드, 재작성 여부, 처리 속도 가정.

여기 값들은 "내가 아는 PostgreSQL" 이 아니라 PostgreSQL 문서에 적힌 동작이다.
바뀌면 이 파일만 고치면 된다. 숫자(행/초)는 **모델 가정**이며 실측이 아니다 —
그 사실을 결과 화면에도 적는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "Severity",
    "SEVERITY_ORDER",
    "LockInfo",
    "LOCKS",
    "Cost",
    "CostKind",
    "TypeSpec",
    "parse_type",
    "type_change",
    "TypeChange",
    "DEFAULT_RATES",
]


class Severity(IntEnum):
    """숫자가 작을수록 무겁다 — 게이트 비교를 단순하게 만든다."""

    치명 = 0
    심각 = 1
    보통 = 2
    참고 = 3

    @property
    def label(self) -> str:
        return self.name


SEVERITY_ORDER = {s.name: int(s) for s in Severity}


# --------------------------------------------------------------------- 락
@dataclass(frozen=True)
class LockInfo:
    mode: str
    blocks_reads: bool     # 일반 SELECT 까지 막는가
    blocks_writes: bool    # INSERT/UPDATE/DELETE 를 막는가
    self_conflict: bool    # 같은 DDL 끼리 줄 서는가

    def describe(self) -> str:
        if self.blocks_reads:
            return "읽기·쓰기 모두 막힘"
        if self.blocks_writes:
            return "쓰기 막힘 (읽기는 통과)"
        if self.self_conflict:
            return "쓰기는 통과, 같은 DDL 은 줄 섬"
        return "경합 없음"


LOCKS: dict[str, LockInfo] = {
    "ACCESS SHARE": LockInfo("ACCESS SHARE", False, False, False),
    "ROW SHARE": LockInfo("ROW SHARE", False, False, False),
    "ROW EXCLUSIVE": LockInfo("ROW EXCLUSIVE", False, False, True),
    "SHARE UPDATE EXCLUSIVE": LockInfo("SHARE UPDATE EXCLUSIVE", False, False, True),
    # SHARE 는 ROW EXCLUSIVE 와 충돌한다 → 쓰기 차단, ACCESS SHARE 는 통과 → 읽기 허용
    "SHARE": LockInfo("SHARE", False, True, True),
    "SHARE ROW EXCLUSIVE": LockInfo("SHARE ROW EXCLUSIVE", False, True, True),
    "EXCLUSIVE": LockInfo("EXCLUSIVE", False, True, True),
    "ACCESS EXCLUSIVE": LockInfo("ACCESS EXCLUSIVE", True, True, True),
}


def lock(mode: str) -> LockInfo:
    return LOCKS[mode]


# --------------------------------------------------------------------- 비용 종류
class CostKind(IntEnum):
    """무엇을 하느라 시간이 드는가 — 추정식이 종류별로 다르다."""

    NONE = 0        # 메타데이터만
    SCAN = 1        # 테이블을 한 번 읽는다 (검증·스캔)
    REWRITE = 2     # 새 파일로 통째로 다시 쓴다
    INDEX = 3       # 인덱스를 만든다
    WRITE = 4       # 행을 갱신·삭제한다


@dataclass(frozen=True)
class Cost:
    kind: CostKind
    rows: int = 0
    note: str = ""

    @property
    def needs_rows(self) -> bool:
        return self.kind is not CostKind.NONE


# 처리 속도 가정 (rows/sec). 실측이 아니라 모델이다 — 결과에 그렇게 적는다.
DEFAULT_RATES: dict[CostKind, float] = {
    CostKind.SCAN: 250_000.0,
    CostKind.REWRITE: 60_000.0,
    CostKind.INDEX: 90_000.0,
    CostKind.WRITE: 120_000.0,
}

# DDL 한 문장이 잡는 고정 오버헤드(락 획득·카탈로그 갱신).
FIXED_SECONDS = 0.02


# --------------------------------------------------------------------- 타입
_INT_BITS = {
    "smallint": 16, "int2": 16,
    "integer": 32, "int": 32, "int4": 32,
    "bigint": 64, "int8": 64,
}

_NUMERIC = re.compile(r"(?:numeric|decimal)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?", re.I)
_VARCHAR = re.compile(r"(?:character varying|varchar)\s*(?:\(\s*(\d+)\s*\))?", re.I)
_CHAR = re.compile(r"(?:character|char)\s*(?:\(\s*(\d+)\s*\))?", re.I)

_TEXT_FAMILY = {"text", "varchar", "character varying", "char", "character", "bpchar", "citext"}


@dataclass(frozen=True)
class TypeSpec:
    raw: str
    base: str            # 정규화된 기본 이름 (varchar, numeric, int8 …)
    args: tuple[int, ...] = ()
    array: bool = False

    def __str__(self) -> str:   # pragma: no cover - 표시용
        return self.raw


def parse_type(text: str) -> TypeSpec:
    """`character varying(64)[]` 같은 표기를 이름·인자·배열로 나눈다."""
    raw = re.sub(r"\s+", " ", text.strip()).strip()
    array = raw.endswith("[]") or " array" in raw.lower()
    core = raw
    if array:
        core = re.sub(r"(\[\s*\])+$", "", core)
        core = re.sub(r"\s+array$", "", core, flags=re.I)
    lower = core.lower().strip()

    if lower in _INT_BITS:
        return TypeSpec(raw, lower, (), array)
    match = _NUMERIC.fullmatch(lower)
    if match:
        args = tuple(int(g) for g in match.groups() if g is not None)
        return TypeSpec(raw, "numeric", args, array)
    match = _VARCHAR.fullmatch(lower)
    if match:
        args = (int(match.group(1)),) if match.group(1) else ()
        return TypeSpec(raw, "varchar", args, array)
    match = _CHAR.fullmatch(lower)
    if match:
        args = (int(match.group(1)),) if match.group(1) else ()
        return TypeSpec(raw, "char", args, array)

    base = re.sub(r"\(.*?\)", "", lower).strip()
    base = re.sub(r"\s+", " ", base)
    return TypeSpec(raw, base, (), array)


class TypeChange(IntEnum):
    """타입을 바꿀 때 무엇이 일어나는가."""

    SAME = 0        # 메타데이터만
    METADATA = 1    # 재작성 없이 카탈로그만 바뀐다 (varchar 확장·text 전환)
    REWRITE = 2     # 테이블을 통째로 다시 쓴다
    RISKY = 3       # 재작성 + 값이 깨지거나 실패할 수 있다


def type_change(old: str, new: str) -> tuple[TypeChange, str]:
    """(무엇이 일어나는가, 왜) — PostgreSQL 의 binary-coercible 규칙을 따른다."""
    a, b = parse_type(old), parse_type(new)
    if a.base == b.base and a.args == b.args and a.array == b.array:
        return TypeChange.SAME, "같은 타입"
    if a.array != b.array:
        return TypeChange.RISKY, "배열 ↔ 단일 값은 값 해석이 바뀐다"

    if a.base in _INT_BITS and b.base in _INT_BITS:
        if _INT_BITS[b.base] > _INT_BITS[a.base]:
            return TypeChange.REWRITE, f"{a.base} → {b.base} 는 재작성(값 손실 없음)"
        if _INT_BITS[b.base] < _INT_BITS[a.base]:
            return TypeChange.RISKY, f"{a.base} → {b.base} 는 재작성 + 범위 초과 시 실패"
        return TypeChange.SAME, "같은 폭"

    if a.base == "numeric" and b.base == "numeric":
        pa, sa = (a.args + (0, 0))[:2]
        pb, sb = (b.args + (0, 0))[:2]
        if pb >= pa and sb >= sa:
            return TypeChange.REWRITE, "numeric 은 정밀도를 늘려도 재작성"
        return TypeChange.RISKY, "정밀도·스케일 축소는 재작성 + 반올림·실패"

    if a.base in _TEXT_FAMILY and b.base in _TEXT_FAMILY:
        if a.base in {"char", "character", "bpchar"} and b.base != a.base:
            return TypeChange.REWRITE, "char(n) 의 뒤 공백 채우기 때문에 재작성이 필요하다"
        if b.base in {"text"}:
            return TypeChange.METADATA, "varchar → text 는 재작성 없음"
        if b.base in {"varchar", "character varying"}:
            old_n = a.args[0] if a.args else None
            new_n = b.args[0] if b.args else None
            if new_n is None:
                return TypeChange.METADATA, "길이 제한 없는 varchar 는 재작성 없음"
            if old_n is None:
                return TypeChange.RISKY, f"text → varchar({new_n}) 는 재작성 + 길이 초과 시 실패"
            if new_n >= old_n:
                return TypeChange.METADATA, f"varchar({old_n}) → varchar({new_n}) 는 재작성 없음"
            return TypeChange.RISKY, f"varchar({old_n}) → varchar({new_n}) 는 재작성 + 잘림·실패"
        if b.base in {"char", "character", "bpchar"}:
            return TypeChange.REWRITE, "char(n) 은 뒤 공백 채우기 때문에 재작성"
        return TypeChange.REWRITE, "문자 타입 사이 변환은 재작성"

    if {a.base, b.base} == {"timestamp", "timestamptz"}:
        return TypeChange.REWRITE, "timestamp ↔ timestamptz 는 시간대 해석이 바뀐다"
    if a.base == "boolean" or b.base == "boolean":
        return TypeChange.RISKY, "boolean 변환은 값에 따라 실패"
    return TypeChange.REWRITE, f"{a.base} → {b.base} 는 테이블 재작성"
