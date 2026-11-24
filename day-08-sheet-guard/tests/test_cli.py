"""CLI — 종료 코드까지 확인한다."""

from __future__ import annotations

from pathlib import Path

from sheet_guard.cli import main


def clean_csv(tmp_path: Path) -> Path:
    path = tmp_path / "clean.csv"
    path.write_text("이름,나이\n김,31\n이,28\n", encoding="utf-8")
    return path


def test_read(raw_path, capsys) -> None:
    assert main(["read", str(raw_path)]) == 0
    out = capsys.readouterr().out
    assert "raw_population.csv" in out
    assert "CP949" in out


def test_problems_exit_two_on_error(raw_path, capsys) -> None:
    assert main(["problems", str(raw_path)]) == 2
    assert "치명" in capsys.readouterr().out


def test_problems_clean_exit_zero(tmp_path, capsys) -> None:
    assert main(["problems", str(clean_csv(tmp_path))]) == 0
    assert "찾지 못했습니다" in capsys.readouterr().out


def test_problems_severity_filter(raw_path, capsys) -> None:
    main(["problems", str(raw_path), "--severity", "error"])
    out = capsys.readouterr().out
    assert "subtotal-row" in out
    assert "thousands-separator" not in out


def test_plan(raw_path, capsys) -> None:
    assert main(["plan", str(raw_path)]) == 2
    out = capsys.readouterr().out
    assert "정리 계획" in out
    assert "행 빼기" in out


def test_clean_writes_files(raw_path, tmp_path, capsys) -> None:
    out_path = tmp_path / "clean.csv"
    assert main(["clean", str(raw_path), "--out", str(out_path)]) == 0
    assert out_path.exists()
    assert (tmp_path / "clean.changes.csv").exists()
    assert (tmp_path / "clean.ragged.csv").exists()
    text = capsys.readouterr().out
    assert "적용 완료" in text
    assert "격리" in text


def test_clean_dry_run(raw_path, tmp_path, capsys) -> None:
    out_path = tmp_path / "clean.csv"
    assert main(["clean", str(raw_path), "--out", str(out_path), "--dry-run"]) == 0
    assert not out_path.exists()
    assert "파일을 쓰지 않았습니다" in capsys.readouterr().out


def test_clean_only_rule(raw_path, tmp_path) -> None:
    out_path = tmp_path / "sub.csv"
    main(["clean", str(raw_path), "--out", str(out_path), "--only", "subtotal-row"])
    text = out_path.read_text(encoding="utf-8-sig")
    assert "소계" not in text
    assert "1,234" in text or "132,456" in text     # 다른 규칙은 그대로


def test_md(raw_path, capsys) -> None:
    assert main(["md", str(raw_path), "--max-rows", "3"]) == 0
    out = capsys.readouterr().out
    assert "| 시도 |" in out


def test_md_clean(raw_path, capsys) -> None:
    main(["md", str(raw_path), "--clean", "--max-rows", "3"])
    out = capsys.readouterr().out
    assert "면적_단위" in out


def test_compare(raw_path, tmp_path, capsys) -> None:
    out_path = tmp_path / "c.csv"
    main(["clean", str(raw_path), "--out", str(out_path)])
    capsys.readouterr()
    assert main(["compare", str(raw_path), str(out_path)]) == 0
    assert "정리 전" in capsys.readouterr().out


def test_rules_list(capsys) -> None:
    assert main(["rules"]) == 0
    assert "duplicate-rows" in capsys.readouterr().out


def test_rules_one(capsys) -> None:
    assert main(["rules", "date-format-mixed"]) == 0
    assert "왜:" in capsys.readouterr().out


def test_rules_unknown(capsys) -> None:
    assert main(["rules", "없는규칙"]) == 1


def test_missing_file(tmp_path, capsys) -> None:
    assert main(["read", str(tmp_path / "없음.csv")]) == 1


def test_profile(raw_path, capsys) -> None:
    assert main(["profile", str(raw_path)]) == 0
    out = capsys.readouterr().out
    assert "우편번호" in out
