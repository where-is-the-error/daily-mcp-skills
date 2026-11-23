"""문장 나누기 — 세미콜론이 문장 끝이 아닌 경우들."""

from __future__ import annotations

from migrate_guard.splitter import (
    match_paren,
    one_line,
    split_statements,
    split_top_level,
    strip_comments,
)


def codes(sql: str) -> list[str]:
    return [statement.code for statement in split_statements(sql)]


def test_two_statements() -> None:
    assert codes("SELECT 1; SELECT 2;") == ["SELECT 1;", "SELECT 2;"]


def test_trailing_without_semicolon() -> None:
    assert codes("SELECT 1") == ["SELECT 1"]


def test_empty_input() -> None:
    assert split_statements("") == []
    assert split_statements("   \n\t ") == []


def test_only_comments() -> None:
    assert split_statements("-- 하나\n/* 둘 */") == []


def test_semicolon_in_line_comment() -> None:
    assert codes("SELECT 1; -- 여기; 세미콜론\nSELECT 2;") == ["SELECT 1;", "SELECT 2;"]


def test_semicolon_in_block_comment() -> None:
    statements = split_statements("SELECT 1 /* ; ; */; SELECT 2;")
    assert len(statements) == 2
    assert statements[0].code.replace("  ", " ") == "SELECT 1 ;"


def test_nested_block_comment() -> None:
    sql = "SELECT 1 /* 바깥 /* 안쪽 ; */ 아직 */; SELECT 2;"
    assert len(split_statements(sql)) == 2


def test_semicolon_in_string() -> None:
    assert codes("INSERT INTO t VALUES ('a;b'); SELECT 1;") == ["INSERT INTO t VALUES ('a;b');", "SELECT 1;"]


def test_escaped_quote_in_string() -> None:
    assert codes("SELECT 'it''s; here'; SELECT 2;") == ["SELECT 'it''s; here';", "SELECT 2;"]


def test_double_quoted_identifier_with_semicolon() -> None:
    assert len(split_statements('CREATE TABLE "weird;name" (id int); SELECT 1;')) == 2


def test_dollar_quoted_body() -> None:
    sql = """
    CREATE OR REPLACE FUNCTION f() RETURNS void AS $$
    BEGIN
      PERFORM 1; -- 본문 안
    END;
    $$ LANGUAGE plpgsql;
    SELECT 1;
    """
    statements = split_statements(sql)
    assert len(statements) == 2
    assert "PERFORM 1" in statements[0].text


def test_tagged_dollar_quote() -> None:
    sql = "DO $body$ BEGIN PERFORM 1; END $body$; SELECT 2;"
    assert len(split_statements(sql)) == 2


def test_dollar_in_identifier_is_not_quote() -> None:
    assert codes("SELECT a$b FROM t;") == ["SELECT a$b FROM t;"]


def test_line_numbers() -> None:
    statements = split_statements("SELECT 1;\n\n-- 주석\nSELECT 2;\nSELECT 3;")
    assert [s.line for s in statements] == [1, 3, 5]   # 두 번째는 앞의 주석 줄에서 시작


def test_line_number_with_leading_blank_lines() -> None:
    statements = split_statements("\n\nALTER TABLE t ADD COLUMN a int;")
    assert statements[0].line == 3


def test_refs_are_sequential() -> None:
    statements = split_statements("SELECT 1; SELECT 2; SELECT 3;")
    assert [s.ref for s in statements] == ["s1", "s2", "s3"]


def test_blank_statements_are_skipped() -> None:
    statements = split_statements(";;;\nSELECT 1;;\n;")
    assert len(statements) == 1
    assert statements[0].ref == "s1"


def test_code_strips_comments_but_keeps_strings() -> None:
    statement = split_statements("SELECT '-- not a comment' /* gone */;")[0]
    assert "not a comment" in statement.code
    assert "gone" not in statement.code


def test_one_line_collapses_whitespace() -> None:
    statement = split_statements("ALTER TABLE t\n   ADD COLUMN a int;")[0]
    assert statement.one_line == "ALTER TABLE t ADD COLUMN a int;"


def test_strip_comments_keeps_string_content() -> None:
    assert "a--b" in strip_comments("SELECT 'a--b'")


def test_strip_comments_removes_nested() -> None:
    assert strip_comments("SELECT 1 /* a /* b */ c */").strip() == "SELECT 1"


def test_statement_text_keeps_original_comments() -> None:
    statement = split_statements("-- 머리말\nSELECT 1;")[0]
    assert statement.text.startswith("-- 머리말")


# ------------------------------------------------------------------ 목록 나누기
def test_split_top_level_simple() -> None:
    assert split_top_level("a, b, c") == ["a", "b", "c"]


def test_split_top_level_respects_parens() -> None:
    assert split_top_level("numeric(10, 2), b int") == ["numeric(10, 2)", "b int"]


def test_split_top_level_respects_strings() -> None:
    assert split_top_level("a text DEFAULT 'x,y', b int") == ["a text DEFAULT 'x,y'", "b int"]


def test_split_top_level_empty() -> None:
    assert split_top_level("") == []


def test_match_paren_basic() -> None:
    sql = "CREATE TABLE t (a int, b numeric(2, 3))"
    assert match_paren(sql, sql.index("(")) == len(sql) - 1


def test_match_paren_ignores_parens_in_strings() -> None:
    sql = "f(')', (a))"
    assert match_paren(sql, 1) == len(sql) - 1


def test_match_paren_missing() -> None:
    assert match_paren("f(a", 1) == -1


def test_crlf_input() -> None:
    statements = split_statements("SELECT 1;\r\nSELECT 2;\r\n")
    assert len(statements) == 2
    assert statements[1].line == 2


def test_semicolon_inside_dollar_quote_with_comment_like_text() -> None:
    sql = "DO $$ -- 주석처럼 보이는 본문; $$; SELECT 1;"
    assert len(split_statements(sql)) == 2
