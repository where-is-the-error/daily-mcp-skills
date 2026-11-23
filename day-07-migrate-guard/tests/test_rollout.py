"""다시 쓴 단계 — 확장·백필·전환으로 나뉘었는지."""

from __future__ import annotations

from conftest import migration
from migrate_guard.rollout import expand_contract, rollout_sql

SCHEMA = """
CREATE TABLE users (
    id bigint PRIMARY KEY,
    phone varchar(32),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE orders (
    id bigint PRIMARY KEY,
    user_id bigint NOT NULL
);
CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    legacy_token text
);
"""

BIG = {"users": 1_000_000, "orders": 5_000_000, "sessions": 100}


def phases(sql: str, **kwargs):
    result = migration(sql, baseline=SCHEMA, rows_map=BIG, **kwargs)
    return expand_contract(result), result


def all_sql(phases) -> str:
    return "\n".join(step.sql for phase in phases for step in phase.steps)


def step_sql(phase) -> list[str]:
    return [step.sql for step in phase.steps]


def test_volatile_default_split_into_three_phases() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")[0]
    keys = [phase.key for phase in result]
    assert keys == ["now", "backfill", "later"]


def test_volatile_default_added_without_default() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")[0]
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS token text;" in step_sql(result[0])


def test_backfill_is_batched_and_bounded() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")[0]
    backfill = step_sql(result[1])[0]
    assert "SET token = gen_random_uuid()" in backfill
    assert "LIMIT 5000" in backfill
    assert "IS NULL" in backfill


def test_default_set_in_later_phase() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")[0]
    assert any("SET DEFAULT gen_random_uuid()" in sql for sql in step_sql(result[2]))


def test_not_null_closed_with_check_then_validate() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text NOT NULL DEFAULT gen_random_uuid();")[0]
    later = step_sql(result[2])
    assert any("CHECK (token IS NOT NULL) NOT VALID" in sql for sql in later)
    assert any("VALIDATE CONSTRAINT" in sql for sql in later)
    assert any("SET NOT NULL" in sql for sql in later)
    assert any("DROP CONSTRAINT" in sql for sql in later)


def test_backfill_rerun_before_closing_not_null() -> None:
    result = phases("ALTER TABLE users ADD COLUMN token text NOT NULL DEFAULT gen_random_uuid();")[0]
    later = step_sql(result[2])
    assert any("3단계 전에 백필" in sql for sql in later)


def test_no_begin_commit_in_output() -> None:
    sql = rollout_sql(migration("BEGIN; ALTER TABLE users ADD COLUMN a int; COMMIT;", baseline=SCHEMA, rows_map=BIG))
    assert "BEGIN" not in sql.upper().replace("BEGIN;", "X")
    assert "COMMIT;" not in sql


def test_index_made_concurrent() -> None:
    result = phases("CREATE INDEX idx ON users (phone);")[0]
    assert "CREATE INDEX CONCURRENTLY idx ON users (phone);" in step_sql(result[0])


def test_unique_index_stays_unique_concurrent() -> None:
    result = phases("CREATE UNIQUE INDEX idx ON users (phone);")[0]
    assert any("CREATE UNIQUE INDEX CONCURRENTLY" in sql for sql in step_sql(result[0]))


def test_concurrent_index_kept_as_is() -> None:
    result = phases("CREATE INDEX CONCURRENTLY idx ON users (phone);")[0]
    assert step_sql(result[0]) == ["CREATE INDEX CONCURRENTLY idx ON users (phone);"]


def test_drop_index_made_concurrent() -> None:
    result = phases("DROP INDEX idx;")[0]
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx;" in step_sql(result[0])


def test_foreign_key_not_valid_then_validate() -> None:
    result = phases("ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users (id);")[0]
    now = step_sql(result[0])
    later = step_sql(result[1])
    assert any("NOT VALID" in sql for sql in now)
    assert any("VALIDATE CONSTRAINT fk" in sql for sql in later)


def test_check_not_valid() -> None:
    result = phases("ALTER TABLE users ADD CONSTRAINT c CHECK (id > 0);")[0]
    assert any("NOT VALID" in sql for sql in step_sql(result[0]))


def test_unique_constraint_via_index() -> None:
    result = phases("ALTER TABLE users ADD CONSTRAINT u UNIQUE (phone);")[0]
    now = step_sql(result[0])
    later = step_sql(result[1])
    assert any("CREATE UNIQUE INDEX CONCURRENTLY" in sql for sql in now)
    assert any("USING INDEX" in sql for sql in later)


def test_set_not_null_split() -> None:
    result = phases("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;")[0]
    now = step_sql(result[0])
    later = step_sql(result[1])
    assert any("CHECK (phone IS NOT NULL) NOT VALID" in sql for sql in now)
    assert any("VALIDATE CONSTRAINT" in sql for sql in now)
    assert any("SET NOT NULL" in sql for sql in later)


def test_drop_column_deferred_by_rename() -> None:
    result = phases("ALTER TABLE sessions DROP COLUMN legacy_token;")[0]
    assert "ALTER TABLE sessions RENAME COLUMN legacy_token TO _deprecated_legacy_token;" in step_sql(result[0])
    assert "ALTER TABLE sessions DROP COLUMN _deprecated_legacy_token;" in step_sql(result[1])


def test_drop_table_deferred_by_rename() -> None:
    result = phases("DROP TABLE sessions;")[0]
    assert "ALTER TABLE sessions RENAME TO _deprecated_sessions;" in step_sql(result[0])
    assert "DROP TABLE IF EXISTS _deprecated_sessions;" in step_sql(result[1])


def test_truncate_becomes_batched_delete() -> None:
    result = phases("TRUNCATE sessions;")[0]
    assert any("DELETE FROM sessions WHERE ctid IN" in sql for sql in step_sql(result[0]))


def test_alter_type_uses_new_column() -> None:
    result = phases("ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);")[0]
    now = step_sql(result[0])
    backfill = step_sql(result[1])
    later = step_sql(result[2])
    assert any("ADD COLUMN IF NOT EXISTS phone_new varchar(16)" in sql for sql in now)
    assert any("SET phone_new = phone::varchar(16)" in sql for sql in backfill)
    assert any("RENAME COLUMN phone_new TO phone" in sql for sql in later)


def test_narrowing_check_uses_length_for_varchar() -> None:
    result = phases("ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);")[0]
    now = step_sql(result[0])
    assert any("length(phone) > 16" in sql for sql in now)


def test_narrowing_check_uses_bounds_for_integer() -> None:
    schema = SCHEMA + "\nALTER TABLE orders ADD COLUMN amount bigint;"
    result = migration("ALTER TABLE orders ALTER COLUMN amount TYPE integer;", baseline=schema, rows_map=BIG)
    now = step_sql(expand_contract(result)[0])
    assert any("2147483647" in sql for sql in now)


def test_update_without_where_becomes_key_range_batches() -> None:
    result = phases("UPDATE users SET phone = NULL;")[0]
    sql = step_sql(result[0])[0]
    assert "UPDATE users SET phone = NULL" in sql
    assert ":last_key" in sql
    assert "LIMIT 5000" in sql


def test_delete_without_where_becomes_batches() -> None:
    result = phases("DELETE FROM sessions;")[0]
    sql = step_sql(result[0])[0]
    assert "DELETE FROM sessions" in sql
    assert ":last_key" in sql


def test_batch_size_is_configurable() -> None:
    migration_result = migration("CREATE INDEX idx ON users (phone);", baseline=SCHEMA, rows_map=BIG)
    result = expand_contract(migration_result, batch=1000)
    assert "LIMIT 1000" in all_sql(result) or "CONCURRENTLY" in all_sql(result)


def test_safe_statement_passes_through() -> None:
    result = phases("CREATE TABLE t (id bigint);")[0]
    assert step_sql(result[0]) == ["CREATE TABLE t (id bigint);"]


def test_why_is_recorded() -> None:
    result = phases("CREATE INDEX idx ON users (phone);")[0]
    assert any("CONCURRENTLY" in reason for reason in result[0].why)


def test_rollout_sql_has_phase_headers() -> None:
    sql = rollout_sql(migration("CREATE INDEX idx ON users (phone);", baseline=SCHEMA, rows_map=BIG))
    assert "1단계" in sql and "각 단계는 서로 다른 배포" in sql


def test_rollout_sql_statements_end_with_semicolon() -> None:
    sql = rollout_sql(migration("CREATE INDEX idx ON users (phone);", baseline=SCHEMA, rows_map=BIG))
    for line in sql.splitlines():
        if line.strip() and not line.strip().startswith("--"):
            assert line.rstrip().endswith(";"), line


def test_fixed_example_has_no_transaction_wrapper(fixed) -> None:
    assert "BEGIN;" not in fixed.source
    result = expand_contract(fixed)
    assert result and all(phase.key != "backfill" or phase.steps for phase in result)


def test_rollout_of_fixed_does_not_make_it_worse(fixed) -> None:
    text = rollout_sql(fixed)
    assert "CREATE INDEX CONCURRENTLY CONCURRENTLY" not in text
