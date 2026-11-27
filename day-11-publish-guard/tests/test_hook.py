"""훅 검사 — 첫 줄이 결론인지 예고인지."""

from __future__ import annotations

import pytest

from publish_guard.hook import check_hook


def rules(hook: str, first_line: str = "", language: str = "ko"):
    return {finding.rule for finding in check_hook(hook, first_line, language)}


class TestEmpty:
    def test_empty_is_block(self):
        findings = check_hook("")
        assert len(findings) == 1
        assert findings[0].severity == "block"
        assert findings[0].rule == "hook-empty"

    def test_whitespace_empty(self):
        assert rules("   ") == {"hook-empty"}


class TestLength:
    def test_short_ok(self):
        assert "hook-too-long" not in rules("12초면 끝난다")

    def test_long_ko(self):
        assert "hook-too-long" in rules("올리기 전에 아주 길게 설명하는 문장입니다 열여덟자를 넘깁니다")

    def test_long_en(self):
        hook = "This hook is definitely far too long for the first one and a half seconds of video"
        assert "hook-too-long" in rules(hook, language="en")

    def test_en_limit_is_larger(self):
        hook = "a" * 30
        assert "hook-too-long" not in rules(hook, language="en")
        assert "hook-too-long" in rules(hook, language="ko")


class TestOpeners:
    @pytest.mark.parametrize("hook", ["안녕하세요 여러분", "오늘은 소리 얘기", "요즘 릴스는", "여러분 이거 보세요"])
    def test_vague_ko(self, hook):
        assert "hook-vague-opener" in rules(hook)

    @pytest.mark.parametrize("hook", ["Hi everyone", "Hello there", "Hey guys"])
    def test_vague_en(self, hook):
        assert "hook-vague-opener" in rules(hook, language="en")

    def test_passive_promise(self):
        assert "hook-passive-promise" in rules("릴스 검사법을 알아보겠습니다")

    def test_let_us_talk(self):
        assert "hook-passive-promise" in rules("let's talk about audio", language="en")

    def test_conclusion_first_passes(self):
        found = rules("피크가 넘으면 소리가 깨진다")
        assert "hook-vague-opener" not in found
        assert "hook-passive-promise" not in found


class TestConcreteness:
    def test_number_is_concrete(self):
        assert "hook-no-concrete" not in rules("10편 중 4편이 걸린다")

    def test_arrow_is_concrete(self):
        assert "hook-no-concrete" not in rules("34 → 100")

    def test_vague_claim(self):
        assert "hook-no-concrete" in rules("검사가 중요하다")

    def test_percent_is_concrete(self):
        assert "hook-no-concrete" not in rules("4편 중 3편이 40% 틀렸다")


class TestOther:
    def test_question_note(self):
        assert "hook-question" in rules("왜 소리가 깨질까?")

    def test_duplicated_in_first_line(self):
        assert "hook-duplicated" in rules("12초면 끝난다", first_line="12초면 끝난다. 정말로")

    def test_not_duplicated(self):
        assert "hook-duplicated" not in rules("12초면 끝난다", first_line="다른 문장")

    def test_clean_hook_has_no_findings(self):
        assert check_hook("10편 중 4편이 피크 초과", "어제 릴스 10편을 쟀다", "ko") == []

    def test_weights(self):
        findings = check_hook("안녕하세요 오늘은 검사가 중요합니다")
        total = sum(f.weight for f in findings)
        assert total == 15 + 6  # 인사 + 구체성 없음 (길이는 18자 이하)
