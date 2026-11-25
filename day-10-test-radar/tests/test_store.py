"""ref 저장소 — 툴 사이에서 무엇을 넘기는가."""

from __future__ import annotations

import pytest

from test_radar.graph import load_sources
from test_radar.store import Store


def test_repo_ref_sequence() -> None:
    store = Store()
    repo = load_sources({"a.py": "x = 1\n"})
    assert store.add_repo(repo) == "repo-1"
    assert store.add_repo(repo) == "repo-2"


def test_get_repo() -> None:
    store = Store()
    repo = load_sources({"a.py": "x = 1\n"})
    ref = store.add_repo(repo)
    assert store.get_repo(ref) is repo


def test_missing_repo() -> None:
    store = Store()
    with pytest.raises(KeyError) as caught:
        store.get_repo("repo-9")
    assert "open_repo" in str(caught.value)


def test_set_ref_sequence() -> None:
    from test_radar.select import ChangeSet
    store = Store()
    first = store.add_set(ChangeSet())
    second = store.add_set(ChangeSet())
    assert (first, second) == ("cs-1", "cs-2")


def test_set_ref_written_back() -> None:
    from test_radar.select import ChangeSet
    store = Store()
    change_set = ChangeSet()
    ref = store.add_set(change_set)
    assert change_set.ref == ref


def test_missing_set() -> None:
    store = Store()
    with pytest.raises(KeyError) as caught:
        store.get_set("cs-3")
    assert "read_diff" in str(caught.value)


def test_repo_stale_after_delete(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    from test_radar.graph import load
    repo = load(tmp_path)
    store = Store()
    ref = store.add_repo(repo)
    assert store.repo_stale(ref) == ""
    tmp_path.rename(tmp_path.with_name(tmp_path.name + "-moved"))
    assert "다시" in store.repo_stale(ref)


def test_clear() -> None:
    store = Store()
    store.add_repo(load_sources({"a.py": "x = 1\n"}))
    store.clear()
    assert store.repos == {} and store.sets == {}
    assert store.add_repo(load_sources({"a.py": "x = 1\n"})) == "repo-1"
