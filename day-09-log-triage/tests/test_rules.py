"""규칙 — 걸리는 것과, 고치는 순서."""

from __future__ import annotations

from datetime import datetime

import pytest

from conftest import AFTER, BEFORE, MESSY, load_log, make
from log_triage.rules import RULES, catalog, check, counts, worst


def ids(findings) -> set[str]:
    return {finding.rule for finding in findings}


def test_catalog_size():
    assert len(RULES) == 25


def test_every_rule_has_why_and_fix():
    for rule in RULES.values():
        assert rule.why and rule.fix and rule.title
        assert rule.severity in ("critical", "warn", "info")


def test_catalog_all_and_one():
    assert len(catalog()) == 25
    one = catalog("secret-in-log")
    assert one and one[0].id == "secret-in-log"


def test_catalog_unknown():
    assert catalog("없는규칙") == []


def test_no_timestamp_file():
    findings = check(make("no timestamps here\nneither here\n"))
    assert "no-timestamp" in ids(findings)
    assert worst(findings) == "critical"


def test_unknown_level():
    findings = check(make("2026-11-25 09:00:01 something happened\n"))
    assert "unknown-level" in ids(findings)


def test_no_timezone_info():
    findings = check(make("2026-11-25 09:00:01 INFO x\n"))
    assert "no-timezone" in ids(findings)
    assert worst(findings) in ("warn", "info")


def test_mixed_timezones():
    log = make(
        "2026-11-25T09:00:01+09:00 INFO a\n"
        "2026-11-25T00:00:02Z INFO b\n"
    )
    assert "mixed-timezones" in ids(check(log))


def test_out_of_order_rule():
    log = make(
        "2026-11-25 09:05:00 INFO a\n"
        "2026-11-25 09:00:00 INFO b\n"
    )
    assert "out-of-order" in ids(check(log))


def test_time_gap_rule():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 10:00:00 INFO b\n"
    )
    assert "time-gap" in ids(check(log))


def test_future_timestamp_needs_now():
    log = make("2026-11-25 09:00:01 INFO a\n")
    assert "future-timestamp" not in ids(check(log))
    findings = check(log, now=datetime(2026, 11, 24, 9, 0, 0))
    assert "future-timestamp" in ids(findings)


def test_error_without_trace():
    log = make(
        "2026-11-25 09:00:01 ERROR plain error 1\n"
        "2026-11-25 09:00:02 ERROR plain error 2\n"
    )
    assert "error-without-trace" in ids(check(log))


def test_trace_without_error():
    log = make(
        "2026-11-25 09:00:01 INFO something\n"
        "Traceback (most recent call last):\n"
        "  ValueError: x\n"
    )
    assert "trace-without-error" in ids(check(log))


def test_empty_message():
    log = make("2026-11-25 09:00:01 INFO \n2026-11-25 09:00:02 INFO \n")
    assert "empty-message" in ids(check(log))


def test_one_line_storm():
    lines = "".join(f"2026-11-25 09:00:{i:02d} INFO same message\n" for i in range(30))
    lines += "".join(f"2026-11-25 09:01:{i:02d} INFO other {i}\n" for i in range(5))
    assert "one-line-storm" in ids(check(make(lines)))


def test_retry_storm():
    lines = "".join("2026-11-25 09:00:05 ERROR retry failed\n" for _ in range(6))
    assert "retry-storm" in ids(check(make(lines)))


def test_error_burst():
    lines = []
    for minute in range(5):
        lines.append(f"2026-11-25 09:{minute:02d}:00 ERROR steady\n")
        lines += [f"2026-11-25 09:{minute:02d}:{i + 1:02d} INFO ok {i}\n" for i in range(10)]
    lines += [f"2026-11-25 09:10:{i:02d} ERROR steady\n" for i in range(25)]
    assert "error-burst" in ids(check(make("".join(lines))))


def test_control_chars():
    log = make("2026-11-25 09:00:01 INFO bad \x07 char\n")
    assert "control-chars" in ids(check(log))


def test_long_line():
    log = make("2026-11-25 09:00:01 INFO " + "x" * 2500 + "\n")
    assert "long-line" in ids(check(log))


def test_mojibake():
    log = make("2026-11-25 09:00:01 INFO 깨진 □□□ 글자\n")
    assert "mojibake" in ids(check(log))


def test_mixed_formats():
    log = make(
        "2026-11-25 09:00:01 INFO a\n"
        "Nov 25 09:00:02 host app: b\n"
        "081109 203615 148 INFO c\n"
    )
    assert "mixed-formats" in ids(check(log))


def test_secret_in_log_is_critical():
    log = make("2026-11-25 09:00:01 INFO password=hunter2\n")
    findings = check(log)
    secret = [f for f in findings if f.rule == "secret-in-log"]
    assert secret and secret[0].severity == "critical"
    assert worst(findings) == "critical"


def test_pii_in_log():
    log = make("2026-11-25 09:00:01 INFO user kim@example.com from 10.0.0.1\n")
    findings = check(log)
    assert "pii-in-log" in ids(findings)
    assert worst(findings) != "critical"


def test_no_request_id():
    log = make(
        "2026-11-25 09:00:01 ERROR plain boom\n"
        "2026-11-25 09:00:02 INFO ok\n"
    )
    assert "no-request-id" in ids(check(log))


def test_request_id_present_quiet():
    log = make(
        "2026-11-25 09:00:01 ERROR request_id=abc123def456 boom\n"
    )
    assert "no-request-id" not in ids(check(log))


def test_unparsed_stack():
    log = make(
        "2026-11-25 09:00:01 ERROR weird\n"
        "  | weird frame line\n"
    )
    assert "unparsed-stack" in ids(check(log))


def test_orphan_lines():
    log = make("banner\n2026-11-25 09:00:01 INFO a\n")
    assert "orphan-lines" in ids(check(log))


def test_year_assumed():
    log = make("Nov 25 09:00:01 host app: x\n")
    assert "year-assumed" in ids(check(log))


def test_findings_sorted_by_severity():
    log = make("2026-11-25 09:00:01 INFO password=x user a@b.co\n")
    findings = check(log)
    severities = [f.severity for f in findings]
    order = {"critical": 0, "warn": 1, "info": 2}
    assert severities == sorted(severities, key=lambda s: order[s])


def test_counts():
    findings = check(make("2026-11-25 09:00:01 INFO password=x\n"))
    tally = counts(findings)
    assert tally["critical"] == 1


def test_messy_example():
    log = load_log(MESSY)
    findings = check(log)
    found = ids(findings)
    for expected in ("secret-in-log", "pii-in-log", "control-chars", "mojibake",
                     "empty-message", "retry-storm", "long-line"):
        assert expected in found, expected
    assert worst(findings) == "critical"


def test_before_example_is_quiet(before=None):
    log = load_log(BEFORE)
    found = ids(check(log))
    assert "secret-in-log" not in found
    assert "error-burst" not in found


def test_after_example_has_burst():
    log = load_log(AFTER)
    found = ids(check(log))
    assert "error-burst" in found
    assert "secret-in-log" not in found
