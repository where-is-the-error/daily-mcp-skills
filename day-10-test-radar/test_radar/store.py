"""메모리 저장소 — 툴 사이에서 저장소와 변경집합을 ref 로 넘긴다.

파일을 쓰지 않는다. 서버가 죽으면 ref 도 사라진다(그게 맞다 — 다시 읽으면 된다).
"""

from __future__ import annotations

from pathlib import Path

from .graph import Repo
from .select import ChangeSet


class Store:
    def __init__(self) -> None:
        self.repos: dict[str, Repo] = {}
        self.sets: dict[str, ChangeSet] = {}
        self._repo_seq = 0
        self._set_seq = 0

    # -------------------------------------------------------------- repos
    def add_repo(self, repo: Repo) -> str:
        self._repo_seq += 1
        ref = f"repo-{self._repo_seq}"
        self.repos[ref] = repo
        return ref

    def get_repo(self, ref: str) -> Repo:
        repo = self.repos.get(ref)
        if repo is None:
            raise KeyError(f"저장소 ref 를 찾을 수 없습니다: {ref} (open_repo 로 먼저 읽으세요)")
        return repo

    def repo_stale(self, ref: str) -> str:
        repo = self.repos.get(ref)
        if repo is None:
            return ""
        if not Path(repo.root).exists():
            return f"{repo.root} 가 사라졌습니다 — 다시 open_repo 하세요"
        return ""

    # --------------------------------------------------------------- sets
    def add_set(self, change_set: ChangeSet) -> str:
        self._set_seq += 1
        ref = f"cs-{self._set_seq}"
        change_set.ref = ref
        self.sets[ref] = change_set
        return ref

    def get_set(self, ref: str) -> ChangeSet:
        change_set = self.sets.get(ref)
        if change_set is None:
            raise KeyError(f"변경집합 ref 를 찾을 수 없습니다: {ref} (read_diff 로 먼저 읽으세요)")
        return change_set

    def clear(self) -> None:
        self.repos.clear()
        self.sets.clear()
        self._repo_seq = 0
        self._set_seq = 0


STORE = Store()
