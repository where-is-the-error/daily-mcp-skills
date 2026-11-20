"""명령줄 — 종료 코드가 계약이다 (0 통과 / 1 치명·심각 / 2 사용법·파일 오류)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from design_spec.cli import main

ROOT = Path(__file__).resolve().parent.parent
BEFORE = ROOT / "examples" / "demo" / "before.json"
AFTER = ROOT / "examples" / "demo" / "after.json"


def run(*argv: str) -> int:
    return main(list(argv))


def test_audit_returns_one_when_serious(capsys) -> None:
    assert run("audit", str(BEFORE)) == 1
    assert "점수" in capsys.readouterr().out


def test_audit_returns_zero_when_clean(capsys) -> None:
    assert run("audit", str(AFTER)) == 0


def test_audit_json(capsys) -> None:
    assert run("audit", str(BEFORE), "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["score"] == 0


def test_audit_rule_filter(capsys) -> None:
    run("audit", str(BEFORE), "--rules", "type-too-small")
    assert "type-too-small" not in capsys.readouterr().out or "위반 없음" in ""


def test_plan_exit_code(capsys) -> None:
    assert run("plan", str(BEFORE)) == 1
    assert "고치기 순서" in capsys.readouterr().out


def test_missing_file_exits_2(capsys) -> None:
    assert run("audit", "없는파일.json") == 2
    assert "⚠️" in capsys.readouterr().err


def test_broken_json_exits_2(tmp_path, capsys) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{oops", encoding="utf-8")
    assert run("audit", str(path)) == 2


def test_read_mode_and_depth(capsys) -> None:
    assert run("read", str(BEFORE), "--mode", "text", "--depth", "3") == 0
    assert "text" in capsys.readouterr().out


def test_find_text(capsys) -> None:
    assert run("find", str(BEFORE), "--text", "Button") == 0
    assert "ref=e" in capsys.readouterr().out


def test_find_no_match(capsys) -> None:
    assert run("find", str(BEFORE), "--text", "없는말") == 0
    assert "없습니다" in capsys.readouterr().out


def test_palette(capsys) -> None:
    assert run("palette", str(BEFORE)) == 0
    assert "#0057FF" in capsys.readouterr().out


def test_scale_spacing(capsys) -> None:
    assert run("scale", str(BEFORE), "--kind", "spacing") == 0
    assert "기준 4px" in capsys.readouterr().out


def test_scale_type(capsys) -> None:
    assert run("scale", str(BEFORE), "--kind", "type") == 0
    assert "6단계" in capsys.readouterr().out


def test_scale_radius(capsys) -> None:
    assert run("scale", str(BEFORE), "--kind", "radius") == 0
    assert "반경" in capsys.readouterr().out


def test_design_md_to_stdout(capsys) -> None:
    assert run("design-md", str(AFTER)) == 0
    assert "## 1. Visual Theme" in capsys.readouterr().out


def test_design_md_to_file(tmp_path) -> None:
    target = tmp_path / "DESIGN.md"
    assert run("design-md", str(AFTER), "--out", str(target)) == 0
    assert "Design System" in target.read_text(encoding="utf-8")


def test_rules_list(capsys) -> None:
    assert run("rules") == 0
    output = capsys.readouterr().out
    assert "contrast-text" in output
    assert output.count("근거:") == 17


def test_rules_single(capsys) -> None:
    assert run("rules", "touch-target") == 0
    assert "44" in capsys.readouterr().out


def test_rules_unknown_exits_2(capsys) -> None:
    assert run("rules", "없는규칙") == 2


def test_unknown_ref_exits_2(capsys) -> None:
    assert run("read", str(BEFORE), "--ref", "e999") == 2


def test_module_entrypoint_works() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "design_spec.cli", "audit", str(AFTER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0
    assert "100/100" in completed.stdout
