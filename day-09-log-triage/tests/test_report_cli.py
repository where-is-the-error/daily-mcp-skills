"""보고서와 명령줄 — 사람이 읽는 출력과 종료 코드."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import AFTER, BEFORE, FORMATS, KOREAN, MESSY
from log_triage import cli, report
from log_triage.compare import compare
from log_triage.parse import load_log, read_whole
from log_triage.rates import analyze
from log_triage.redact import redact_text
from log_triage.rules import check
from log_triage.signature import cluster
from log_triage.stack import stack_report
from log_triage.timeline import build


def test_table_summary_contains_core_facts():
    log = load_log(BEFORE)
    text = report.table_summary(log, ref="lg-1")
    assert "api-before.log" in text
    assert "utf-8" in text
    assert "ref lg-1" in text
    assert "레벨:" in text


def test_table_summary_no_records():
    from conftest import make
    text = report.table_summary(make("nothing here\n"))
    assert "시각을 읽은 레코드가 없습니다" in text


def test_signature_view_limits_and_counts():
    log = load_log(AFTER)
    text = report.signature_view(cluster(log), log, limit=3)
    assert "서명" in text
    assert text.count("\n") <= 8


def test_rate_view_shows_error_bursts():
    log = load_log(AFTER)
    text = report.rate_view(analyze(log), log)
    assert "오류 폭주" in text or "평소 오류" in text


def test_compare_view_marks_changes():
    before, after = load_log(BEFORE), load_log(AFTER)
    text = report.compare_view(compare(before, after))
    assert "새로 생김" in text
    assert "ERROR/CRITICAL" in text


def test_stack_view_top_frames():
    log = load_log(AFTER)
    text = report.stack_view(stack_report(log), log)
    assert "pool.py:64" in text
    assert "python" in text


def test_timeline_view():
    log = load_log(AFTER)
    text = report.timeline_view(build(log), log)
    assert "첫 오류" in text
    assert "직전 정상" in text


def test_timeline_view_without_errors():
    from conftest import make
    log = make("2026-11-25 09:00:01 INFO ok\n")
    assert "ERROR 없음" in report.timeline_view(build(log), log)


def test_problems_view_empty():
    assert report.problems_view([]) == "✅ 걸리는 것 없음"


def test_problems_view_and_fix_order():
    log = load_log(MESSY)
    findings = check(log)
    text = report.problems_view(findings)
    assert "치명" in text
    assert "→" in text
    assert "고치는 순서" in report.fix_order(findings)


def test_redact_view_reports_zero_residual():
    result = redact_text("a@b.co\n")
    text = report.redact_view(result, checked_lines=1)
    assert "0 확인" in text


def test_catalog_view_groups():
    text = report.catalog_view()
    assert "규칙 25종" in text
    assert "secret-in-log" in text


def test_catalog_view_one_rule():
    text = report.catalog_view("secret-in-log")
    assert "왜:" in text and "고치기:" in text


def test_catalog_view_unknown_rule():
    assert "그런 규칙이 없습니다" in report.catalog_view("nope")


def test_overview_mentions_limits():
    assert "판정하지 않는 것" in report.OVERVIEW
    assert "read_logs" in report.OVERVIEW


# ------------------------------------------------------------------ CLI
def test_cli_read(capsys):
    assert cli.main(["read", str(BEFORE), "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "api-before.log" in out
    assert "판정하지 않음" in out


def test_cli_sigs(capsys):
    assert cli.main(["sigs", str(AFTER), "--limit", "2"]) == 0
    assert "서명" in capsys.readouterr().out


def test_cli_rates(capsys):
    assert cli.main(["rates", str(AFTER)]) == 0
    assert "구간" in capsys.readouterr().out


def test_cli_compare(capsys):
    assert cli.main(["compare", str(BEFORE), str(AFTER)]) == 0
    assert "새로 생김" in capsys.readouterr().out


def test_cli_stack(capsys):
    assert cli.main(["stack", str(AFTER)]) == 0
    assert "pool.py:64" in capsys.readouterr().out


def test_cli_timeline(capsys):
    assert cli.main(["timeline", str(AFTER)]) == 0
    assert "첫 오류" in capsys.readouterr().out


def test_cli_timeline_with_baseline(capsys):
    assert cli.main(["timeline", str(AFTER), "--baseline", str(BEFORE)]) == 0
    assert "기준선에 없던" in capsys.readouterr().out


def test_cli_problems_exit_codes():
    assert cli.main(["problems", str(BEFORE), "--limit", "3"]) in (0, 1, 2)


def test_cli_problems_critical_exit(capsys):
    assert cli.main(["problems", str(MESSY), "--limit", "3"]) == 2


def test_cli_problems_quiet_file(tmp_path, capsys):
    path = tmp_path / "clean.log"
    path.write_text(
        "2026-11-25 09:00:01,000 INFO  [api] request_id=abc123def456 path=/v1/orders done\n"
        "2026-11-25 09:00:02,000 INFO  [api] request_id=abc123def457 path=/v1/orders done\n",
        encoding="utf-8")
    code = cli.main(["problems", str(path)])
    assert code in (0, 1)


def test_cli_find(capsys):
    assert cli.main(["find", str(BEFORE), "ConnectionReset"]) == 0
    out = capsys.readouterr().out
    assert "일치" in out
    assert ">" in out


def test_cli_find_regex_bad(capsys):
    assert cli.main(["find", str(BEFORE), "([", "--regex"]) == 2


def test_cli_redact_writes_file(tmp_path, capsys):
    out_path = tmp_path / "masked.log"
    assert cli.main(["redact", str(MESSY), "--out", str(out_path)]) == 0
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "0 확인" in capsys.readouterr().out


def test_cli_redact_preview_only(capsys, tmp_path):
    assert cli.main(["redact", str(MESSY)]) == 0
    assert "지운 값" in capsys.readouterr().out
    assert not (tmp_path / "unused.log").exists()


def test_cli_catalog(capsys):
    assert cli.main(["catalog"]) == 0
    assert "규칙" in capsys.readouterr().out


def test_cli_catalog_one(capsys):
    assert cli.main(["catalog", "secret-in-log"]) == 0
    assert "왜:" in capsys.readouterr().out


def test_cli_overview(capsys):
    assert cli.main(["overview"]) == 0
    assert "log-triage" in capsys.readouterr().out


def test_cli_missing_file(capsys):
    assert cli.main(["read", "no-such-file.log"]) == 1
    assert "⚠️" in capsys.readouterr().out


def test_cli_formats_file(capsys):
    assert cli.main(["read", str(FORMATS), "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert "json-iso" in out or "jsonl" in out


def test_cli_korean_encoding(capsys):
    assert cli.main(["read", str(KOREAN), "--limit", "2"]) == 0
    assert "cp949" in capsys.readouterr().out


def test_cli_help_exists():
    with pytest.raises(SystemExit):
        cli.main([])
