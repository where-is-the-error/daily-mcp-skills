"""기억 그래프 — 엔티티·관찰·관계."""

from __future__ import annotations

from web_memo import graph


def test_entity_type_detection() -> None:
    assert graph.entity_type("https://e.com/a") == "page"
    assert graph.entity_type("@someone") == "person"
    assert graph.entity_type("owner/repo") == "repo"
    assert graph.entity_type("배포 체크리스트") == "topic"


def test_annotate_creates_entity_and_note(conn) -> None:
    result = graph.annotate(conn, "https://e.com/a", "첫 메모")
    assert result.created_entity is True
    assert result.added_note is True
    assert result.notes[0].text == "첫 메모"


def test_same_note_is_not_duplicated(conn) -> None:
    graph.annotate(conn, "https://e.com/a", "같은 메모")
    again = graph.annotate(conn, "https://e.com/a", "같은 메모")
    assert again.added_note is False
    assert graph.graph_stats(conn)["observations"] == 1


def test_tags_create_relations(conn) -> None:
    result = graph.annotate(conn, "https://e.com/a", "메모", tags=["docs", "#api"])
    assert result.tags == ["docs", "api"]
    rels = graph.neighbors(conn, "https://e.com/a")
    assert ("tagged", "docs", "→") in rels
    assert ("tagged_by", "api", "←") in rels


def test_tags_are_idempotent(conn) -> None:
    graph.annotate(conn, "https://e.com/a", "", tags=["docs"])
    graph.annotate(conn, "https://e.com/a", "", tags=["docs"])
    assert graph.graph_stats(conn)["relations"] == 2  # tagged + tagged_by


def test_observations_newest_first(conn) -> None:
    graph.annotate(conn, "topic", "첫째")
    graph.annotate(conn, "topic", "둘째")
    notes = graph.observations(conn, "topic")
    assert [note.text for note in notes] == ["둘째", "첫째"]


def test_about_relation_to_source(conn) -> None:
    graph.annotate(conn, "배포 체크리스트", "금요일 금지", source="https://e.com/ops")
    rels = graph.neighbors(conn, "https://e.com/ops")
    assert ("about", "배포 체크리스트", "→") in rels


def test_empty_target_is_refused(conn) -> None:
    import pytest

    with pytest.raises(ValueError):
        graph.annotate(conn, "   ", "메모")


def test_graph_stats_counts(conn) -> None:
    graph.annotate(conn, "a", "메모", tags=["x"])
    stats = graph.graph_stats(conn)
    assert stats["entities"] >= 2
    assert stats["observations"] == 1
    assert stats["relations"] == 2
