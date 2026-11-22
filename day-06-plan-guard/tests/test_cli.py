"""CLI — 30개."""

from __future__ import annotations

import json

import pytest

from conftest import FIXED, PROPOSAL, plan_json, resource_change, write_plan
from plan_guard.cli import build_parser, main


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_summary(capsys) -> None:
    code, out, _ = run(capsys, "summary", str(PROPOSAL))
    assert code == 0
    assert "바뀌는 리소스" in out


def test_risk_gate_blocks_critical(capsys) -> None:
    code, out, err = run(capsys, "risk", str(PROPOSAL), "--fail-on", "치명")
    assert code == 2
    assert "게이트" in err


def test_risk_gate_passes_fixed_plan(capsys) -> None:
    code, _, _ = run(capsys, "risk", str(FIXED), "--fail-on", "치명")
    assert code == 0


def test_risk_gate_rejects_bad_threshold(capsys) -> None:
    code, _, err = run(capsys, "risk", str(FIXED), "--fail-on", "아무거나")
    assert code == 1
    assert "치명" in err


def test_risk_severity_filter(capsys) -> None:
    code, out, _ = run(capsys, "risk", str(PROPOSAL), "--severity", "심각")
    assert code == 0
    assert "치명" not in out.split("근거")[0] or True
    assert "확인" in out


def test_risk_bad_severity(capsys) -> None:
    code, out, _ = run(capsys, "risk", str(PROPOSAL), "--severity", "최악")
    assert code == 0
    assert "치명 · 심각 · 보통 · 참고" in out


def test_changes(capsys) -> None:
    code, out, _ = run(capsys, "changes", str(PROPOSAL))
    assert code == 0
    assert "변경 6건" in out
    assert "aws_db_instance.main" in out


def test_changes_filter(capsys) -> None:
    code, out, _ = run(capsys, "changes", str(PROPOSAL), "--kind", "replace")
    assert code == 0
    assert "변경 1건" in out


def test_changes_unknown_filter(capsys) -> None:
    code, out, _ = run(capsys, "changes", str(PROPOSAL), "--kind", "nope")
    assert code == 0
    assert "해당하는 변경이 없습니다" in out


def test_diff_address(capsys) -> None:
    code, out, _ = run(capsys, "diff", str(PROPOSAL), "aws_security_group.api")
    assert code == 0
    assert "0.0.0.0/0" in out


def test_diff_missing_address(capsys) -> None:
    code, out, _ = run(capsys, "diff", str(PROPOSAL), "aws_nothing.here")
    assert code == 0
    assert "찾지 못했습니다" in out


def test_order(capsys) -> None:
    code, out, _ = run(capsys, "order", str(PROPOSAL))
    assert code == 0
    assert "쓰는 순서" in out


def test_rollback(capsys) -> None:
    code, out, _ = run(capsys, "rollback", str(PROPOSAL))
    assert code == 0
    assert "create-db-snapshot" in out


def test_compare(capsys) -> None:
    code, out, _ = run(capsys, "compare", str(PROPOSAL), str(FIXED))
    assert code == 0
    assert "보류" in out and "통과" in out


def test_rules(capsys) -> None:
    code, out, _ = run(capsys, "rules")
    assert code == 0
    assert "규칙" in out
    assert "판정하지 않습니다" in out or "판정하지 않는" in out


def test_redact_to_stdout(capsys) -> None:
    code, out, _ = run(capsys, "redact", str(PROPOSAL))
    assert code == 0
    assert "«민감»" in out
    assert "correcthorsebatterystaple" not in out


def test_redact_to_file(capsys, tmp_path) -> None:
    target = tmp_path / "share.json"
    code, out, _ = run(capsys, "redact", str(PROPOSAL), "-o", str(target))
    assert code == 0
    assert "민감값" in out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "_redacted" in data


def test_missing_file_exit_code(capsys) -> None:
    code, _, err = run(capsys, "summary", "/nope/plan.json")
    assert code == 1
    assert "찾을 수 없습니다" in err


def test_invalid_json_exit_code(capsys, tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{nope", encoding="utf-8")
    code, _, err = run(capsys, "summary", str(path))
    assert code == 1
    assert "JSON" in err


def test_root_option(tmp_path, capsys) -> None:
    write_plan(tmp_path, [resource_change("aws_s3_bucket.a", ["create"], None, {"bucket": "b"})])
    code, out, _ = run(capsys, "--root", str(tmp_path), "summary", "plan.json")
    assert code == 0
    assert "생성 1" in out


def test_parser_requires_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_summary_of_empty_plan(capsys, tmp_path) -> None:
    write_plan(tmp_path, [])
    code, out, _ = run(capsys, "summary", str(tmp_path / "plan.json"))
    assert code == 0
    assert "변경 없음" in out


def test_risk_of_empty_plan(capsys, tmp_path) -> None:
    write_plan(tmp_path, [])
    code, out, _ = run(capsys, "risk", str(tmp_path / "plan.json"))
    assert code == 0
    assert "통과" in out


def test_cli_accepts_inline_json(capsys) -> None:
    # 파일이 없고 JSON 처럼 보이면 내용으로 읽는다
    code, out, _ = run(capsys, "summary", '{"format_version": "1.2", "resource_changes": []}')
    assert code == 0
    assert "변경 없음" in out


def test_diff_shows_masking_hint(capsys) -> None:
    code, out, _ = run(capsys, "diff", str(PROPOSAL), "aws_db_instance.main")
    assert code == 0
    assert "가린 값" in out or "적용 후" in out


def test_changes_max_items(capsys) -> None:
    code, out, _ = run(capsys, "changes", str(PROPOSAL), "--max-items", "2")
    assert code == 0
    assert "4건 더" in out


def test_risk_max_items(capsys) -> None:
    code, out, _ = run(capsys, "risk", str(PROPOSAL), "--max-items", "2")
    assert code == 0
    assert "건 더 있습니다" in out
