"""되돌리기 — 역순으로, 되돌릴 수 없는 것은 그렇게 표시."""

from __future__ import annotations

from conftest import migration
from migrate_guard.rollback import irreversible_ops, rollback, rollback_sql

SCHEMA = """
CREATE TABLE users (
    id bigint PRIMARY KEY,
    email varchar(255) NOT NULL,
    phone varchar(32)
);
CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    legacy_token text
);
"""


def steps(sql: str):
    result = migration(sql, baseline=SCHEMA, rows_map={"users": 1000})
    return rollback(result)


def test_reverse_order() -> None:
    result = steps("ALTER TABLE users ADD COLUMN a int; ALTER TABLE users ADD COLUMN b int;")
    assert [step.ref for step in result] == ["s2", "s1"]


def test_add_column_inverse_is_drop() -> None:
    step = steps("ALTER TABLE users ADD COLUMN a int;")[0]
    assert step.sql == "ALTER TABLE users DROP COLUMN IF EXISTS a"
    assert step.reversible is True


def test_drop_table_has_no_sql() -> None:
    step = steps("DROP TABLE sessions;")[0]
    assert step.sql is None
    assert step.reversible is False
    assert "백업" in step.reason


def test_drop_column_restores_schema_only() -> None:
    step = steps("ALTER TABLE users DROP COLUMN phone;")[0]
    assert step.sql == "ALTER TABLE users ADD COLUMN phone varchar(32)"
    assert step.reversible is False
    assert "값은 복구되지 않는다" in step.reason


def test_drop_column_keeps_constraints_in_definition() -> None:
    step = steps("ALTER TABLE users DROP COLUMN email;")[0]
    assert "NOT NULL" in step.sql


def test_create_index_inverse_drops_concurrently() -> None:
    step = steps("CREATE INDEX idx ON users (phone);")[0]
    assert step.sql == "DROP INDEX CONCURRENTLY IF EXISTS idx"


def test_add_constraint_inverse() -> None:
    step = steps("ALTER TABLE users ADD CONSTRAINT c CHECK (id > 0) NOT VALID;")[0]
    assert step.sql == "ALTER TABLE users DROP CONSTRAINT IF EXISTS c"


def test_set_not_null_inverse() -> None:
    step = steps("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;")[0]
    assert step.sql == "ALTER TABLE users ALTER COLUMN phone DROP NOT NULL"


def test_alter_type_inverse_uses_previous_type() -> None:
    step = steps("ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);")[0]
    assert step.sql == "ALTER TABLE users ALTER COLUMN phone TYPE varchar(32)"
    assert step.reversible is False


def test_alter_type_metadata_is_reversible() -> None:
    step = steps("ALTER TABLE users ALTER COLUMN phone TYPE varchar(64);")[0]
    assert step.reversible is True


def test_rename_column_inverse() -> None:
    step = steps("ALTER TABLE users RENAME COLUMN phone TO phone_number;")[0]
    assert step.sql == "ALTER TABLE users RENAME COLUMN phone TO phone_number"


def test_update_has_no_inverse() -> None:
    step = steps("UPDATE users SET phone = NULL;")[0]
    assert step.sql is None and step.reversible is False


def test_delete_has_no_inverse() -> None:
    step = steps("DELETE FROM users;")[0]
    assert step.sql is None


def test_truncate_has_no_inverse() -> None:
    step = steps("TRUNCATE users;")[0]
    assert step.sql is None


def test_create_table_inverse_drops() -> None:
    step = steps("CREATE TABLE t (id bigint);")[0]
    assert step.sql == "DROP TABLE IF EXISTS t"


def test_transaction_statements_are_skipped() -> None:
    result = steps("BEGIN; ALTER TABLE users ADD COLUMN a int; COMMIT;")
    assert [step.ref for step in result] == ["s2"]


def test_irreversible_ops_listed() -> None:
    result = migration("DROP TABLE sessions; UPDATE users SET phone = NULL;", baseline=SCHEMA)
    assert len(irreversible_ops(result)) == 2


def test_rollback_sql_has_header_and_steps() -> None:
    text = rollback_sql(migration("ALTER TABLE users ADD COLUMN a int;", baseline=SCHEMA))
    assert "되돌리기 SQL" in text
    assert "ALTER TABLE users DROP COLUMN IF EXISTS a;" in text


def test_rollback_sql_marks_data_loss() -> None:
    text = rollback_sql(migration("DROP TABLE sessions;", baseline=SCHEMA))
    assert "값이 사라진 문장" in text
    assert "⚠️" in text


def test_rollback_sql_counts_steps() -> None:
    text = rollback_sql(migration("ALTER TABLE users ADD COLUMN a int; ALTER TABLE users ADD COLUMN b int;",
                                  baseline=SCHEMA))
    assert "되돌리기 단계 2개" in text


def test_drop_index_cannot_be_restored() -> None:
    step = steps("DROP INDEX users_email_key;")[0]
    assert step.sql is None
    assert step.reversible is False
