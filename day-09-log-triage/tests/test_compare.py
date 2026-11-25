"""두 창 비교 — 새로 생긴 것과 드물게 한 번."""

from __future__ import annotations

import pytest

from conftest import AFTER, BEFORE, load_log, make
from log_triage.compare import compare, same_pair


def _log(spec: list[tuple[int, str]], minutes: int = 10):
    lines = []
    for minute, message in spec:
        lines.append(f"2026-11-25 09:{minute:02d}:01 {message}\n")
    return make("".join(lines))


def test_new_signature():
    before = _log([(0, "INFO ok 1"), (1, "INFO ok 2")])
    after = _log([(0, "INFO ok 1"), (1, "ERROR pool timeout 7")])
    result = compare(before, after, rare=1)
    new = result.with_status("new")
    assert len(new) == 1
    assert "pool timeout" in new[0].template
    assert new[0].before_count == 0


def test_rare_new_is_not_new():
    before = _log([(0, "INFO ok 1")])
    after = _log([(0, "INFO ok 1"), (1, "ERROR once only")])
    result = compare(before, after, rare=3)
    assert result.with_status("new") == []
    assert len(result.with_status("new-rare")) == 1


def test_gone_signature():
    before = _log([(0, "ERROR reset 1"), (1, "ERROR reset 2"), (2, "ERROR reset 3")])
    after = _log([(0, "INFO fine")])
    result = compare(before, after, rare=2)
    assert len(result.with_status("gone")) == 1


def test_rates_normalise_window_length():
    # before 는 10분, after 는 20분 — 개수는 같아도 비율은 절반
    before = make("".join(f"2026-11-25 09:{m:02d}:00 ERROR boom\n" for m in range(10)))
    after = make("".join(f"2026-11-25 09:{m:02d}:00 ERROR boom\n" for m in range(0, 20, 2)))
    result = compare(before, after)
    row = result.rows[0]
    assert row.before_count == row.after_count == 10
    assert row.before_rate == pytest.approx(1.0, rel=0.2)


def test_grew_status():
    before = make("".join(f"2026-11-25 09:{m:02d}:00 ERROR boom\n" for m in range(10)))
    after = make("".join(
        f"2026-11-25 09:{m:02d}:{s:02d} ERROR boom\n" for m in range(10) for s in range(5)
    ))
    result = compare(before, after)
    assert "grew" in {row.status for row in result.rows}


def test_shrank_status():
    before = make("".join(
        f"2026-11-25 09:{m:02d}:{s:02d} ERROR boom\n" for m in range(10) for s in range(5)
    ))
    after = make("".join(f"2026-11-25 09:{m:02d}:00 ERROR boom\n" for m in range(10)))
    result = compare(before, after)
    assert "shrank" in {row.status for row in result.rows}


def test_same_status():
    before = make("2026-11-25 09:00:00 ERROR boom\n2026-11-25 09:09:00 INFO ok\n")
    after = make("2026-11-25 10:00:00 ERROR boom\n2026-11-25 10:09:00 INFO ok\n")
    result = compare(before, after)
    statuses = {row.status for row in result.rows}
    assert "same" in statuses


def test_error_rate_change():
    before = make("2026-11-25 09:00:00 ERROR a\n2026-11-25 09:09:00 INFO b\n")
    after = make("".join(f"2026-11-25 09:{m:02d}:00 ERROR a\n" for m in range(10)))
    result = compare(before, after)
    assert result.error_rate_change > 1


def test_row_ratio_infinite_for_new():
    before = _log([(0, "INFO ok")])
    after = _log([(0, "ERROR fresh 1"), (1, "ERROR fresh 2"), (2, "ERROR fresh 3")])
    row = compare(before, after, rare=2).with_status("new")[0]
    assert row.ratio == float("inf")


def test_ordering_new_first():
    before = _log([(0, "ERROR old 1"), (1, "ERROR old 2"), (2, "ERROR old 3")])
    after = _log([
        (0, "ERROR newsh 1"), (1, "ERROR newsh 2"), (2, "ERROR newsh 3"),
        (3, "INFO ok"),
    ])
    result = compare(before, after, rare=2)
    assert result.rows[0].status in ("new", "grew")


def test_empty_before_is_all_new():
    after = _log([(0, f"INFO line {i}") for i in range(5)])
    result = compare(make(""), after)
    assert result.before_total == 0
    assert all(row.status.startswith("new") for row in result.rows)


def test_same_pair_on_identical_file():
    first = load_log(BEFORE)
    second = load_log(BEFORE)
    assert same_pair(first, second)


def test_real_incident_story():
    before = load_log(BEFORE)
    after = load_log(AFTER)
    result = compare(before, after)
    new = result.with_status("new")
    assert any("PoolTimeoutError" in row.template for row in new)
    assert any("ConnectionResetError" == row.template.split(":")[0].split("] ")[-1].strip()[:20]
               or "ConnectionResetError" in row.template
               for row in result.with_status("gone", "gone-rare"))
    assert result.error_rate_change > 10


def test_first_after_clock_recorded():
    before = _log([(0, "INFO ok")])
    after = make("2026-11-25 09:03:11 ERROR fresh 1\n2026-11-25 09:04:11 ERROR fresh 2\n"
                 "2026-11-25 09:05:11 ERROR fresh 3\n")
    row = compare(before, after, rare=2).with_status("new")[0]
    assert row.first_after.startswith("2026-11-25 09:03:11")
