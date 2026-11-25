"""스택 — 언어마다 반대인 프레임 순서를 지킨다."""

from __future__ import annotations

import pytest

from conftest import make
from log_triage.stack import analyze_trace, detect_language, exception_head, stack_report

PY_TRACE = [
    "Traceback (most recent call last):",
    '  File "/srv/app/main.py", line 10, in main',
    "    run()",
    '  File "/srv/app/db/pool.py", line 64, in acquire',
    "    raise PoolTimeoutError()",
    "app.db.pool.PoolTimeoutError: could not get connection",
]

JAVA_TRACE = [
    "java.lang.IllegalStateException: pool closed",
    "\tat com.example.Pool.acquire(Pool.java:64)",
    "\tat com.example.App.main(App.java:10)",
    "Caused by: java.io.IOException: disk full",
    "\tat com.example.Disk.write(Disk.java:42)",
]

NODE_TRACE = [
    "TypeError: Cannot read properties of undefined (reading 'id')",
    "    at getUser (/srv/app/users.js:22:15)",
    "    at /srv/app/index.js:10:3",
]

GO_TRACE = [
    "panic: runtime error: index out of range [3] with length 2",
    "",
    "goroutine 1 [running]:",
    "main.process(0xc000012345)",
    "\t/srv/app/main.go:42 +0x1d",
]


def test_detect_python():
    assert detect_language(PY_TRACE) == "python"


def test_detect_java():
    assert detect_language(JAVA_TRACE) == "java"


def test_detect_node():
    assert detect_language(NODE_TRACE) == "node"


def test_detect_go():
    assert detect_language(GO_TRACE) == "go"


def test_detect_unknown():
    assert detect_language(["something went wrong", "no frames here"]) == "unknown"


def test_python_top_frame_is_innermost():
    info = analyze_trace(PY_TRACE)
    assert info.top_frame == "acquire (pool.py:64)"
    assert len(info.frames) == 2


def test_python_exception_line():
    info = analyze_trace(PY_TRACE)
    assert info.exception.startswith("app.db.pool.PoolTimeoutError")


def test_python_first_frame_is_outermost():
    info = analyze_trace(PY_TRACE)
    assert info.frames[0].startswith("main (main.py:10)")


def test_java_top_frame_is_first():
    info = analyze_trace(JAVA_TRACE)
    assert info.top_frame == "com.example.Pool.acquire(Pool.java:64)"
    assert len(info.frames) == 3


def test_java_causes_counted():
    info = analyze_trace(JAVA_TRACE)
    assert info.causes == 2
    assert info.deepest.startswith("java.io.IOException")


def test_java_exception_type():
    info = analyze_trace(JAVA_TRACE)
    assert "IllegalStateException" in info.exception


def test_node_top_frame():
    info = analyze_trace(NODE_TRACE)
    assert info.top_frame == "getUser (users.js:22)"
    assert "TypeError" in info.exception


def test_go_top_frame():
    info = analyze_trace(GO_TRACE)
    assert info.top_frame.startswith("main.process")
    assert "main.go:42" in info.top_frame
    assert "index out of range" in info.exception


def test_unknown_language_leaves_location_blank():
    info = analyze_trace(["boom", "still boom"])
    assert info.language == "unknown"
    assert info.top_frame == ""
    assert info.exception == "boom"


def test_empty_trace():
    info = analyze_trace([])
    assert info.language == "unknown"
    assert info.frames == []


def test_report_counts_traced_records():
    log = make(
        "2026-11-25 09:00:01 ERROR boom\n"
        + "\n".join(PY_TRACE) + "\n"
        "2026-11-25 09:00:02 ERROR no stack here\n"
    )
    report = stack_report(log)
    assert report.traced == 1
    assert report.untraced_errors == 1
    assert report.languages["python"] == 1


def test_report_groups_by_signature():
    log = make(
        "2026-11-25 09:00:01 ERROR pool timeout 1\n" + "\n".join(PY_TRACE) + "\n"
        "2026-11-25 09:00:02 ERROR pool timeout 2\n" + "\n".join(PY_TRACE) + "\n"
    )
    report = stack_report(log)
    assert len(report.groups) == 1
    assert report.groups[0].count == 2
    assert report.groups[0].distinct_stacks == 1


def test_distinct_stacks_counted():
    other = [
        "Traceback (most recent call last):",
        '  File "/srv/app/main.py", line 10, in main',
        '  File "/srv/app/other.py", line 3, in handler',
        "OtherError: x",
    ]
    log = make(
        "2026-11-25 09:00:01 ERROR unhandled\n" + "\n".join(PY_TRACE) + "\n"
        "2026-11-25 09:00:02 ERROR unhandled\n" + "\n".join(other) + "\n"
    )
    report = stack_report(log)
    assert report.groups[0].distinct_stacks == 2


def test_top_frames_ranked():
    log = make(
        "2026-11-25 09:00:01 ERROR a\n" + "\n".join(PY_TRACE) + "\n"
        "2026-11-25 09:00:02 ERROR a\n" + "\n".join(PY_TRACE) + "\n"
    )
    report = stack_report(log)
    assert report.top_frames.most_common(1)[0] == ("pool.py:64", 2)


def test_exception_head_used_for_display():
    record = make("2026-11-25 09:00:01 ERROR unhandled\n" + "\n".join(PY_TRACE) + "\n").records[0]
    head = exception_head(record)
    assert head.startswith("app.db.pool.PoolTimeoutError")


def test_exception_head_empty_without_trace():
    record = make("2026-11-25 09:00:01 ERROR plain\n").records[0]
    assert exception_head(record) == ""


def test_real_after_file_stack_report(after):
    report = stack_report(after)
    assert report.traced > 200
    assert report.languages["python"] == report.traced
    assert report.groups[0].location == "acquire (pool.py:64)"


def test_java_stack_attached_in_parse():
    log = make(
        "2026-11-25 09:00:01 ERROR request failed\n"
        "\tat com.example.App.main(App.java:10)\n"
        "Caused by: java.io.IOException: disk full\n"
    )
    info = analyze_trace(log.records[0].trace)
    assert info.language == "java"
    assert info.top_frame == "com.example.App.main(App.java:10)"
