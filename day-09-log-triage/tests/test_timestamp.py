"""시각 읽기 — 표기 12가지와, 읽지 못했을 때의 태도."""

from __future__ import annotations

from datetime import datetime

import pytest

from log_triage.timestamp import read_stamp


def stamp(text: str, previous=None, year: int = 2026):
    result = read_stamp(text, previous, year)
    assert result is not None, text
    return result


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-11-25 09:00:01,123 INFO x", datetime(2026, 11, 25, 9, 0, 1, 123000)),
        ("2026-11-25T09:00:02.456+09:00 INFO x", datetime(2026, 11, 25, 9, 0, 2, 456000)),
        ("2026/11/25 09:00:03 x", datetime(2026, 11, 25, 9, 0, 3)),
        ("2026.11.25 09:00:04 x", datetime(2026, 11, 25, 9, 0, 4)),
        ("[2026-11-25 09:00:05] x", datetime(2026, 11, 25, 9, 0, 5)),
        ("2026-11-25 09:00:06| x", datetime(2026, 11, 25, 9, 0, 6)),
    ],
)
def test_iso_family(text, expected):
    result = stamp(text)
    assert result.ts == expected
    assert result.kind == "iso"


def test_iso_offset_kept():
    result = stamp("2026-11-25T09:00:02.456+09:00 INFO x")
    assert result.tz_minutes == 540


def test_zulu_is_utc():
    result = stamp("2026-11-25T00:00:02.456Z INFO x")
    assert result.tz_minutes == 0
    assert result.ts.hour == 0


def test_negative_offset():
    result = stamp('2026-11-25T01:00:00-05:00 INFO x')
    assert result.tz_minutes == -300


def test_comma_without_fraction():
    # Windows 이벤트 로그: `2026-11-25 09:00:07, Info   CBS ...`
    result = stamp("2026-11-25 09:00:07, Info                  CBS    started")
    assert result.ts == datetime(2026, 11, 25, 9, 0, 7)


def test_apache_access():
    result = stamp('10.0.4.18 - - [25/Nov/2026:09:00:06 +0900] "GET / HTTP/1.1" 200 512')
    assert result.ts == datetime(2026, 11, 25, 9, 0, 6)
    assert result.tz_minutes == 540
    assert result.kind == "apache"
    assert result.consumed >= 40


def test_apache_error_log():
    result = stamp("[Sun Dec 04 04:47:44 2005] [notice] workerEnv.init() ok")
    assert result.ts == datetime(2005, 12, 4, 4, 47, 44)
    assert result.kind == "apache-clf"


def test_syslog_month_name():
    result = stamp("Nov 25 09:00:05 combo sshd(pam_unix)[19939]: session opened")
    assert result.ts == datetime(2026, 11, 25, 9, 0, 5)
    assert "year-assumed" in result.flags


def test_syslog_single_digit_day():
    result = stamp("Nov  5 09:00:05 host app: hi")
    assert result.ts.day == 5


def test_syslog_uses_previous_year():
    previous = datetime(2025, 12, 31, 23, 0, 0)
    result = stamp("Jan  1 00:10:00 host app: hi", previous)
    assert result.ts.year == 2026
    assert "year-assumed" not in result.flags


def test_hdfs_compact():
    result = stamp("081109 203615 148 INFO dfs.DataNode$PacketResponder: terminating")
    assert result.ts == datetime(2008, 11, 9, 20, 36, 15, 148000)
    assert result.kind == "hdfs"


def test_spark_two_digit_year():
    result = stamp("26/11/25 09:00:09 INFO SparkContext: Running Spark")
    assert result.ts.year == 2026


def test_android_logcat():
    result = stamp("11-25 09:00:10.445  1842  1842 I ActivityManager: Start proc")
    assert result.ts == datetime(2026, 11, 25, 9, 0, 10, 445000)
    assert result.kind == "android"


def test_proxifier_bracket_mmdd():
    result = stamp("[10.30 16:49:06] chrome.exe - open through proxy")
    assert result.ts.hour == 16
    assert result.kind == "mmdd"


def test_compact_health_app():
    result = stamp("20171223-22:15:29:606|Step_LSC|30002312|onStandStepChanged 3579")
    assert result.ts == datetime(2017, 12, 23, 22, 15, 29, 606000)
    assert result.kind == "compact"


def test_dotted_bgl():
    result = stamp("- 1117838570 2005.06.03 R02-M1-N0 2005-06-03-15.42.50.675872 R02 RAS KERNEL INFO")
    assert result.ts == datetime(2005, 6, 3, 15, 42, 50, 675872)
    assert result.kind == "dotted"


def test_epoch_seconds():
    result = stamp("1764037247 INFO x")
    assert result.kind == "epoch"
    assert result.ts.year in (2025, 2026)


def test_epoch_out_of_range_rejected():
    # 2000년보다 이르거나 2100년보다 늦는 값은 시각으로 쓰지 않는다
    assert read_stamp("0000000001 INFO x") is None


def test_field_epoch_needs_ten_digits():
    result = stamp("134681 node-246 unix.hw state_change.unavailable 1077804742 1 Component")
    assert result.kind == "epoch-field"
    assert "epoch-guess" in result.flags
    assert result.ts.year == 2004


def test_time_only_uses_previous_date():
    previous = datetime(2026, 11, 25, 9, 0, 0)
    result = stamp("09:00:11 INFO  [boot] time only", previous)
    assert result.ts == datetime(2026, 11, 25, 9, 0, 11)
    assert result.kind == "time-only"


def test_time_only_without_previous_is_flagged():
    result = stamp("09:00:11 INFO x")
    assert "date-assumed" in result.flags


def test_no_timestamp_returns_none():
    assert read_stamp("Traceback (most recent call last):") is None
    assert read_stamp("    raise ValueError('x')") is None
    assert read_stamp("") is None


def test_invalid_date_rejected():
    assert read_stamp("2026-02-30 09:00:00 x") is None


def test_number_in_middle_is_not_a_stamp():
    # 줄 앞 64자 밖의 숫자는 시각이 아니다
    text = "x" * 70 + " 2026-11-25 09:00:00"
    assert read_stamp(text) is None


def test_empty_message_stamp_only():
    result = stamp("2026-11-25 09:00:00")
    assert result.consumed == 19
