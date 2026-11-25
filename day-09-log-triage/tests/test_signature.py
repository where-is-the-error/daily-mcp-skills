"""서명 — 같은 사건은 하나로, 다른 사건은 나뉘어."""

from __future__ import annotations

import pytest

from conftest import make
from log_triage.signature import (by_signature, cluster, normalize_message, record_signature,
                                  signature_of, template_share)


def test_numbers_are_stripped():
    assert normalize_message("retry 3 of 5 after 1200ms") == "retry <n> of <n> after <n>"


def test_ids_are_stripped():
    left = normalize_message("request_id=abc123def456 status=200")
    right = normalize_message("request_id=999888777666 status=500")
    assert left == right == "request_id=<*> status=<n>"


def test_uuid_replaced():
    text = normalize_message("trace 8f3c2a1e-1111-2222-3333-444455556666 failed")
    assert "<uuid>" in text


def test_ip_replaced():
    assert normalize_message("client 10.0.4.18 dropped") == "client <ip> dropped"


def test_path_replaced():
    assert normalize_message("GET /v1/orders/1042") == "GET <path>"


def test_quoted_junk_replaced():
    assert normalize_message('value "a b c" here') == "value <str> here"


def test_same_error_different_ids_share_signature():
    a = signature_of("PoolTimeoutError: pool 7 after 5000ms request_id=aaa111bbb222")
    b = signature_of("PoolTimeoutError: pool 12 after 5000ms request_id=ccc333ddd444")
    assert a == b


def test_different_error_types_differ():
    a = signature_of("PoolTimeoutError: pool 7")
    b = signature_of("ConnectionResetError: reset")
    assert a != b


def test_signature_is_stable_across_calls():
    assert signature_of("boom 1") == signature_of("boom 1")


def test_template_truncated():
    text = normalize_message("x" * 500)
    assert len(text) <= 200
    assert text.endswith("…")


def test_cluster_counts():
    log = make(
        "2026-11-25 09:00:01 ERROR pool 1 timeout\n"
        "2026-11-25 09:00:02 ERROR pool 2 timeout\n"
        "2026-11-25 09:00:03 ERROR pool 3 timeout\n"
        "2026-11-25 09:00:04 INFO all good\n"
    )
    clusters = cluster(log)
    assert len(clusters) == 2
    assert clusters[0].count == 3
    assert clusters[0].is_error
    assert clusters[1].count == 1


def test_cluster_first_and_last():
    log = make(
        "2026-11-25 09:00:01 ERROR boom 1\n"
        "2026-11-25 09:05:01 ERROR boom 2\n"
    )
    item = cluster(log)[0]
    assert item.first_ts.minute == 0
    assert item.last_ts.minute == 5
    assert item.first_clock.startswith("2026-11-25 09:00:01")


def test_cluster_samples_unique():
    log = make(
        "2026-11-25 09:00:01 ERROR pool 1 timeout\n"
        "2026-11-25 09:00:02 ERROR pool 2 timeout\n"
        "2026-11-25 09:00:03 ERROR pool 3 timeout\n"
        "2026-11-25 09:00:04 ERROR pool 4 timeout\n"
    )
    item = cluster(log)[0]
    assert len(item.samples) >= 2
    assert len(item.samples) <= 3


def test_template_share():
    log = make(
        "2026-11-25 09:00:01 ERROR boom\n"
        "2026-11-25 09:00:02 ERROR boom\n"
        "2026-11-25 09:00:03 INFO other\n"
        "2026-11-25 09:00:04 INFO other2\n"
    )
    clusters = cluster(log)
    top, share = template_share(clusters, log)
    assert top.count == 2
    assert share == pytest.approx(50.0)


def test_by_signature_index():
    log = make("2026-11-25 09:00:01 ERROR a\n2026-11-25 09:00:02 ERROR b 1\n")
    clusters = cluster(log)
    index = by_signature(clusters)
    assert set(index) == {c.signature for c in clusters}


def test_record_signature_cached():
    log = make("2026-11-25 09:00:01 ERROR boom 1\n")
    record = log.records[0]
    assert record.signature == ""
    first = record_signature(record)
    assert record.signature == first
    assert record_signature(record) == first


def test_order_by_count_then_first():
    log = make(
        "2026-11-25 09:00:01 INFO rare\n"
        "2026-11-25 09:00:02 INFO common 1\n"
        "2026-11-25 09:00:03 INFO common 2\n"
        "2026-11-25 09:00:04 INFO common 3\n"
    )
    clusters = cluster(log)
    assert clusters[0].count == 3
    assert clusters[1].count == 1


def test_empty_message_record():
    log = make("2026-11-25 09:00:01 INFO \n2026-11-25 09:00:02 INFO \n")
    clusters = cluster(log)
    assert len(clusters) == 1


def test_stack_is_not_in_signature():
    a = make(
        "2026-11-25 09:00:01 ERROR failed\n"
        "Traceback (most recent call last):\n"
        '  File "/a.py", line 1, in f\n'
    )
    b = make(
        "2026-11-25 09:00:02 ERROR failed\n"
        "Traceback (most recent call last):\n"
        '  File "/b.py", line 99, in g\n'
    )
    assert cluster(a)[0].signature == cluster(b)[0].signature


def test_korean_message_grouped():
    log = make(
        "2026-11-25 09:00:01 WARN 재고 부족: 상품 A-1042 남은 수량 2\n"
        "2026-11-25 09:00:02 WARN 재고 부족: 상품 B-9911 남은 수량 7\n"
    )
    clusters = cluster(log)
    assert len(clusters) == 1
    assert "재고 부족" in clusters[0].template


def test_hdfs_block_ids_grouped():
    log = make(
        "081109 203615 148 INFO dfs.DataNode$PacketResponder: "
        "PacketResponder 1 for block blk_38865049064139660 terminating\n"
        "081109 203807 222 INFO dfs.DataNode$PacketResponder: "
        "PacketResponder 0 for block blk_-6952295868487656571 terminating\n"
    )
    clusters = cluster(log)
    assert len(clusters) == 1
    assert "blk_<*>" in clusters[0].template
