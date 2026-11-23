"""CLI — 여덟 명령과 게이트 종료 코드."""

from __future__ import annotations

import pytest

from conftest import EXAMPLES, FIXED, RISKY, SCHEMA, STATS
from migrate_guard.cli import build_parser, main


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def common() -> list[str]:
    return ["--baseline", str(SCHEMA), "--rows", str(STATS)]


def test_parser_lists_commands() -> None:
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"][0]
    assert set(actions.choices) == {
        "summary", "statements", "locks", "risk", "rollout", "rollback", "schema", "compare", "rules",
    }


def test_summary(capsys) -> None:
    code, out, _ = run(capsys, "summary", str(RISKY), *common())
    assert code == 0
    assert "판정 **보류**" in out
    assert "events" in out


def test_summary_mentions_assumed_rows(capsys) -> None:
    code, out, _ = run(capsys, "summary", str(RISKY), "--baseline", str(SCHEMA))
    assert code == 0
    assert "100,000행으로 가정" in out


def test_statements(capsys) -> None:
    code, out, _ = run(capsys, "statements", str(RISKY), *common())
    assert code == 0
    assert "s3 · 줄 6 · alter_type" in out


def test_statements_max_items(capsys) -> None:
    code, out, _ = run(capsys, "statements", str(RISKY), "--max-items", "2", *common())
    assert code == 0
    assert "개 더" in out


def test_locks(capsys) -> None:
    code, out, _ = run(capsys, "locks", str(RISKY), *common())
    assert code == 0
    assert "ACCESS EXCLUSIVE" in out
    assert "락 유지 합계" in out


def test_risk(capsys) -> None:
    code, out, _ = run(capsys, "risk", str(RISKY), *common())
    assert code == 0
    assert "치명" in out


def test_risk_severity_filter(capsys) -> None:
    code, out, _ = run(capsys, "risk", str(RISKY), "--severity", "치명", *common())
    assert code == 0
    assert "심각 ·" not in out


def test_risk_bad_severity(capsys) -> None:
    code, _, err = run(capsys, "risk", str(RISKY), "--severity", "아무거나", *common())
    assert code == 1
    assert "치명" in err


def test_gate_blocks_risky(capsys) -> None:
    code, _, err = run(capsys, "risk", str(RISKY), "--fail-on", "치명", *common())
    assert code == 2
    assert "게이트" in err


def test_gate_passes_fixed(capsys) -> None:
    code, _, _ = run(capsys, "risk", str(FIXED), "--fail-on", "치명", *common())
    assert code == 0


def test_gate_rejects_unknown_threshold(capsys) -> None:
    code, _, err = run(capsys, "risk", str(FIXED), "--fail-on", "없는등급", *common())
    assert code == 1
    assert "치명" in err


def test_rollout_prints(capsys) -> None:
    code, out, _ = run(capsys, "rollout", str(RISKY), *common())
    assert code == 0
    assert "1단계" in out
    assert "CREATE INDEX CONCURRENTLY" in out


def test_rollout_writes_file(capsys, tmp_path) -> None:
    target = tmp_path / "fixed.sql"
    code, out, _ = run(capsys, "rollout", str(RISKY), "--out", str(target), *common())
    assert code == 0
    assert target.exists()
    assert "CONCURRENTLY" in target.read_text(encoding="utf-8")


def test_rollback_prints(capsys) -> None:
    code, out, _ = run(capsys, "rollback", str(RISKY), "--baseline", str(SCHEMA))
    assert code == 0
    assert "되돌리기 SQL" in out


def test_rollback_writes_file(capsys, tmp_path) -> None:
    target = tmp_path / "down.sql"
    code, _, _ = run(capsys, "rollback", str(RISKY), "--baseline", str(SCHEMA), "--out", str(target))
    assert code == 0
    assert target.read_text(encoding="utf-8").startswith("--")


def test_schema(capsys) -> None:
    code, out, _ = run(capsys, "schema", str(RISKY), "--baseline", str(SCHEMA))
    assert code == 0
    assert "사라지는 컬럼: sessions.legacy_token" in out
    assert "text → jsonb" in out


def test_compare(capsys) -> None:
    code, out, _ = run(capsys, "compare", str(RISKY), str(FIXED), *common())
    assert code == 0
    assert "치명: 3 → 0" in out


def test_rules(capsys) -> None:
    code, out, _ = run(capsys, "rules")
    assert code == 0
    assert "판정하지 않는 것" in out
    assert "drop-table" in out


def test_missing_file(capsys) -> None:
    code, _, err = run(capsys, "summary", "없는파일.sql")
    assert code == 1
    assert "찾지 못했습니다" in err


def test_examples_exist() -> None:
    for path in (SCHEMA, RISKY, FIXED, STATS):
        assert path == path and path.exists()


def test_stdin_like_sql_string(capsys) -> None:
    sql = "CREATE INDEX idx ON users (phone);"
    code, out, _ = run(capsys, "summary", sql, "--baseline", str(SCHEMA))
    assert code == 0
    assert "판정" in out
