"""스키마 읽기 — CREATE TABLE / CREATE INDEX 를 모델로, 마이그레이션을 얹어 비교."""

from __future__ import annotations

from migrate_guard.schema import (
    apply_statement,
    bare,
    diff_schema,
    parse_create_index,
    parse_create_table,
    parse_identifier,
    parse_schema,
    schema_after,
)
from migrate_guard.splitter import split_statements


def table_of(sql: str):
    table = parse_create_table(sql)
    assert table is not None
    return table


# ------------------------------------------------------------------ 식별자
def test_parse_identifier_folds_case() -> None:
    assert parse_identifier("Users") == "users"


def test_parse_identifier_quoted_keeps_case() -> None:
    assert parse_identifier('"Users"') == "Users"


def test_parse_identifier_schema() -> None:
    assert parse_identifier("public.users") == "public.users"


def test_bare_drops_schema() -> None:
    assert bare("public.users") == "users"


# ------------------------------------------------------------------ CREATE TABLE
def test_columns_are_parsed() -> None:
    table = table_of("CREATE TABLE users (id bigint, email varchar(255))")
    assert list(table.columns) == ["id", "email"]
    assert table.columns["email"].type == "varchar(255)"


def test_primary_key_inline() -> None:
    table = table_of("CREATE TABLE t (id bigint PRIMARY KEY)")
    assert table.columns["id"].primary_key is True
    assert table.columns["id"].nullable is False


def test_not_null() -> None:
    table = table_of("CREATE TABLE t (a text NOT NULL, b text)")
    assert table.columns["a"].nullable is False
    assert table.columns["b"].nullable is True


def test_default_literal() -> None:
    table = table_of("CREATE TABLE t (a integer NOT NULL DEFAULT 0)")
    assert table.columns["a"].default == "0"


def test_default_string() -> None:
    table = table_of("CREATE TABLE t (a varchar(24) NOT NULL DEFAULT 'pending')")
    assert table.columns["a"].default == "'pending'"


def test_default_function() -> None:
    table = table_of("CREATE TABLE t (a timestamptz NOT NULL DEFAULT now())")
    assert table.columns["a"].default == "now()"


def test_default_cast_expression() -> None:
    table = table_of("CREATE TABLE t (a jsonb DEFAULT '{}'::jsonb)")
    assert table.columns["a"].default == "'{}'::jsonb"


def test_default_parenthesized_expression() -> None:
    table = table_of("CREATE TABLE t (a integer DEFAULT (1 + 2))")
    assert table.columns["a"].default == "(1 + 2)"


def test_inline_references() -> None:
    table = table_of("CREATE TABLE t (user_id bigint NOT NULL REFERENCES users (id))")
    assert table.columns["user_id"].references == "users"


def test_table_level_primary_key() -> None:
    table = table_of("CREATE TABLE t (a bigint, b bigint, PRIMARY KEY (a, b))")
    assert table.columns["a"].primary_key and table.columns["b"].primary_key
    assert table.primary_key == ["a", "b"]


def test_table_level_unique_marks_column() -> None:
    table = table_of("CREATE TABLE t (name varchar(64), UNIQUE(name))")
    assert table.columns["name"].unique is True


def test_named_constraint_is_kept() -> None:
    table = table_of("CREATE TABLE t (a int, CONSTRAINT t_a_positive CHECK (a > 0))")
    assert "t_a_positive" in table.constraints


def test_table_constraint_without_name() -> None:
    table = table_of("CREATE TABLE t (a int, CHECK (a > 0))")
    assert any("CHECK" in value for value in table.constraints.values())


def test_if_not_exists() -> None:
    assert table_of("CREATE TABLE IF NOT EXISTS t (a int)").name == "t"


def test_unlogged_table() -> None:
    assert table_of("CREATE UNLOGGED TABLE t (a int)").name == "t"


def test_schema_qualified_table() -> None:
    assert table_of("CREATE TABLE billing.invoices (id bigint)").name == "billing.invoices"


def test_quoted_column_name() -> None:
    table = table_of('CREATE TABLE t ("order" integer)')
    assert "order" in table.columns


def test_multiline_table() -> None:
    sql = """CREATE TABLE t (
        id bigint PRIMARY KEY,
        email varchar(255) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        amount numeric(12, 2) DEFAULT 0
    )"""
    table = table_of(sql)
    assert len(table.columns) == 4
    assert table.columns["amount"].type == "numeric(12, 2)"


def test_generated_column_marked() -> None:
    table = table_of("CREATE TABLE t (a integer, b integer GENERATED ALWAYS AS (a * 2) STORED)")
    assert table.columns["b"].generated is True


# ------------------------------------------------------------------ CREATE INDEX
def test_index_columns() -> None:
    index = parse_create_index("CREATE INDEX orders_user_id_idx ON orders (user_id)")
    assert index is not None
    assert index.table == "orders"
    assert index.columns == ["user_id"]


def test_index_unique() -> None:
    index = parse_create_index("CREATE UNIQUE INDEX users_email_key ON users (email)")
    assert index.unique is True


def test_index_concurrently() -> None:
    index = parse_create_index("CREATE INDEX CONCURRENTLY idx ON t (a)")
    assert index.concurrently is True


def test_index_where_clause() -> None:
    index = parse_create_index("CREATE INDEX idx ON t (a) WHERE a IS NOT NULL")
    assert index.where == "a IS NOT NULL"


def test_index_method() -> None:
    index = parse_create_index("CREATE INDEX idx ON t USING gin (payload)")
    assert index.method == "gin"
    assert index.columns == ["payload"]


def test_index_expression_flagged() -> None:
    index = parse_create_index("CREATE INDEX idx ON t (lower(email))")
    assert index.expression is True


def test_index_desc_column() -> None:
    index = parse_create_index("CREATE INDEX idx ON t (created_at DESC)")
    assert index.columns == ["created_at"]


def test_index_if_not_exists() -> None:
    index = parse_create_index("CREATE INDEX IF NOT EXISTS idx ON t (a)")
    assert index.name == "idx"


# ------------------------------------------------------------------ 적용
def apply_all(schema, sql: str):
    for statement in split_statements(sql):
        apply_statement(schema, statement)
    return schema


def test_apply_add_column() -> None:
    schema = parse_schema("CREATE TABLE t (id bigint PRIMARY KEY)")
    apply_all(schema, "ALTER TABLE t ADD COLUMN email varchar(255);")
    assert schema.table("t").columns["email"].type == "varchar(255)"


def test_apply_drop_column() -> None:
    schema = parse_schema("CREATE TABLE t (id bigint, email varchar(255))")
    apply_all(schema, "ALTER TABLE t DROP COLUMN email;")
    assert "email" not in schema.table("t").columns


def test_apply_rename_column() -> None:
    schema = parse_schema("CREATE TABLE t (id bigint, old_name text)")
    apply_all(schema, "ALTER TABLE t RENAME COLUMN old_name TO new_name;")
    assert "new_name" in schema.table("t").columns


def test_apply_rename_table() -> None:
    schema = parse_schema("CREATE TABLE t (id bigint)")
    apply_all(schema, "ALTER TABLE t RENAME TO t2;")
    assert schema.table("t2") is not None
    assert schema.table("t") is None


def test_apply_alter_type() -> None:
    schema = parse_schema("CREATE TABLE t (a varchar(32))")
    apply_all(schema, "ALTER TABLE t ALTER COLUMN a TYPE varchar(64);")
    assert schema.table("t").columns["a"].type == "varchar(64)"


def test_apply_set_not_null() -> None:
    schema = parse_schema("CREATE TABLE t (a text)")
    apply_all(schema, "ALTER TABLE t ALTER COLUMN a SET NOT NULL;")
    assert schema.table("t").columns["a"].nullable is False


def test_apply_drop_not_null() -> None:
    schema = parse_schema("CREATE TABLE t (a text NOT NULL)")
    apply_all(schema, "ALTER TABLE t ALTER COLUMN a DROP NOT NULL;")
    assert schema.table("t").columns["a"].nullable is True


def test_apply_set_default() -> None:
    schema = parse_schema("CREATE TABLE t (a integer)")
    apply_all(schema, "ALTER TABLE t ALTER COLUMN a SET DEFAULT 3;")
    assert schema.table("t").columns["a"].default == "3"


def test_apply_drop_default() -> None:
    schema = parse_schema("CREATE TABLE t (a integer DEFAULT 1)")
    apply_all(schema, "ALTER TABLE t ALTER COLUMN a DROP DEFAULT;")
    assert schema.table("t").columns["a"].default is None


def test_apply_add_constraint() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint)")
    apply_all(schema, "ALTER TABLE t ADD CONSTRAINT t_pk PRIMARY KEY (a);")
    assert schema.table("t").columns["a"].primary_key is True


def test_apply_drop_constraint() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint, CONSTRAINT t_pk PRIMARY KEY (a))")
    apply_all(schema, "ALTER TABLE t DROP CONSTRAINT t_pk;")
    assert "t_pk" not in schema.table("t").constraints


def test_apply_drop_table_removes_indexes() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint); CREATE INDEX t_a_idx ON t (a);")
    apply_all(schema, "DROP TABLE t;")
    assert schema.indexes == {}


def test_apply_create_index() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint)")
    apply_all(schema, "CREATE INDEX t_a_idx ON t (a);")
    assert "t_a_idx" in schema.indexes


def test_apply_drop_index() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint); CREATE INDEX t_a_idx ON t (a);")
    apply_all(schema, "DROP INDEX CONCURRENTLY t_a_idx;")
    assert "t_a_idx" not in schema.indexes


def test_alter_unknown_table_is_ignored() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint)")
    apply_all(schema, "ALTER TABLE nope ADD COLUMN b int;")
    assert "b" not in schema.table("t").columns


# ------------------------------------------------------------------ 비교
def test_diff_detects_added_and_removed() -> None:
    before = parse_schema("CREATE TABLE t (a bigint, b text)")
    after = apply_all(parse_schema("CREATE TABLE t (a bigint, b text)"), "ALTER TABLE t DROP COLUMN b;")
    diff = diff_schema(before, after)
    assert diff.columns_removed == [("t", "b")]


def test_diff_type_change() -> None:
    before = parse_schema("CREATE TABLE t (a varchar(32))")
    after = apply_all(parse_schema("CREATE TABLE t (a varchar(32))"), "ALTER TABLE t ALTER COLUMN a TYPE varchar(16);")
    diff = diff_schema(before, after)
    assert [c.field for c in diff.columns_changed] == ["type"]
    assert diff.columns_changed[0].before == "varchar(32)"


def test_diff_table_added() -> None:
    before = parse_schema("CREATE TABLE t (a bigint)")
    after = apply_all(parse_schema("CREATE TABLE t (a bigint)"), "CREATE TABLE u (id bigint);")
    assert diff_schema(before, after).tables_added == ["u"]


def test_diff_index_added() -> None:
    before = parse_schema("CREATE TABLE t (a bigint)")
    after = apply_all(parse_schema("CREATE TABLE t (a bigint)"), "CREATE INDEX t_a_idx ON t (a);")
    assert diff_schema(before, after).indexes_added == ["t_a_idx"]


def test_diff_empty() -> None:
    schema = parse_schema("CREATE TABLE t (a bigint)")
    assert diff_schema(schema, schema).empty


def test_schema_after_does_not_mutate_baseline() -> None:
    before = parse_schema("CREATE TABLE t (a bigint)")
    after = schema_after(before, split_statements("ALTER TABLE t ADD COLUMN b int;"))
    assert "b" in after.table("t").columns
    assert "b" not in before.table("t").columns


def test_example_schema_parses() -> None:
    from conftest import SCHEMA

    schema = parse_schema(SCHEMA.read_text(encoding="utf-8"))
    assert len(schema.tables) == 6
    assert schema.table("users") is not None
    assert len(schema.indexes) == 3
