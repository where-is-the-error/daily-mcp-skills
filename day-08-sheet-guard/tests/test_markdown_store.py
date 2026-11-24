"""마크다운 출력과 세션 저장."""

from __future__ import annotations

import pytest

from conftest import make
from sheet_guard.markdown import markdown_cell_table, to_markdown
from sheet_guard.store import Store, file_fingerprint


def test_markdown_has_header_and_rows() -> None:
    table = make("이름,나이\n김,31\n이,28\n")
    text = to_markdown(table)
    assert "| 이름 | 나이 |" in text
    assert "| 김 | 31 |" in text


def test_markdown_escapes_pipe() -> None:
    table = make("이름,메모\n김,a|b\n")
    assert "a\\|b" in to_markdown(table)


def test_markdown_type_line() -> None:
    table = make("이름,나이\n김,31\n")
    text = to_markdown(table)
    assert "열 종류" in text
    assert "나이:정수" in text


def test_markdown_type_line_can_be_off() -> None:
    table = make("이름,나이\n김,31\n")
    assert "열 종류" not in to_markdown(table, include_types=False)


def test_markdown_truncation_note() -> None:
    text = "a\n" + "".join(f"{i}\n" for i in range(40))
    table = make(text)
    out = to_markdown(table, max_rows=5)
    assert "행 더" in out


def test_markdown_column_limit() -> None:
    header = ",".join(f"c{i}" for i in range(20))
    row = ",".join(str(i) for i in range(20))
    table = make(f"{header}\n{row}\n")
    out = to_markdown(table, column_limit=5)
    assert "열 더" in out


def test_markdown_skips_non_data_rows() -> None:
    table = make("a,b\n1,2\n소계,3\n")
    assert "소계" not in to_markdown(table)


def test_markdown_empty_table() -> None:
    table = make("")
    assert "비어" in to_markdown(table)


def test_markdown_newline_in_cell_replaced() -> None:
    table = make('a,b\n"첫줄\n둘째",2\n')
    assert "첫줄 둘째" in to_markdown(table)


def test_cell_table_view() -> None:
    table = make("이름,나이\n김,31\n이,28\n")
    out = markdown_cell_table(table, max_rows=1)
    assert out.startswith("- 이름: 김")


def test_store_put_get() -> None:
    store = Store()
    table = make("a,b\n1,2\n")
    ref = store.put(table)
    assert ref == "t1"
    assert store.get(ref) is table


def test_store_unknown_ref() -> None:
    store = Store()
    with pytest.raises(KeyError):
        store.get("t99")


def test_store_limit() -> None:
    store = Store(limit=2)
    for _ in range(3):
        store.put(make("a,b\n1,2\n"))
    assert store.refs() == ["t2", "t3"]
    with pytest.raises(KeyError):
        store.get("t1")


def test_store_fingerprint() -> None:
    store = Store()
    ref = store.put(make("a\n1\n"), "abc123")
    assert store.fingerprint(ref) == "abc123"


def test_file_fingerprint(tmp_path) -> None:
    path = tmp_path / "a.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    first = file_fingerprint(path)
    path.write_text("a,b\n1,3\n", encoding="utf-8")
    assert first != file_fingerprint(path)
    assert file_fingerprint(tmp_path / "없음.csv") == ""


def test_store_clear() -> None:
    store = Store()
    store.put(make("a\n1\n"))
    store.clear()
    assert store.refs() == []
