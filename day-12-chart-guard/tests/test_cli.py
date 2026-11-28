"""CLI — MCP 없이도 같은 검사를, 같은 종료 코드로."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chart_guard import cli

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def path(name: str) -> str:
    return str(EXAMPLES / name)


class TestRead:
    def test_prints_facts(self, capsys):
        assert cli.main(["read", path("before.json")]) == 0
        out = capsys.readouterr().out
        assert "차트 — 막대" in out
        assert "판정하지 않음" in out


class TestDistortion:
    def test_numbers(self, capsys):
        cli.main(["distortion", path("before.json")])
        out = capsys.readouterr().out
        assert "화면 길이비" in out
        assert "과장" in out


class TestCheck:
    def test_hold_exit_code(self, capsys):
        assert cli.main(["check", path("before.json")]) == 2
        out = capsys.readouterr().out
        assert "보류" in out
        assert "고치기 순서" in out

    def test_pass_exit_code(self, capsys):
        assert cli.main(["check", path("after.json")]) == 0
        assert "통과" in capsys.readouterr().out

    def test_warn_exit_code(self, tmp_path, capsys):
        spec = {
            "type": "bar",
            "categories": ["아주아주긴지역이름입니다", "또아주긴이름입니다"],
            "series": [{"name": "s", "values": [1, 2]}],
            "y": {"min": 0, "title": "값(개)"},
            "title": "긴 이름 두 곳의 값 비교",
            "source": "테스트",
            "alt": "막대 차트. 두 값 1개, 2개.",
            "font_px": 20,
            "width": 300,
        }
        file = tmp_path / "warn.json"
        file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        code = cli.main(["check", str(file)])
        out = capsys.readouterr().out
        assert code == 1
        assert "주의" in out

    def test_json_output(self, capsys):
        cli.main(["check", "--json", path("pie-before.json")])
        payload = json.loads(capsys.readouterr().out)
        assert payload["verdict"] == "hold"
        assert any(f["rule"] == "pie-too-many" for f in payload["findings"])


class TestFix:
    def test_json_spec(self, capsys):
        cli.main(["fix", path("before.json")])
        payload = json.loads(capsys.readouterr().out)
        assert payload["y"]["min"] == 0

    def test_pie_becomes_bar(self, capsys):
        cli.main(["fix", path("pie-before.json")])
        payload = json.loads(capsys.readouterr().out)
        assert payload["type"] == "bar"
        assert payload["categories"][-1] == "기타"


class TestAlt:
    def test_alt_and_table(self, capsys):
        cli.main(["alt", path("after.json")])
        out = capsys.readouterr().out
        assert "alt (" in out
        assert "| 구분 |" in out


class TestCompare:
    def test_before_after(self, capsys):
        cli.main(["compare", path("before.json"), path("after.json")])
        out = capsys.readouterr().out
        assert "전후 비교" in out
        assert "고쳐진 것" in out
        assert "잃은 값 없음" in out


class TestRules:
    def test_list(self, capsys):
        assert cli.main(["rules"]) == 0
        out = capsys.readouterr().out
        assert "규칙 41종" in out
        assert "bar-truncated-baseline" in out

    def test_one(self, capsys):
        cli.main(["rules", "three-d"])
        out = capsys.readouterr().out
        assert "3D" in out
        assert "bar-truncated-baseline" not in out

    def test_unknown(self, capsys):
        cli.main(["rules", "nope"])
        assert "그런 규칙이 없습니다" in capsys.readouterr().out


class TestOverview:
    def test_overview(self, capsys):
        assert cli.main(["overview"]) == 0
        out = capsys.readouterr().out
        assert "chart-guard" in out
        assert "규칙 41종" in out


class TestErrors:
    def test_missing_file(self, capsys):
        assert cli.main(["check", "/nope/nothing.json"]) == 3
        assert "⚠️" in capsys.readouterr().err

    def test_bad_spec(self, tmp_path, capsys):
        file = tmp_path / "bad.json"
        file.write_text("{\"hello\": 1}", encoding="utf-8")
        assert cli.main(["read", str(file)]) == 3
        assert "읽을 수 있는" in capsys.readouterr().err

    def test_no_command(self, capsys):
        assert cli.main([]) == 0
