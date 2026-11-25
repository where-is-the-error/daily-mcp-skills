"""검색 — 원본 줄 번호로 돌려준다."""

from __future__ import annotations

import pytest

from conftest import make
from log_triage.search import find


def _log():
    return make(
        "2026-11-25 09:00:01 INFO boot\n"
        "2026-11-25 09:00:02 ERROR connection reset\n"
        "Traceback (most recent call last):\n"
        '  File "/srv/app/net.py", line 10, in recv\n'
        "2026-11-25 09:00:03 INFO done\n"
    )


def test_plain_find():
    result = find(_log(), "connection")
    assert result.total == 1
    assert result.matches[0].line_no == 2


def test_case_insensitive_default():
    assert find(_log(), "CONNECTION").total == 1


def test_case_sensitive():
    assert find(_log(), "CONNECTION", ignore_case=False).total == 0


def test_context_lines():
    result = find(_log(), "Traceback", context=1)
    match = result.matches[0]
    assert [number for number, _ in match.before] == [2]
    assert [number for number, _ in match.after] == [4]


def test_regex_mode():
    result = find(_log(), r"line \d+", regex=True)
    assert result.total == 1


def test_bad_regex_reports_error():
    result = find(_log(), "([", regex=True)
    assert result.error.startswith("정규식 오류")


def test_empty_pattern():
    assert find(_log(), "").error


def test_max_matches_limits_but_total_counts():
    log = make("".join(f"2026-11-25 09:00:{i:02d} INFO hit {i}\n" for i in range(10)))
    result = find(log, "hit", max_matches=3)
    assert result.total == 10
    assert len(result.matches) == 3


def test_trace_lines_searchable_with_line_numbers():
    result = find(_log(), "net.py")
    assert result.total == 1
    assert result.matches[0].line_no == 4


def test_scanned_count():
    assert find(_log(), "x").scanned == 5


def test_no_match():
    result = find(_log(), "definitely-not-there")
    assert result.total == 0
    assert result.matches == []
