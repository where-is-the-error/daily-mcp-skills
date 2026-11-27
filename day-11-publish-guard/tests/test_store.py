"""작업 기억 — ref 발급과 오류."""

from __future__ import annotations

import pytest

from conftest import make_media
from publish_guard.caption import read_caption
from publish_guard.store import Store
from publish_guard.types import Report


@pytest.fixture
def store():
    return Store()


class TestStore:
    def test_media_refs(self, store):
        assert store.add_media(make_media()) == "m-1"
        assert store.add_media(make_media()) == "m-2"
        assert store.media("m-1").width == 1080

    def test_caption_refs(self, store):
        assert store.add_caption(read_caption("문장")) == "c-1"
        assert store.caption("c-1").text == "문장"

    def test_report_refs(self, store):
        report = Report(media=None, caption=None, platforms=("tiktok",))
        assert store.add_report(report) == "r-1"
        assert report.ref == "r-1"
        assert store.report("r-1") is report

    def test_missing_media(self, store):
        with pytest.raises(KeyError, match="read_media"):
            store.media("m-9")

    def test_missing_caption(self, store):
        with pytest.raises(KeyError, match="read_caption"):
            store.caption("c-9")

    def test_missing_report(self, store):
        with pytest.raises(KeyError, match="publish_check"):
            store.report("r-9")

    def test_counts(self, store):
        store.add_media(make_media())
        store.add_caption(read_caption("문장"))
        assert store.counts() == {"media": 1, "captions": 1, "reports": 0}

    def test_clear(self, store):
        store.add_media(make_media())
        store.clear()
        assert store.counts()["media"] == 0
        assert store.add_media(make_media()) == "m-1"
