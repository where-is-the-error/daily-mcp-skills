"""PostgreSQL 사실 — 타입 표기, 타입 변경의 결과, 락 모드가 막는 것."""

from __future__ import annotations

import pytest

from migrate_guard.dialect import (
    DEFAULT_RATES,
    LOCKS,
    CostKind,
    Severity,
    TypeChange,
    lock,
    parse_type,
    type_change,
)


# ------------------------------------------------------------------ 타입 표기
def test_parse_varchar_with_length() -> None:
    spec = parse_type("character varying(64)")
    assert spec.base == "varchar"
    assert spec.args == (64,)


def test_parse_varchar_short_form() -> None:
    assert parse_type("varchar(255)").args == (255,)


def test_parse_varchar_without_length() -> None:
    assert parse_type("varchar").args == ()


def test_parse_numeric_precision() -> None:
    spec = parse_type("numeric(12, 2)")
    assert spec.base == "numeric"
    assert spec.args == (12, 2)


def test_parse_numeric_plain() -> None:
    assert parse_type("numeric").args == ()


def test_parse_char() -> None:
    spec = parse_type("character(3)")
    assert spec.base == "char"
    assert spec.args == (3,)


def test_parse_array() -> None:
    spec = parse_type("bigint[]")
    assert spec.base == "bigint"
    assert spec.array is True


def test_parse_array_keyword() -> None:
    assert parse_type("text array").array is True


def test_parse_timestamp_with_time_zone() -> None:
    spec = parse_type("timestamp(3) with time zone")
    assert spec.base.startswith("timestamp")


def test_parse_keeps_raw() -> None:
    assert parse_type("VARCHAR(10)").raw == "VARCHAR(10)"


# ------------------------------------------------------------------ 타입 변경
def same(old: str, new: str) -> TypeChange:
    return type_change(old, new)[0]


def test_same_type_is_same() -> None:
    assert same("integer", "integer") == TypeChange.SAME


def test_int_alias_is_same() -> None:
    assert same("integer", "int4") == TypeChange.SAME


def test_int_widening_rewrites() -> None:
    assert same("integer", "bigint") == TypeChange.REWRITE


def test_int_narrowing_is_risky() -> None:
    assert same("bigint", "integer") == TypeChange.RISKY


def test_varchar_widening_is_metadata() -> None:
    assert same("varchar(32)", "varchar(64)") == TypeChange.METADATA


def test_varchar_to_text_is_metadata() -> None:
    assert same("varchar(32)", "text") == TypeChange.METADATA


def test_text_to_unbounded_varchar_is_metadata() -> None:
    assert same("text", "varchar") == TypeChange.METADATA


def test_varchar_narrowing_is_risky() -> None:
    assert same("varchar(32)", "varchar(16)") == TypeChange.RISKY


def test_text_to_varchar_is_risky() -> None:
    assert same("text", "varchar(64)") == TypeChange.RISKY


def test_char_to_varchar_rewrites() -> None:
    assert same("char(10)", "varchar(10)") == TypeChange.REWRITE


def test_numeric_widening_rewrites() -> None:
    assert same("numeric(10, 2)", "numeric(12, 2)") == TypeChange.REWRITE


def test_numeric_scale_drop_is_risky() -> None:
    assert same("numeric(12, 2)", "numeric(12, 0)") == TypeChange.RISKY


def test_timestamp_to_timestamptz_rewrites() -> None:
    assert same("timestamp", "timestamptz") == TypeChange.REWRITE


def test_array_to_scalar_is_risky() -> None:
    assert same("int[]", "int") == TypeChange.RISKY


def test_boolean_conversion_is_risky() -> None:
    assert same("boolean", "integer") == TypeChange.RISKY


def test_unrelated_types_rewrite() -> None:
    assert same("uuid", "text") == TypeChange.REWRITE


def test_type_change_has_reason() -> None:
    change, why = type_change("varchar(32)", "varchar(16)")
    assert change == TypeChange.RISKY
    assert "varchar(16)" in why


# ------------------------------------------------------------------ 락
def test_access_exclusive_blocks_everything() -> None:
    info = lock("ACCESS EXCLUSIVE")
    assert info.blocks_reads and info.blocks_writes


def test_share_blocks_writes_only() -> None:
    info = lock("SHARE")
    assert info.blocks_writes and not info.blocks_reads


def test_row_exclusive_blocks_nothing() -> None:
    info = lock("ROW EXCLUSIVE")
    assert not info.blocks_writes and not info.blocks_reads


def test_share_update_exclusive_allows_writes() -> None:
    info = lock("SHARE UPDATE EXCLUSIVE")
    assert not info.blocks_writes and not info.blocks_reads


def test_share_row_exclusive_blocks_writes() -> None:
    info = lock("SHARE ROW EXCLUSIVE")
    assert info.blocks_writes and not info.blocks_reads


def test_describe_access_exclusive() -> None:
    assert lock("ACCESS EXCLUSIVE").describe() == "읽기·쓰기 모두 막힘"


def test_describe_share() -> None:
    assert "쓰기" in lock("SHARE").describe()


def test_all_modes_registered() -> None:
    assert set(LOCKS) == {
        "ACCESS SHARE", "ROW SHARE", "ROW EXCLUSIVE", "SHARE UPDATE EXCLUSIVE",
        "SHARE", "SHARE ROW EXCLUSIVE", "EXCLUSIVE", "ACCESS EXCLUSIVE",
    }


# ------------------------------------------------------------------ 기타
def test_severity_order() -> None:
    assert Severity.치명 < Severity.심각 < Severity.보통 < Severity.참고


def test_rates_cover_every_cost_kind() -> None:
    for kind in CostKind:
        if kind is CostKind.NONE:
            continue
        assert kind in DEFAULT_RATES


def test_unknown_lock_raises() -> None:
    with pytest.raises(KeyError):
        lock("NOPE")
