"""명령줄 — CI 에서 쓰는 경로. 종료 코드가 계약이다."""

from __future__ import annotations

import json

import pytest

from a11y_lens.cli import main

BAD = """<html><body><main><h1>가</h1><img src="a.png"><h5>나</h5></main></body></html>"""
GOOD = """<html lang="ko"><head><title>t</title></head><body><main><h1>가</h1><img src="a.png" alt="그림"></main></body></html>"""


@pytest.fixture
def bad_path(tmp_path):
    path = tmp_path / "bad.html"
    path.write_text(BAD, encoding="utf-8")
    return path


@pytest.fixture
def good_path(tmp_path):
    path = tmp_path / "good.html"
    path.write_text(GOOD, encoding="utf-8")
    return path


def test_snapshot_command(bad_path, capsys) -> None:
    assert main(["snapshot", str(bad_path)]) == 0
    out = capsys.readouterr().out
    assert "heading" in out
    assert "ref=e" in out


def test_snapshot_without_source_lines(bad_path, capsys) -> None:
    main(["snapshot", str(bad_path), "--no-source"])
    assert "L" not in capsys.readouterr().out


def test_audit_command_returns_1_for_critical(bad_path, capsys) -> None:
    assert main(["audit", str(bad_path)]) == 1
    assert "점수" in capsys.readouterr().out


def test_audit_command_returns_0_when_clean(good_path, capsys) -> None:
    assert main(["audit", str(good_path)]) == 0
    assert "위반은 없습니다" in capsys.readouterr().out


def test_audit_json_flag(bad_path, capsys) -> None:
    main(["audit", str(bad_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["path"].endswith("bad.html")


def test_audit_directory(site, capsys) -> None:
    assert main(["audit", str(site)]) == 1
    assert "사이트 검사" in capsys.readouterr().out


def test_audit_rule_filter(bad_path, capsys) -> None:
    main(["audit", str(bad_path), "--rules", "image-alt", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert {v["rule"] for v in data["violations"]} == {"image-alt"}


def test_plan_command(bad_path, capsys) -> None:
    assert main(["plan", str(bad_path)]) == 0
    assert "고치기 순서" in capsys.readouterr().out


def test_plan_clean(good_path, capsys) -> None:
    assert main(["plan", str(good_path)]) == 0
    assert "✅" in capsys.readouterr().out


def test_verify_save_then_check(bad_path, good_path, lens_home, capsys) -> None:
    assert main(["verify", str(bad_path), "--baseline", "cli", "--save"]) == 0
    assert "기준선 저장" in capsys.readouterr().out
    assert main(["verify", str(good_path), "--baseline", "cli"]) == 0
    out = capsys.readouterr().out
    assert "✅" in out


def test_verify_regression_returns_1(tmp_path, lens_home, capsys) -> None:
    good_path = tmp_path / "g.html"
    good_path.write_text(GOOD, encoding="utf-8")
    main(["verify", str(good_path), "--baseline", "x", "--save"])
    broken = tmp_path / "b.html"
    broken.write_text("<html><body><main><h1>가</h1><iframe src='x'></iframe></main></body></html>", encoding="utf-8")
    assert main(["verify", str(broken), "--baseline", "x"]) == 1


def test_verify_json_summary(bad_path, lens_home, capsys) -> None:
    main(["verify", str(bad_path), "--baseline", "j", "--save"])
    capsys.readouterr()
    main(["verify", str(bad_path), "--baseline", "j", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["baseline_count"] == data["current_count"]


def test_verify_missing_baseline(bad_path, lens_home, capsys) -> None:
    assert main(["verify", str(bad_path), "--baseline", "없음"]) == 2
    assert "⚠️" in capsys.readouterr().err


def test_rules_listing(capsys) -> None:
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "규칙 20종" in out
    assert "image-alt" in out


def test_rules_single(capsys) -> None:
    assert main(["rules", "form-label"]) == 0
    out = capsys.readouterr().out
    assert "WCAG 3.3.2" in out
    assert "placeholder" in out


def test_rules_unknown(capsys) -> None:
    assert main(["rules", "nope"]) == 2


def test_missing_file_exit_code(capsys) -> None:
    assert main(["audit", "없는파일.html"]) == 2
    assert "⚠️" in capsys.readouterr().err


def test_unknown_rule_in_audit(bad_path, capsys) -> None:
    assert main(["audit", str(bad_path), "--rules", "nope"]) == 2
