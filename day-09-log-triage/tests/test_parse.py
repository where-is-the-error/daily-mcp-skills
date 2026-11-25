"""파일 읽기 — 인코딩·이어짐·JSON·레코드 경계."""

from __future__ import annotations

import pytest

from conftest import make, raw_lines
from log_triage.parse import decode_bytes, has_trace_id, load_log, parse_text

from conftest import BEFORE, KOREAN, MESSY


def test_counts_and_bounds():
    log = make(
        "2026-11-25 09:00:01 INFO a\n"
        "2026-11-25 09:00:02 INFO b\n"
    )
    assert len(log) == 2
    assert log.records[0].line_no == 1
    assert log.records[1].line_no == 2
    assert log.total_lines == 2
    assert log.continuation_lines == 0


def test_multiline_stack_attaches_to_previous():
    log = make(
        "2026-11-25 09:00:01 ERROR boom\n"
        "Traceback (most recent call last):\n"
        '  File "/srv/app/x.py", line 1, in f\n'
        "ValueError: bad\n"
        "2026-11-25 09:00:02 INFO next\n"
    )
    assert len(log) == 2
    first = log.records[0]
    assert first.trace == [
        "Traceback (most recent call last):",
        '  File "/srv/app/x.py", line 1, in f',
        "ValueError: bad",
    ]
    assert log.continuation_lines == 3
    assert first.line_count == 4
    assert first.has_trace


def test_indented_continuation():
    log = make(
        "2026-11-25 09:00:01 INFO message starts\n"
        "  wrapped line continues here\n"
        "2026-11-25 09:00:02 INFO next\n"
    )
    assert len(log) == 2
    assert log.records[0].trace == ["  wrapped line continues here"]


def test_java_caused_by_continuation():
    log = make(
        "2026-11-25 09:00:01 ERROR request failed\n"
        "\tat com.example.App.main(App.java:10)\n"
        "Caused by: java.io.IOException: disk full\n"
        "\tat com.example.Disk.write(Disk.java:42)\n"
    )
    assert len(log) == 1
    assert len(log.records[0].trace) == 3


def test_same_line_number_accounting():
    log = make(
        "2026-11-25 09:00:01 ERROR boom\n"
        "Traceback (most recent call last):\n"
        "  ValueError: bad\n"
        "2026-11-25 09:00:02 INFO next\n"
    )
    # 다음 레코드의 줄 번호는 이어짐 줄 수를 건너뛴 실제 위치
    assert log.records[1].line_no == 4


def test_orphans_before_first_record():
    log = make("JVM started\nbanner line\n2026-11-25 09:00:01 INFO a\n")
    assert len(log.orphans) == 2
    assert log.orphans[0] == (1, "JVM started")
    assert len(log) == 1


def test_blank_lines_not_counted_as_records():
    log = make("\n\n2026-11-25 09:00:01 INFO a\n\n2026-11-25 09:00:02 INFO b\n\n")
    assert len(log) == 2


def test_no_timestamp_file_has_no_records():
    log = make("설정 파일 덤프\nkey=value\n")
    assert len(log) == 0
    assert len(log.orphans) == 2
    assert log.span() == (None, None, 0.0)


def test_json_lines_detected():
    log = make(
        '{"@timestamp":"2026-11-25T09:00:01Z","level":"info","message":"ready"}\n'
        '{"@timestamp":"2026-11-25T09:00:02Z","level":"error","message":"boom"}\n'
        '{"@timestamp":"2026-11-25T09:00:03Z","level":"warn","message":"slow"}\n'
    )
    assert log.format_hint == "jsonl"
    assert [r.level for r in log.records] == ["INFO", "ERROR", "WARN"]
    assert log.records[1].message == "boom"


def test_json_epoch_millis():
    log = make('{"ts":1764037247123,"level":"ERROR","msg":"x"}\n')
    record = log.records[0]
    assert record.ts is not None
    assert record.message == "x"


def test_json_stack_field():
    log = make('{"ts":"2026-11-25T09:00:01Z","level":"error","msg":"x",'
               '"error":{"stack":"Error: bad\\n    at f (/a.js:1:1)"}}\n')
    assert log.records[0].trace
    assert "at f" in log.records[0].trace[1]


def test_json_extra_fields():
    log = make('{"ts":"2026-11-25T09:00:01Z","level":"info","msg":"x",'
               '"service":"api","status":200,"request_id":"abc"}\n')
    fields = log.records[0].fields
    assert fields["service"] == "api"
    assert fields["status"] == "200"


def test_json_line_inside_plain_file():
    log = make(
        "2026-11-25 09:00:01 INFO text line\n"
        '{"@timestamp":"2026-11-25T09:00:02Z","level":"error","message":"json"}\n'
        "2026-11-25 09:00:03 INFO text again\n"
    )
    assert log.format_hint == "plain"
    assert log.records[1].message == "json"
    assert log.records[1].level == "ERROR"


def test_broken_json_falls_back_to_text():
    log = make(
        '{"@timestamp":"2026-11-25T09:00:01Z","level":"info","msg":"a"}\n'
        '{"@timestamp":"2026-11-25T09:00:02Z", broken\n'
        '{"@timestamp":"2026-11-25T09:00:03Z","level":"info","msg":"c"}\n'
    )
    assert len(log.records) == 3


def test_kv_fields():
    log = make("2026-11-25 09:00:01 INFO user=kim status=200 path=/v1/orders\n")
    fields = log.records[0].fields
    assert fields["user"] == "kim"
    assert fields["path"] == "/v1/orders"


def test_message_excludes_timestamp_and_level():
    log = make("2026-11-25 09:00:01,123 INFO  [api] hello world\n")
    assert log.records[0].message == "[api] hello world"


def test_apache_message_keeps_request_line():
    log = make('10.0.4.18 - - [25/Nov/2026:09:00:06 +0900] "POST /v1/orders HTTP/1.1" 502 128\n')
    record = log.records[0]
    assert record.level == "ERROR"
    assert "POST /v1/orders" in record.message


def test_apache_status_4xx_is_warn():
    log = make('10.0.4.18 - - [25/Nov/2026:09:00:06 +0900] "GET /x HTTP/1.1" 404 12\n')
    assert log.records[0].level == "WARN"


def test_encoding_utf8_exact():
    text, encoding, confidence, bom = decode_bytes("한글 로그".encode("utf-8"))
    assert encoding == "utf-8"
    assert confidence == 1.0
    assert not bom
    assert text == "한글 로그"


def test_encoding_cp949():
    text, encoding, confidence, bom = decode_bytes("결제 승인 실패: 카드사 지연".encode("cp949"))
    assert encoding == "cp949"
    assert confidence > 0.5
    assert "결제" in text


def test_encoding_bom_stripped():
    text, encoding, _, bom = decode_bytes(b"\xef\xbb\xbf2026-11-25 09:00:01 INFO x\n")
    assert bom is True
    assert encoding == "utf-8-sig"
    assert not text.startswith("\ufeff")


def test_encoding_utf16():
    text, encoding, _, _ = decode_bytes("2026-11-25 09:00:01 INFO x\n".encode("utf-16"))
    assert encoding == "utf-16-le"
    assert "INFO" in text


def test_encoding_latin1_fallback():
    data = b"caf\xe9 au lait 2026-11-25\n"
    text, encoding, _, _ = decode_bytes(data)
    assert "caf" in text


def test_fingerprint_stable(tmp_path):
    path = tmp_path / "a.log"
    path.write_text("2026-11-25 09:00:01 INFO x\n", encoding="utf-8")
    first = load_log(path)
    second = load_log(path)
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 16


def test_span_and_duration():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 09:02:00 INFO b\n"
    )
    first, last, seconds = log.span()
    assert seconds == 120
    assert log.duration_minutes() == pytest.approx(2.0)


def test_out_of_order_records_sorted_for_span():
    log = make(
        "2026-11-25 09:05:00 INFO late\n"
        "2026-11-25 09:00:00 INFO early\n"
    )
    first, last, seconds = log.span()
    assert first.hour == 9 and first.minute == 0
    assert last.minute == 5
    assert seconds == 300


def test_unknown_levels_kept():
    log = make("2026-11-25 09:00:01 no level here at all\n")
    assert log.records[0].level is None
    assert log.level_counts()["UNKNOWN"] == 1


def test_trace_id_detection():
    log = make(
        "2026-11-25 09:00:01 ERROR request_id=abc123 failed\n"
        "2026-11-25 09:00:02 ERROR trace_id=deadbeef failed\n"
    )
    assert has_trace_id(log.records[0])
    assert has_trace_id(log.records[1])


def test_no_trace_id():
    log = make("2026-11-25 09:00:01 INFO just a message\n")
    assert not has_trace_id(log.records[0])


def test_real_before_file_parses_almost_everything():
    log = load_log(BEFORE)
    assert len(log.records) > 1300
    assert len(log.records) / log.total_lines > 0.95
    assert log.encoding == "utf-8"


def test_real_korean_cp949_file():
    log = load_log(KOREAN)
    assert log.encoding == "cp949"
    assert "결제" in log.records[2].message
    assert log.records[2].level == "ERROR"


def test_real_messy_file_control_char_kept():
    log = load_log(MESSY)
    assert any("\x07" in r.raw for r in log.records)


def test_preview():
    log = make("2026-11-25 09:00:01 INFO a\n2026-11-25 09:00:02 INFO b\n")
    assert len(log.preview(1)) == 1


def test_iter_lines_reconstructs():
    log = make(
        "2026-11-25 09:00:01 ERROR boom\n"
        "Traceback (most recent call last):\n"
        "ValueError: bad\n"
    )
    lines = list(log.iter_lines())
    assert lines[0].startswith("2026-11-25")
    assert lines[-1] == "ValueError: bad"
