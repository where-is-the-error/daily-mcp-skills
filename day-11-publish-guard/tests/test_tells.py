"""AI 글투 — 패턴·강도·겹침 규칙."""

from __future__ import annotations

import pytest

from conftest import CAPTION_GOOD
from publish_guard.tells import BY_ID, TELLS, active_hits, catalog, clean_for_scan, scan


class TestCatalog:
    def test_count(self):
        assert len(TELLS) == 21

    def test_ids_unique(self):
        assert len({tell.id for tell in TELLS}) == len(TELLS)

    def test_strong_and_weak(self):
        assert any(tell.strength == "strong" for tell in TELLS)
        assert any(tell.strength == "weak" for tell in TELLS)

    def test_weights_positive(self):
        assert all(tell.weight > 0 for tell in TELLS)

    def test_lookup(self):
        assert BY_ID["not-x-but-y"].strength == "strong"
        assert catalog("not-x-but-y")[0].title == "'X가 아니라 Y' 대구"
        assert catalog("없는규칙") == []
        assert len(catalog()) == 21


class TestEachTellMatchesItsExample:
    @pytest.mark.parametrize("tell", TELLS, ids=[tell.id for tell in TELLS])
    def test_before_matches(self, tell):
        hits = scan(tell.example_before)
        assert tell.id in {hit.id for hit in hits}, f"{tell.id} 가 자기 예시를 못 잡음"

    @pytest.mark.parametrize("tell", TELLS, ids=[tell.id for tell in TELLS])
    def test_after_is_clean(self, tell):
        if not tell.example_after:
            pytest.skip("빈 예시")
        hits = scan(tell.example_after)
        assert tell.id not in {hit.id for hit in hits}, f"{tell.id} 가 고친 예시도 잡음"


class TestCorroboration:
    def test_single_weak_is_inactive(self):
        hits = scan("결론적으로 정리하자면 이렇다.")
        summary = [hit for hit in hits if hit.id == "summary-closer"]
        assert summary and summary[0].active is False

    def test_two_weak_are_active(self):
        hits = scan("결론적으로 매우 좋다.")
        ids = {hit.id: hit.active for hit in hits}
        assert ids["summary-closer"] is True
        assert ids["empty-adverb"] is True

    def test_strong_alone_is_active(self):
        hits = scan("이것은 단순히 편집이 아니라 검사입니다.")
        hit = [h for h in hits if h.id == "not-x-but-y"][0]
        assert hit.active is True

    def test_include_weak_false(self):
        hits = scan("결론적으로 매우 좋다.", include_weak=False)
        assert all(hit.active is False for hit in hits if hit.tell.strength == "weak")

    def test_active_hits_filters(self):
        hits = scan("결론적으로 매우 좋다.")
        assert len(active_hits(hits)) == 2


class TestNoiseControl:
    def test_hashtags_are_stripped(self):
        hits = scan("#본질 #핵심은 #다양한")
        assert hits == []

    def test_links_are_stripped(self):
        hits = scan("https://example.com/본질적인-이야기")
        assert [h.id for h in hits if h.id == "deep-saying"] == []

    def test_clean_caption_has_no_active_hits(self):
        hits = scan(CAPTION_GOOD)
        assert active_hits(hits) == []

    def test_plain_caption_is_clean(self):
        assert active_hits(scan("피크가 -0.2 dBTP라 소리가 깨진다. loudnorm으로 -1.5까지 내린다.")) == []

    def test_dash_needs_two(self):
        assert "dash-overuse" not in {h.id for h in scan("검사—업로드")}
        assert "dash-overuse" in {h.id for h in scan("검사—업로드—확인")}

    def test_exclamation_needs_two(self):
        assert "exclamation" not in {h.id for h in scan("됩니다!")}
        assert "exclamation" in {h.id for h in scan("됩니다!!")}

    def test_clean_for_scan_leaves_text(self):
        assert "본문" in clean_for_scan("본문 #태그 https://a.b")


class TestHits:
    def test_matches_are_deduplicated(self):
        hits = scan("결론적으로. 결론적으로. 매우.")
        summary = [h for h in hits if h.id == "summary-closer"][0]
        assert summary.matches.count("결론적으로") == 1

    def test_matches_capped(self):
        hits = scan("! " * 10)
        exclamation = [h for h in hits if h.id == "exclamation"][0]
        assert len(exclamation.matches) == 1  # 같은 스니펫은 하나

    def test_sorted_strong_first(self):
        hits = scan("단순히 편집이 아니라 검사입니다. 결론적으로 매우.")
        assert hits[0].tell.strength == "strong"

    def test_english_patterns(self):
        hits = scan("This is not just a tool but a mirror.")
        assert "not-x-but-y" in {h.id for h in hits}

    def test_english_stock_word(self):
        hits = scan("Let us delve into the landscape.")
        assert "stock-words" in {h.id for h in hits}

    def test_english_curly_quote(self):
        assert "curly-quotes" in {h.id for h in scan("“hello”")}
