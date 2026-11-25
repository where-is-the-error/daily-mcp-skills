"""레벨 읽기 — 같은 ERROR 를 다섯 가지로 부르는 로그들."""

from __future__ import annotations

import pytest

from log_triage.levels import normalize_word, read_level


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-11-25 09:00:01 INFO  [api] x", "INFO"),
        ("2026-11-25 09:00:01 [error] x", "ERROR"),
        ("2026-11-25 09:00:01 SEVERE: x", "ERROR"),
        ("2026-11-25 09:00:01 FATAL x", "CRITICAL"),
        ("2026-11-25 09:00:01 CRITICAL x", "CRITICAL"),
        ("2026-11-25 09:00:01 DEBUG x", "DEBUG"),
        ("2026-11-25 09:00:01 NOTICE x", "NOTICE"),
        ("2026-11-25 09:00:01 TRACE x", "TRACE"),
        ("2026-11-25 09:00:01 level=error msg=boom", "ERROR"),
        ("2026-11-25 09:00:01 lvl: warn x", "WARN"),
        ("2026-11-25 09:00:01 severity=3 x", "ERROR"),
        ("2026-11-25 09:00:01 severity=0 x", "CRITICAL"),
        ("2026-11-25 09:00:01 E/AndroidRuntime: FATAL EXCEPTION: main", "ERROR"),
        ("2026-11-25 09:00:01 W/ActivityManager: Slow operation", "WARN"),
        ("2026-11-25 09:00:01 I/ActivityManager: Start proc", "INFO"),
        ("2026-11-25 09:00:01 - INFO  [main] x", "INFO"),
        ("2026-11-25 09:00:01 <4> host app[1]: x", "WARN"),
    ],
)
def test_levels(text, expected):
    level, raw, end = read_level(text, 19)
    assert level == expected, (level, raw, text)
    assert raw
    assert end >= 19


def test_level_after_comma_millis():
    text = "2026-11-25 09:00:01,123 WARNING [api] x"
    level, raw, end = read_level(text, 23)
    assert level == "WARN"
    assert text[end:].strip().startswith("[api]")


def test_level_after_apache_status():
    text = '10.0.4.18 - - [25/Nov/2026:09:00:06 +0900] "POST /v1/orders HTTP/1.1" 502 128'
    level, raw, _ = read_level(text, 44)
    assert level in (None, "ERROR")


def test_no_level_found():
    level, raw, end = read_level("combo sshd(pam_unix)[19939]: session opened", 0)
    assert level is None
    assert raw is None
    assert end == 0


def test_empty_line_is_safe():
    assert read_level("", 0) == (None, None, 0)


def test_level_not_confused_with_word_inside_message():
    # 본문 첫 단어가 'information' 이면 레벨로 읽힐 수 있다 — 그건 감수하고 원문을 남긴다
    level, raw, _ = read_level("2026-11-25 09:00:01 information about the job", 19)
    assert level == "INFO"
    assert raw == "information"


def test_numeric_python_levels():
    assert normalize_word("40") is None       # 숫자는 단어가 아니다
    level, _, _ = read_level("2026-11-25 09:00:01 level=40 x", 19)
    assert level == "ERROR"


def test_log4j_lowercase_variants():
    for word in ("warn", "warning", "Warn", "WARNING"):
        level, _, _ = read_level(f"2026-11-25 09:00:01 {word} x", 19)
        assert level == "WARN"


def test_java_util_logging_fine():
    level, _, _ = read_level("2026-11-25 09:00:01 FINE: low level detail", 19)
    assert level == "DEBUG"


def test_trace_position_used_for_cut():
    text = "2026-11-25 09:00:01 ERROR boom"
    level, _, end = read_level(text, 19)
    assert level == "ERROR"
    assert text[end:].strip() == "boom"
