from __future__ import annotations

from pathlib import Path

import pytest

from repo_context import pack
from repo_context.sandbox import Sandbox


def test_pack_contains_every_section(sandbox: Sandbox) -> None:
    text = pack.context_pack(sandbox, max_tokens=1200)
    assert text.startswith("# repo-context")
    assert "## 최근 커밋" in text
    assert "## 지금 바뀐 파일" in text
    assert "## 핫 파일" in text
    assert "TODO / FIXME" in text
    assert "`main`" in text


def test_pack_never_leaks_secret_files(sandbox: Sandbox) -> None:
    text = pack.context_pack(sandbox, max_tokens=2000)
    assert "sk-should-not-leak" not in text
    assert "보안 파일 1개" in text


@pytest.mark.parametrize("budget", [200, 400, 800, 1200, 2000])
def test_pack_respects_budget(sandbox: Sandbox, budget: int) -> None:
    text = pack.context_pack(sandbox, max_tokens=budget)
    assert pack.estimate_tokens(text) <= budget


def test_small_budget_degrades_instead_of_failing(sandbox: Sandbox) -> None:
    text = pack.context_pack(sandbox, max_tokens=150)
    assert text.startswith("# repo-context")
    assert pack.estimate_tokens(text) <= 150


def test_pack_of_plain_directory(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "notes.txt").write_text("hi", encoding="utf-8")
    text = pack.context_pack(Sandbox.open(plain), max_tokens=300)
    assert "git 저장소가 아닙니다" in text
    assert "notes.txt" in text


def test_estimate_tokens_is_monotonic() -> None:
    assert pack.estimate_tokens("") == 0
    assert pack.estimate_tokens("abcd") == 1
    assert pack.estimate_tokens("한글") == 2
    assert pack.estimate_tokens("a" * 400) > pack.estimate_tokens("a" * 40)
