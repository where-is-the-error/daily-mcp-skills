"""규칙 — 잡아야 할 것을 잡고, 잡지 말아야 할 것은 놓아준다."""

from __future__ import annotations

from conftest import migration
from migrate_guard import risks
from migrate_guard.dialect import Severity

SCHEMA = """
CREATE TABLE users (
    id bigint PRIMARY KEY,
    email varchar(255) NOT NULL,
    phone varchar(32),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE orders (
    id bigint PRIMARY KEY,
    user_id bigint NOT NULL,
    total integer NOT NULL
);
CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    legacy_token text
);
"""

BIG = {"users": 1_000_000, "orders": 5_000_000, "sessions": 100}


def ids(sql: str, rows_map: dict | None = None, **kwargs) -> set[str]:
    result = migration(sql, baseline=SCHEMA, rows_map=rows_map if rows_map is not None else BIG, **kwargs)
    return {finding.rule_id for finding in risks.findings(result)}


def only(sql: str, rule_id: str, **kwargs) -> bool:
    return rule_id in ids(sql, **kwargs)


# ------------------------------------------------------------------ 데이터 손실
def test_drop_table() -> None:
    assert "drop-table" in ids("DROP TABLE sessions;")


def test_drop_announced_table_is_cleanup() -> None:
    fired = ids("DROP TABLE _deprecated_sessions;")
    assert "drop-column-cleanup" in fired and "drop-table" not in fired


def test_drop_column() -> None:
    assert "drop-column" in ids("ALTER TABLE sessions DROP COLUMN legacy_token;")


def test_drop_announced_column_is_cleanup() -> None:
    fired = ids("ALTER TABLE sessions DROP COLUMN _deprecated_legacy_token;")
    assert "drop-column-cleanup" in fired and "drop-column" not in fired


def test_drop_old_suffix_is_cleanup() -> None:
    assert "drop-column-cleanup" in ids("ALTER TABLE sessions DROP COLUMN legacy_token_old;")


def test_truncate() -> None:
    assert "truncate" in ids("TRUNCATE sessions;")


def test_delete_without_where() -> None:
    assert "delete-without-where" in ids("DELETE FROM sessions;")


def test_delete_with_where_only_notes_dml() -> None:
    fired = ids("DELETE FROM sessions WHERE id = '00000000-0000-0000-0000-000000000000';")
    assert "delete-without-where" not in fired
    assert "dml-in-migration" in fired


def test_update_without_where() -> None:
    assert "update-without-where" in ids("UPDATE users SET phone = NULL;")


def test_batched_update_does_not_trigger_dml_note() -> None:
    fired = ids("UPDATE users SET phone = NULL WHERE id IN (SELECT id FROM users LIMIT 5000);")
    assert "dml-in-migration" not in fired


# ------------------------------------------------------------------ 컬럼 추가
def test_add_column_not_null_without_default() -> None:
    assert "add-column-not-null-no-default" in ids("ALTER TABLE users ADD COLUMN code text NOT NULL;")


def test_add_column_nullable_no_warning() -> None:
    fired = ids("ALTER TABLE users ADD COLUMN code text;")
    assert "add-column-not-null-no-default" not in fired


def test_empty_table_not_null_is_fine() -> None:
    fired = ids("ALTER TABLE sessions ADD COLUMN code text NOT NULL;", rows_map={"sessions": 0})
    assert "add-column-not-null-no-default" not in fired


def test_volatile_default_rewrite() -> None:
    assert "volatile-default-rewrite" in ids("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")


def test_constant_default_is_not_rewrite() -> None:
    fired = ids("ALTER TABLE users ADD COLUMN active boolean NOT NULL DEFAULT true;")
    assert "volatile-default-rewrite" not in fired


# ------------------------------------------------------------------ 타입
def test_type_rewrite() -> None:
    assert "rewrite-type" in ids("ALTER TABLE orders ALTER COLUMN total TYPE bigint;")


def test_type_narrowing() -> None:
    assert "type-narrowing" in ids("ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);")


def test_widening_varchar_not_flagged() -> None:
    fired = ids("ALTER TABLE users ALTER COLUMN phone TYPE varchar(64);")
    assert "rewrite-type" not in fired and "type-narrowing" not in fired


# ------------------------------------------------------------------ 잠금
def test_long_read_blocking_lock() -> None:
    assert "lock-blocks-reads" in ids("ALTER TABLE orders ALTER COLUMN total TYPE bigint;")


def test_tiny_table_rewrite_is_not_headline() -> None:
    fired = ids("ALTER TABLE sessions ADD COLUMN token text DEFAULT gen_random_uuid();",
                rows_map={"sessions": 10})
    assert "lock-blocks-reads" not in fired


def test_set_not_null_scan() -> None:
    assert "set-not-null-scan" in ids("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;")


def test_set_not_null_with_check_is_quiet() -> None:
    schema = """
    CREATE TABLE users (
        id bigint PRIMARY KEY,
        phone varchar(32),
        CONSTRAINT users_phone_nn CHECK (phone IS NOT NULL) NOT VALID
    );
    """
    result = migration("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;", baseline=schema, rows_map=BIG)
    assert "set-not-null-scan" not in {f.rule_id for f in risks.findings(result)}


def test_create_index_blocks_writes() -> None:
    assert "create-index-blocks-writes" in ids("CREATE INDEX idx ON users (email);")


def test_create_index_concurrently_is_quiet() -> None:
    fired = ids("CREATE INDEX CONCURRENTLY idx ON users (email);")
    assert "create-index-blocks-writes" not in fired


def test_concurrent_inside_transaction() -> None:
    fired = ids("BEGIN; CREATE INDEX CONCURRENTLY idx ON users (email); COMMIT;")
    assert "concurrent-in-transaction" in fired


def test_concurrent_outside_transaction_is_fine() -> None:
    assert "concurrent-in-transaction" not in ids("CREATE INDEX CONCURRENTLY idx ON users (email);")


# ------------------------------------------------------------------ 제약
def test_foreign_key_without_not_valid() -> None:
    assert "fk-without-not-valid" in ids(
        "ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users (id);"
    )


def test_foreign_key_with_not_valid_is_quiet() -> None:
    fired = ids("ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;")
    assert "fk-without-not-valid" not in fired


def test_add_unique_locks() -> None:
    assert "add-unique-locks" in ids("ALTER TABLE users ADD CONSTRAINT u UNIQUE (email);")


def test_check_without_not_valid() -> None:
    assert "check-without-not-valid" in ids("ALTER TABLE users ADD CONSTRAINT c CHECK (id > 0);")


def test_drop_constraint_note() -> None:
    assert "drop-constraint" in ids("ALTER TABLE orders DROP CONSTRAINT orders_user_fk;")


def test_drop_temporary_not_null_check_is_quiet() -> None:
    assert "drop-constraint" not in ids("ALTER TABLE users DROP CONSTRAINT users_phone_not_null;")


# ------------------------------------------------------------------ 이름·인덱스
def test_rename_column() -> None:
    assert "rename-column-breaks-clients" in ids("ALTER TABLE users RENAME COLUMN phone TO phone_number;")


def test_rename_table() -> None:
    assert "rename-table-breaks-clients" in ids("ALTER TABLE users RENAME TO accounts;")


def test_drop_index() -> None:
    assert "drop-index" in ids("DROP INDEX users_email_key;")


# ------------------------------------------------------------------ 파일 단위
def test_locks_held_to_commit() -> None:
    fired = ids("BEGIN; CREATE INDEX i1 ON users (email); CREATE INDEX i2 ON orders (user_id); COMMIT;")
    assert "locks-held-to-commit" in fired


def test_single_statement_transaction_does_not_trigger_hold_note() -> None:
    fired = ids("BEGIN; CREATE INDEX i1 ON users (email); COMMIT;")
    assert "locks-held-to-commit" not in fired


def test_lock_timeout_advice() -> None:
    assert "no-lock-timeout" in ids("CREATE INDEX i1 ON users (email);")


def test_lock_timeout_silences_advice() -> None:
    fired = ids("SET lock_timeout = '3s'; CREATE INDEX i1 ON users (email);")
    assert "no-lock-timeout" not in fired


# ------------------------------------------------------------------ 판정
def test_verdict_critical() -> None:
    result = migration("DROP TABLE sessions;", baseline=SCHEMA)
    assert risks.verdict(risks.findings(result)) == "보류"


def test_verdict_warning() -> None:
    result = migration("CREATE INDEX idx ON users (email);", baseline=SCHEMA, rows_map=BIG)
    assert risks.verdict(risks.findings(result)) == "주의"


def test_verdict_pass() -> None:
    result = migration("SELECT 1;", baseline=SCHEMA)
    assert risks.verdict(risks.findings(result)) == "통과"


def test_findings_sorted_by_severity() -> None:
    result = migration(
        "DROP TABLE sessions; CREATE INDEX idx ON users (email); UPDATE users SET phone = NULL;",
        baseline=SCHEMA, rows_map=BIG,
    )
    severities = [int(f.severity) for f in risks.findings(result)]
    assert severities == sorted(severities)


def test_counts_match_findings() -> None:
    result = migration("DROP TABLE sessions; CREATE INDEX idx ON users (email);", baseline=SCHEMA, rows_map=BIG)
    items = risks.findings(result)
    counts = risks.summary_counts(items)
    assert sum(counts.values()) == len(items)


def test_evidence_has_numbers(big_migration=None) -> None:
    result = migration("UPDATE users SET phone = NULL;", baseline=SCHEMA, rows_map=BIG)
    finding = [f for f in risks.findings(result) if f.rule_id == "update-without-where"][0]
    assert any("1,000,000" in line for line in finding.evidence)


def test_every_rule_has_explanation() -> None:
    for rule in risks.CATALOG:
        assert rule.why and rule.fix and rule.title


def test_rule_ids_are_unique() -> None:
    ids_seen = [rule.rule_id for rule in risks.CATALOG]
    assert len(ids_seen) == len(set(ids_seen))


def test_rule_lookup() -> None:
    assert risks.rule("drop-table").severity is Severity.치명


def test_catalog_size() -> None:
    assert len(risks.CATALOG) >= 20


# ------------------------------------------------------------------ 예제
def test_example_is_blocked(risky) -> None:
    items = risks.findings(risky)
    counts = risks.summary_counts(items)
    assert risks.verdict(items) == "보류"
    assert counts[Severity.치명] >= 3
    assert counts[Severity.심각] >= 5


def test_fixed_example_passes(fixed) -> None:
    items = risks.findings(fixed)
    counts = risks.summary_counts(items)
    assert risks.verdict(items) == "통과"
    assert counts[Severity.치명] == 0
    assert counts[Severity.심각] == 0
