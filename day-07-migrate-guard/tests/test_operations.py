"""문장 분류 — 종류·락·비용·되돌릴 수 있는지."""

from __future__ import annotations

from conftest import migration
from migrate_guard.dialect import CostKind, FIXED_SECONDS
from migrate_guard.operations import analyze, estimate_seconds

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
"""

ROWS = {"users": 1_000_000, "orders": 5_000_000}


def op(sql: str, **kwargs):
    result = migration(sql, baseline=SCHEMA, rows_map=ROWS, **kwargs)
    return result.ops[0], result


def test_create_table_does_not_contend() -> None:
    operation, _ = op("CREATE TABLE t (id bigint);")
    assert operation.kind == "create_table"
    assert operation.contends is False


def test_add_column_constant_default_is_metadata_only() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN active boolean NOT NULL DEFAULT true;")
    assert operation.kind == "add_column"
    assert operation.metadata_only is True
    assert operation.lock_mode == "ACCESS EXCLUSIVE"


def test_add_column_volatile_default_rewrites() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN token text DEFAULT gen_random_uuid();")
    assert operation.metadata_only is False
    assert operation.cost.kind is CostKind.REWRITE
    assert operation.cost.rows == 1_000_000


def test_now_is_stable_not_volatile() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN seen timestamptz DEFAULT now();")
    assert operation.metadata_only is True


def test_random_default_is_volatile() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN token text DEFAULT md5(random()::text);")
    assert operation.detail["volatile_default"] is True


def test_pg10_default_rewrites() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN n integer DEFAULT 0;", pg_version=10)
    assert operation.metadata_only is False
    assert "11 미만" in operation.cost.note


def test_add_column_not_null_without_default_flagged_in_detail() -> None:
    operation, _ = op("ALTER TABLE users ADD COLUMN code text NOT NULL;")
    assert operation.detail["nullable"] is False
    assert operation.detail["default"] is None


def test_add_column_with_references_notes_lock() -> None:
    operation, _ = op("ALTER TABLE orders ADD COLUMN uid bigint REFERENCES users (id);")
    assert operation.detail["references"] == "users"
    assert "참조 테이블" in operation.note


def test_drop_column_is_irreversible() -> None:
    operation, _ = op("ALTER TABLE users DROP COLUMN phone;")
    assert operation.kind == "drop_column"
    assert operation.irreversible is True
    assert operation.metadata_only is True


def test_alter_type_uses_baseline() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);")
    assert operation.kind == "alter_type"
    assert operation.detail["from"] == "varchar(32)"
    assert operation.detail["to"] == "varchar(16)"
    assert operation.detail["change"] == "RISKY"


def test_alter_type_widening_text_is_metadata() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN phone TYPE text;")
    assert operation.metadata_only is True


def test_alter_type_with_using_always_rewrites() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN phone TYPE varchar(32) USING trim(phone);")
    assert operation.metadata_only is False
    assert operation.cost.kind is CostKind.REWRITE


def test_alter_type_without_baseline_assumes_rewrite() -> None:
    result = migration("ALTER TABLE unknown_table ALTER COLUMN a TYPE bigint;")
    operation = result.ops[0]
    assert operation.kind == "alter_type"
    assert "모른다" in operation.detail["why"]


def test_set_not_null_scans_without_check() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;")
    assert operation.kind == "set_not_null"
    assert operation.cost.kind is CostKind.SCAN
    assert operation.detail["check"] is False


def test_set_not_null_skips_scan_with_valid_check() -> None:
    schema = """
    CREATE TABLE users (
        id bigint PRIMARY KEY,
        phone varchar(32),
        CONSTRAINT users_phone_nn CHECK (phone IS NOT NULL) NOT VALID
    );
    """
    result = migration("ALTER TABLE users ALTER COLUMN phone SET NOT NULL;", baseline=schema, rows_map=ROWS)
    operation = result.ops[0]
    assert operation.detail["check"] is True
    assert operation.metadata_only is True


def test_drop_not_null_is_metadata() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN email DROP NOT NULL;")
    assert operation.kind == "drop_not_null"
    assert operation.metadata_only is True


def test_set_default_is_metadata() -> None:
    operation, _ = op("ALTER TABLE users ALTER COLUMN phone SET DEFAULT 'x';")
    assert operation.kind == "column_default"


def test_rename_column() -> None:
    operation, _ = op("ALTER TABLE users RENAME COLUMN phone TO phone_number;")
    assert operation.kind == "rename_column"
    assert operation.detail["to"] == "phone_number"


def test_rename_table() -> None:
    operation, _ = op("ALTER TABLE users RENAME TO accounts;")
    assert operation.kind == "rename_table"
    assert operation.detail["to"] == "accounts"


def test_add_check_not_valid_does_not_scan() -> None:
    operation, _ = op("ALTER TABLE users ADD CONSTRAINT c CHECK (id > 0) NOT VALID;")
    assert operation.kind == "add_check"
    assert operation.lock_mode == "SHARE ROW EXCLUSIVE"
    assert operation.metadata_only is True


def test_add_check_valid_scans() -> None:
    operation, _ = op("ALTER TABLE users ADD CONSTRAINT c CHECK (id > 0);")
    assert operation.cost.kind is CostKind.SCAN


def test_add_foreign_key_not_valid() -> None:
    operation, _ = op("ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;")
    assert operation.kind == "add_foreign_key"
    assert operation.detail["not_valid"] is True
    assert operation.metadata_only is True


def test_add_foreign_key_scans_orders() -> None:
    operation, _ = op("ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users (id);")
    assert operation.cost.rows == 5_000_000


def test_add_unique_builds_index() -> None:
    operation, _ = op("ALTER TABLE users ADD CONSTRAINT u UNIQUE (email);")
    assert operation.kind == "add_unique"
    assert operation.cost.kind is CostKind.INDEX


def test_add_primary_key() -> None:
    operation, _ = op("ALTER TABLE orders ADD CONSTRAINT pk PRIMARY KEY (id);")
    assert operation.kind == "add_primary_key"
    assert operation.cost.kind is CostKind.INDEX


def test_validate_constraint_mode() -> None:
    operation, _ = op("ALTER TABLE orders VALIDATE CONSTRAINT fk;")
    assert operation.kind == "validate_constraint"
    assert operation.lock_mode == "SHARE UPDATE EXCLUSIVE"
    assert operation.cost.kind is CostKind.SCAN


def test_drop_constraint() -> None:
    operation, _ = op("ALTER TABLE orders DROP CONSTRAINT fk;")
    assert operation.kind == "drop_constraint"
    assert operation.detail["constraint"] == "fk"


def test_create_index_blocks_writes() -> None:
    operation, _ = op("CREATE INDEX idx ON users (email);")
    assert operation.kind == "create_index"
    assert operation.lock_mode == "SHARE"
    assert operation.lock.blocks_writes is True
    assert operation.lock.blocks_reads is False


def test_create_index_concurrently_allows_writes() -> None:
    operation, _ = op("CREATE INDEX CONCURRENTLY idx ON users (email);")
    assert operation.lock_mode == "SHARE UPDATE EXCLUSIVE"
    assert operation.blocking is False


def test_create_index_in_transaction_flagged() -> None:
    operation, _ = op("BEGIN; CREATE INDEX CONCURRENTLY idx ON users (email); COMMIT;")
    assert migration("BEGIN; CREATE INDEX CONCURRENTLY idx ON users (email); COMMIT;",
                     baseline=SCHEMA, rows_map=ROWS).ops[1].in_transaction is True
    assert operation.kind == "begin"


def test_drop_index_modes() -> None:
    operation, _ = op("DROP INDEX idx;")
    assert operation.lock_mode == "ACCESS EXCLUSIVE"
    concurrent, _ = op("DROP INDEX CONCURRENTLY idx;")
    assert concurrent.lock_mode == "SHARE UPDATE EXCLUSIVE"


def test_truncate_is_irreversible() -> None:
    operation, _ = op("TRUNCATE users;")
    assert operation.kind == "truncate"
    assert operation.irreversible is True


def test_drop_table_is_irreversible() -> None:
    operation, _ = op("DROP TABLE users;")
    assert operation.kind == "drop_table"
    assert operation.irreversible is True


def test_update_without_where_writes_every_row() -> None:
    operation, _ = op("UPDATE users SET phone = NULL;")
    assert operation.kind == "update"
    assert operation.detail["where"] is False
    assert operation.cost.rows == 1_000_000
    assert operation.irreversible is True


def test_update_with_where_is_cheaper() -> None:
    operation, _ = op("UPDATE users SET phone = NULL WHERE id = 1;")
    assert operation.detail["where"] is True
    assert operation.cost.rows == 10_000
    assert operation.irreversible is False


def test_delete_without_where() -> None:
    operation, _ = op("DELETE FROM orders;")
    assert operation.kind == "delete"
    assert operation.irreversible is True


def test_insert_single_row() -> None:
    operation, _ = op("INSERT INTO users (id) VALUES (1);")
    assert operation.kind == "insert"
    assert operation.cost.rows == 1


def test_set_statement_is_not_blocking() -> None:
    operation, _ = op("SET lock_timeout = '3s';")
    assert operation.kind == "other"
    assert operation.contends is False


# ------------------------------------------------------------------ 파일 단위
def test_transaction_wrapped_with_begin_commit() -> None:
    result = migration("BEGIN; ALTER TABLE users ADD COLUMN a int; COMMIT;", baseline=SCHEMA, rows_map=ROWS)
    assert result.transaction_wrapped is True


def test_transaction_wrapped_when_commit_missing() -> None:
    result = migration("BEGIN; ALTER TABLE users ADD COLUMN a int;", baseline=SCHEMA, rows_map=ROWS)
    assert result.transaction_wrapped is True


def test_not_wrapped_without_begin() -> None:
    result = migration("ALTER TABLE users ADD COLUMN a int;", baseline=SCHEMA, rows_map=ROWS)
    assert result.transaction_wrapped is False


def test_sql_ops_excludes_transaction() -> None:
    result = migration("BEGIN; ALTER TABLE users ADD COLUMN a int; COMMIT;", baseline=SCHEMA, rows_map=ROWS)
    assert len(result.ops) == 3
    assert len(result.sql_ops) == 1


def test_rows_unknown_uses_default() -> None:
    result = migration("CREATE INDEX idx ON mystery (a);", baseline=SCHEMA)
    operation = result.ops[0]
    assert operation.cost.rows == 100_000
    assert operation.detail["rows_known"] is False


def test_hold_seconds_max_when_not_wrapped() -> None:
    result = migration("CREATE INDEX i1 ON users (email); CREATE INDEX i2 ON orders (user_id);",
                       baseline=SCHEMA, rows_map=ROWS)
    estimates = [operation.estimate() for operation in result.blocking_ops]
    assert result.hold_seconds() == max(estimates)


def test_hold_seconds_sum_when_wrapped() -> None:
    result = migration("BEGIN; CREATE INDEX i1 ON users (email); CREATE INDEX i2 ON orders (user_id); COMMIT;",
                       baseline=SCHEMA, rows_map=ROWS)
    estimates = [operation.estimate() for operation in result.blocking_ops]
    assert result.hold_seconds() == sum(estimates)


def test_worst_picks_longest() -> None:
    result = migration("CREATE INDEX i1 ON users (email); CREATE INDEX i2 ON orders (user_id);",
                       baseline=SCHEMA, rows_map=ROWS)
    assert result.worst().table == "orders"


def test_estimate_none_kind_is_fixed() -> None:
    assert estimate_seconds(__import__("migrate_guard.dialect", fromlist=["Cost"]).Cost(CostKind.NONE)) == FIXED_SECONDS


def test_op_by_ref_is_case_insensitive() -> None:
    result = migration("SELECT 1; SELECT 2;", baseline=SCHEMA)
    assert result.op_by_ref("S2") is result.ops[1]
    assert result.op_by_ref("s9") is None


def test_tables_lists_in_order() -> None:
    result = migration(
        "ALTER TABLE users ADD COLUMN a int; ALTER TABLE orders ADD COLUMN b int; ALTER TABLE users ADD COLUMN c int;",
        baseline=SCHEMA, rows_map=ROWS,
    )
    assert result.tables() == ["users", "orders"]


def test_target_falls_back_to_index_name() -> None:
    result = migration("DROP INDEX orders_user_id_idx;", baseline=SCHEMA)
    assert result.ops[0].target == "orders_user_id_idx"


def test_analyze_is_pure() -> None:
    first = analyze("ALTER TABLE users ADD COLUMN a int;", baseline=None)
    second = analyze("ALTER TABLE users ADD COLUMN a int;", baseline=None)
    assert first.ops[0].kind == second.ops[0].kind == "add_column"
