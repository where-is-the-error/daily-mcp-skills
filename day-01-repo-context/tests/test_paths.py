"""쪼개진 저장소에서도 경로가 어긋나지 않는지 — git은 저장소 루트 기준으로,
샌드박스는 자기 루트 기준으로 말한다."""

from __future__ import annotations

from pathlib import Path

from repo_context import gitio, pack, views
from repo_context.sandbox import Sandbox

from conftest import git


def _monorepo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "mono"
    (root / "pkg").mkdir(parents=True)
    (root / "root.txt").write_text("root\n", encoding="utf-8")
    (root / "pkg" / "core.py").write_text("def run():\n    # TODO: 테스트\n    pass\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feat: 둘 다")
    return root, root / "pkg"


def test_subdirectory_sandbox_rebases_paths(tmp_path: Path) -> None:
    root, pkg = _monorepo(tmp_path)
    sandbox = Sandbox.open(pkg)

    commits = gitio.recent_commits(sandbox)
    assert commits[0].files == ("core.py",)
    assert gitio.tracked_files(sandbox) == ["core.py"]

    state = gitio.repo_state(sandbox)
    assert state.is_repo is True
    assert state.commit_count == 1

    overview = views.render_overview(sandbox)
    assert "core.py" in overview
    assert "root.txt" not in overview


def test_subdirectory_pack_reads_files(tmp_path: Path) -> None:
    _root, pkg = _monorepo(tmp_path)
    sandbox = Sandbox.open(pkg)
    text = pack.context_pack(sandbox, max_tokens=800)
    assert "core.py" in text
    assert "TODO — 테스트" in text
    assert "root.txt" not in text


def test_repository_inside_sandbox(tmp_path: Path) -> None:
    root, _pkg = _monorepo(tmp_path)
    sandbox = Sandbox.open(tmp_path)
    assert gitio.is_repo(sandbox) is False  # 샌드박스 루트 자체는 저장소가 아니다
    assert "mono/pkg/core.py" in gitio.tracked_files(sandbox, "mono")
    assert "mono/root.txt" in gitio.tracked_files(sandbox, "mono")
    assert root.name == "mono"
