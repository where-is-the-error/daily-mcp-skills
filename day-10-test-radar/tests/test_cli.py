"""명령줄 — 실제 저장소를 만들고 diff 를 넣어 종료 코드까지 본다."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import SHOP, make_diff
from test_radar import cli


@pytest.fixture()
def project(tmp_path) -> Path:
    for path, text in SHOP.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def write_patch(tmp_path: Path, text: str, name: str = "change.patch") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run(argv: list[str]) -> int:
    return cli.main(argv)


def test_rules_output(capsys) -> None:
    assert run(["rules"]) == 0
    out = capsys.readouterr().out
    assert "test-config-changed" in out
    assert "규칙" not in out or "치명" in out


def test_rules_json(capsys) -> None:
    assert run(["rules", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 23


def test_rules_filter(capsys) -> None:
    assert run(["rules", "dynamic-import"]) == 0
    assert "동적 import" in capsys.readouterr().out


def test_rules_unknown(capsys) -> None:
    assert run(["rules", "nope"]) == 1
    assert "없습니다" in capsys.readouterr().out


def test_help_without_command(capsys) -> None:
    assert run([]) == 1
    assert "scan" in capsys.readouterr().out


def test_scan_patch(project, tmp_path, capsys) -> None:
    patch = write_patch(tmp_path, make_diff(
        "shop/pricing.py", SHOP["shop/pricing.py"], SHOP["shop/pricing.py"].replace("0.1", "0.2")))
    code = run(["scan", str(project), "--diff", str(patch)])
    out = capsys.readouterr().out
    assert code in (0, 2)
    assert "test-radar" in out
    assert "판정" in out


def test_scan_changes_hunks(project, tmp_path, capsys) -> None:
    patch = write_patch(tmp_path, make_diff(
        "shop/cart.py", SHOP["shop/cart.py"], SHOP["shop/cart.py"] + "\n# x\n"))
    run(["scan", str(project), "--diff", str(patch), "--changes", "--hunks"])
    out = capsys.readouterr().out
    assert "변경 1개 파일" in out
    assert "@@" in out


def test_scan_json(project, tmp_path, capsys) -> None:
    patch = write_patch(tmp_path, make_diff(
        "shop/pricing.py", SHOP["shop/pricing.py"], SHOP["shop/pricing.py"].replace("0.1", "0.2")))
    run(["scan", str(project), "--diff", str(patch), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["diff"]["files"] == 1
    assert payload["selection"]["files"] >= 1
    assert payload["verdict"]
    assert payload["limits"]


def test_scan_fatal_exit_code(project, tmp_path, capsys) -> None:
    patch = write_patch(tmp_path, make_diff(
        "tests/conftest.py", SHOP["tests/conftest.py"], SHOP["tests/conftest.py"] + "\n# x\n"))
    assert run(["scan", str(project), "--diff", str(patch)]) == 2


def test_scan_missing_repo(capsys) -> None:
    assert run(["scan", "/없는/저장소", "--diff", "-"]) == 1
    assert "없습니다" in capsys.readouterr().out


def test_scan_garbage_diff(project, tmp_path, capsys) -> None:
    patch = write_patch(tmp_path, "not a diff at all\n")
    assert run(["scan", str(project), "--diff", str(patch)]) == 1
    assert "읽지 못했습니다" in capsys.readouterr().out


def test_scan_without_diff(project, capsys) -> None:
    with pytest.raises(SystemExit):
        run(["scan", str(project)])


def test_scan_stdin(project, monkeypatch, capsys) -> None:
    import io
    diff = make_diff("shop/pricing.py", SHOP["shop/pricing.py"],
                     SHOP["shop/pricing.py"].replace("0.1", "0.2"))
    monkeypatch.setattr("sys.stdin", io.StringIO(diff))
    code = run(["scan", str(project), "--diff", "-"])
    assert code in (0, 2)
    assert "선택:" in capsys.readouterr().out


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)


@pytest.fixture()
def git_project(tmp_path) -> Path:
    project = tmp_path / "repo"
    project.mkdir()
    for path, text in SHOP.items():
        target = project / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "t")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "init")
    return project


def test_scan_git_base(git_project, capsys) -> None:
    (git_project / "shop" / "pricing.py").write_text(
        SHOP["shop/pricing.py"].replace("0.1", "0.3"), encoding="utf-8")
    code = run(["scan", str(git_project), "--base", "HEAD"])
    out = capsys.readouterr().out
    assert code in (0, 2)
    assert "shop/pricing.py" in out


def test_scan_git_staged(git_project, capsys) -> None:
    (git_project / "shop" / "cart.py").write_text(SHOP["shop/cart.py"] + "\n# x\n", encoding="utf-8")
    _git(git_project, "add", "-A")
    code = run(["scan", str(git_project), "--base", "HEAD", "--staged"])
    assert code in (0, 2)
    assert "변경 1개 파일" in capsys.readouterr().out


def test_scan_git_bad_base(git_project) -> None:
    with pytest.raises(SystemExit) as caught:
        run(["scan", str(git_project), "--base", "없는브랜치"])
    assert "git diff" in str(caught.value)
