"""AI 글투 목록 — 강한 신호는 한 번만 보여도 고치고, 약한 신호는 겹칠 때만 고친다.

번호와 태도는 참고한 스킬에서 가져왔지만, 패턴·문장·예시는 이 캡션 검사에 맞게 새로 썼다.
캡션은 짧다. 그래서 '한 번 나왔다고 다 고치기'는 오탐이 되기 쉽다 — 강도와 겹침을 함께 본다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .caption import HASHTAG_RE, LINK_RE, emoji_count


@dataclass(frozen=True)
class Tell:
    id: str
    strength: str  # strong | weak
    weight: int
    title: str
    pattern: str
    why: str
    fix: str
    example_before: str
    example_after: str
    min_count: int = 1
    flags: int = re.IGNORECASE | re.MULTILINE

    @property
    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


TELLS: tuple[Tell, ...] = (
    Tell(
        id="not-x-but-y",
        strength="strong",
        weight=6,
        title="'X가 아니라 Y' 대구",
        pattern=r"(?:단순히|그저|그냥|다만)\s*[^.\n]{1,30}?(?:이|가|은|는)?\s*아니라"
        r"|(?:이|가)\s*아니라\s*[^.\n]{1,30}(?:이다|입니다)"
        r"|\bnot\s+(?:just|only|merely)\b[^.\n]{1,60}?\bbut\b"
        r"|\bnot\b[^.\n]{1,40}?\bit'?s\b",
        why="부정한 쪽은 아무도 주장하지 않은 것이라, 앞뒤를 붙여 강조만 키운다.",
        fix="부정을 걷어내고 Y만 말한다. 독자가 실제로 믿는 것을 바로잡을 때만 대구를 남긴다.",
        example_before="편집이 아니라 검사입니다.",
        example_after="올리기 전에 12초만 재보세요.",
    ),
    Tell(
        id="one-line-closer",
        strength="strong",
        weight=5,
        title="한 줄 마무리·강조 조각",
        pattern=r"(?:그게|이게|그것이)\s*(?:전부|핵심|답)|다시\s*읽어|이게\s*전부다"
        r"|\bthat'?s the (?:real )?(?:win|point|whole)\b|\bread that again\b|\blet that sink in\b",
        why="바로 앞 문장을 다시 말할 뿐 새 사실을 더하지 않는다.",
        fix="앞 문장에 없던 사실이나 결과를 붙이거나, 문장을 지운다.",
        example_before="그게 핵심이다.",
        example_after="피크가 -0.2 dBTP라 업로드하면 소리가 찌그러진다.",
    ),
    Tell(
        id="deep-saying",
        strength="strong",
        weight=5,
        title="깊어 보이는 상투구",
        pattern=r"본질(?:은|적인|이다)|진짜\s*질문|핵심은\s*[^.\n]{1,25}"
        r"|\bat its core\b|\bthe real question\b|\bheart of the matter\b"
        r"|\bthe language of\b|\bthe currency of\b",
        why="평범한 말을 숨은 진실처럼 포장한다.",
        fix="상투구를 걷어내고 구체적인 주장으로 바꾼다.",
        example_before="핵심은 소리다.",
        example_after="소리가 -14 LUFS를 넘으면 플랫폼이 볼륨을 낮춘다.",
    ),
    Tell(
        id="staged-opener",
        strength="strong",
        weight=5,
        title="본론 전 준비 동작",
        pattern=r"^(?:자|이제|그럼)[,\s]+(?:이제\s*)?(?:알아보|살펴보|시작|보겠)|본격적으로"
        r"|\blet'?s dive in\b|\bhere'?s what you need to know\b|\bnow let'?s look\b",
        why="본론을 말하기 전에 본론을 예고하며 한 줄을 쓴다.",
        fix="예고를 지우고 첫 문장을 결론으로 시작한다.",
        example_before="자, 이제 알아보겠습니다.",
        example_after="21.5초, 1080×1920, -11.7 LUFS. 셋 중 하나가 걸린다.",
    ),
    Tell(
        id="inflated-significance",
        strength="strong",
        weight=4,
        title="부풀린 수식",
        pattern=r"혁신적|완벽한|압도적|게임\s*체인저|패러다임"
        r"|\brevolutionary\b|\bgame-?chang(?:er|ing)\b|\bseamless(?:ly)?\b"
        r"|\btransformative\b|\bcutting-edge\b|\belevate\b",
        why="크기를 키우는 말이 사실을 대신한다.",
        fix="수식 대신 잰 값이나 비교 대상을 쓴다.",
        example_before="혁신적인 검사 도구",
        example_after="업로드 전 12초 검사",
    ),
    Tell(
        id="sales-language",
        strength="strong",
        weight=4,
        title="판매 문구",
        pattern=r"지금\s*바로|놓치지\s*마|단\s*\d+\s*원|\blimited[- ]time\b|\bact now\b"
        r"|\bdon'?t miss\b|\bwhile supplies last\b",
        why="정보가 아니라 재촉이다.",
        fix="재촉을 지우고 무엇이 바뀌는지 적는다.",
        example_before="지금 바로 확인하세요",
        example_after="다음 업로드 전에 한 번 돌려보세요",
    ),
    Tell(
        id="ordinal-triad",
        strength="strong",
        weight=4,
        title="첫째·둘째·셋째 나열",
        pattern=r"첫째[^\n]{0,200}?둘째[^\n]{0,200}?셋째|\bfirst(?:ly)?\b[^\n]{0,200}?\bsecond(?:ly)?\b[^\n]{0,200}?\bthird(?:ly)?\b",
        why="내용이 셋이라서가 아니라 리듬 때문에 셋으로 맞춘 나열이다.",
        fix="꼭 필요한 항목만 남기고, 개수를 내용에 맡긴다.",
        example_before="첫째, 둘째, 셋째로 정리했습니다.",
        example_after="막는 것 두 가지: 피크와 첫 문장.",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    ),
    Tell(
        id="bold-label",
        strength="strong",
        weight=3,
        title="장식용 굵은 글씨·라벨",
        pattern=r"\*\*[^*\n]{1,40}\*\*|__[^_\n]{1,40}__|【[^】]{1,30}】",
        why="모든 항목에 굵게를 붙이면 아무것도 강조되지 않는다.",
        fix="정말 중요한 한 곳만 남기거나 굵게를 모두 뺀다.",
        example_before="**핵심**: **소리**",
        example_after="소리부터 본다",
    ),
    Tell(
        id="chatbot-residue",
        strength="strong",
        weight=5,
        title="챗봇 잔여 문구",
        pattern=r"도움이\s*되(?:셨길|었길)|궁금한\s*점(?:이)?\s*있으면"
        r"|\bas an ai\b|\bi hope this helps\b|\blet me know if\b|\bfeel free to\b",
        why="대화창에서 쓰던 말이 게시물에 그대로 남았다.",
        fix="지운다. 캡션은 독자에게 하는 말이다.",
        example_before="도움이 되셨길 바랍니다.",
        example_after="",
    ),
    Tell(
        id="knowledge-disclaimer",
        strength="strong",
        weight=4,
        title="지식 한계 변명",
        pattern=r"제\s*(?:지식|학습)\s*기준|최신\s*정보가\s*아닐"
        r"|\bas of my knowledge\b|\bi (?:don'?t|do not) have access\b|\bmy training data\b",
        why="독자에게 필요 없는 모델 사정이다.",
        fix="지우고, 확인한 날짜와 출처를 적는다.",
        example_before="제 지식 기준으로는",
        example_after="2026-11-27 확인",
    ),
    Tell(
        id="dash-overuse",
        strength="weak",
        weight=3,
        title="쉼표 대신 쓰는 대시",
        pattern=r"[—–]",
        why="생각을 이어 붙이는 대시가 반복되면 문장이 다 비슷해진다.",
        fix="두 번까지로 줄이고, 나머지는 문장을 끊는다.",
        example_before="검사—업로드—확인",
        example_after="검사하고 올리고 확인한다.",
        min_count=2,
    ),
    Tell(
        id="stock-words",
        strength="weak",
        weight=3,
        title="상투 단어",
        pattern=r"다양한|중요한|필수적|\bcrucial\b|\bvital\b|\bdelve\b|\blandscape\b"
        r"|\btapestry\b|\brobust\b|\bleverage\b|\bmyriad\b|\bplethora\b",
        why="어떤 주제에나 붙는 말이라 정보가 없다.",
        fix="그 자리에 실제 대상·숫자·행동을 넣는다.",
        example_before="다양한 기능",
        example_after="LUFS·피크·길이 세 가지",
    ),
    Tell(
        id="hedge-stack",
        strength="weak",
        weight=2,
        title="겹친 완곡 표현",
        pattern=r"(?:할|될)\s*수\s*있습니다|것\s*같습니다|라고\s*할\s*수\s*있"
        r"|\bit (?:can|could) be (?:argued|said)\b|\barguably\b",
        why="확신을 흐려서 결론을 뒤로 미룬다.",
        fix="확인한 것은 단정하고, 모르는 것은 모른다고 쓴다.",
        example_before="도움이 될 수 있습니다",
        example_after="피크가 0.8 dB 넘으면 걸린다",
    ),
    Tell(
        id="meta-narration",
        strength="weak",
        weight=3,
        title="글 자체를 설명하는 문장",
        pattern=r"이번\s*(?:글|영상|포스팅)에서는|지금부터"
        r"|\bin this (?:post|video|article)\b|\bbelow,? (?:we|i)\b",
        why="독자는 이미 그 글을 읽고 있다.",
        fix="문장을 지우고 내용으로 들어간다.",
        example_before="이번 영상에서는 세 가지를 봅니다.",
        example_after="피크, 길이, 첫 문장 순서로 본다.",
    ),
    Tell(
        id="exclamation",
        strength="weak",
        weight=2,
        title="느낌표 반복",
        pattern=r"!",
        why="강조 부호가 반복되면 문장의 힘을 부호가 대신한다.",
        fix="한 번만 남기거나 모두 뺀다.",
        example_before="진짜 됩니다!!",
        example_after="됩니다.",
        min_count=2,
    ),
    Tell(
        id="summary-closer",
        strength="weak",
        weight=3,
        title="결론 예고 마무리",
        pattern=r"결론적으로|마무리하(?:겠|면)|정리하자면"
        r"|\bin conclusion\b|\bultimately\b|\bto sum up\b",
        why="이미 말한 것을 다시 묶는 데 한 줄을 쓴다.",
        fix="지우거나, 마지막에 새로 알게 된 결과를 붙인다.",
        example_before="결론적으로, 검사가 중요합니다.",
        example_after="검사에서 걸린 3건, 다 고치고 올렸다.",
    ),
    Tell(
        id="empty-adverb",
        strength="weak",
        weight=2,
        title="빈 부사",
        pattern=r"매우|정말로|아주|\bextremely\b|\bincredibly\b|\babsolutely\b",
        why="정도를 부사로만 말하면 얼마나인지 알 수 없다.",
        fix="부사를 지우고 숫자나 비교로 바꾼다.",
        example_before="매우 조용합니다",
        example_after="-18.4 LUFS입니다",
    ),
    Tell(
        id="borrowed-authority",
        strength="weak",
        weight=3,
        title="출처 없는 권위",
        pattern=r"전문가들은|연구에\s*따르면|조사에\s*따르면|\bexperts say\b"
        r"|\bstudies show\b|\bresearch shows\b",
        why="누가 그랬는지 없으면 확인할 수 없다.",
        fix="기관·문서·날짜를 붙이거나 문장을 뺀다.",
        example_before="전문가들은 그렇게 말합니다.",
        example_after="YouTube 도움말은 3분이라고 적는다.",
    ),
    Tell(
        id="vague-association",
        strength="weak",
        weight=2,
        title="'~에 대해' 돌려 말하기",
        pattern=r"와\s*관련하여|에\s*대해\s*(?:살펴|알아)|\bwhen it comes to\b|\bwith regard to\b",
        why="동사를 피해 문장을 늘린다.",
        fix="동사를 바로 쓴다.",
        example_before="소리에 대해 살펴봅니다",
        example_after="소리를 잰다",
    ),
    Tell(
        id="passive-voice",
        strength="weak",
        weight=2,
        title="주체 없는 수동",
        pattern=r"되어집니다|여겨집니다|간주됩니다|\bit is (?:believed|thought|said) that\b",
        why="누가 하는지 사라져서 문장이 흐려진다.",
        fix="주체를 앞에 세운다.",
        example_before="검사가 요구되어집니다",
        example_after="업로드 전에 검사한다",
    ),
    Tell(
        id="curly-quotes",
        strength="weak",
        weight=1,
        title="굽은 따옴표",
        pattern=r"[\u2018\u2019\u201c\u201d]",
        why="편집기에서 온 흔적이라 손으로 쓴 글과 결이 다르다.",
        fix="곧은 따옴표로 바꾸거나 인용을 없앤다.",
        example_before="“검사”",
        example_after="\"검사\"",
    ),
)

BY_ID = {tell.id: tell for tell in TELLS}


@dataclass(frozen=True)
class TellHit:
    tell: Tell
    matches: tuple[str, ...]
    active: bool

    @property
    def id(self) -> str:
        return self.tell.id


def clean_for_scan(text: str) -> str:
    text = LINK_RE.sub(" ", text)
    text = HASHTAG_RE.sub(" ", text)
    return text


def scan(text: str, include_weak: bool = True) -> list[TellHit]:
    haystack = clean_for_scan(text)
    raw: list[tuple[Tell, tuple[str, ...]]] = []
    for tell in TELLS:
        found = tell.compiled.findall(haystack)
        if len(found) < tell.min_count:
            continue
        snippets: list[str] = []
        for match in tell.compiled.finditer(haystack):
            snippet = match.group(0).strip().replace("\n", " ")
            if snippet and snippet not in snippets:
                snippets.append(snippet[:60])
            if len(snippets) >= 5:
                break
        raw.append((tell, tuple(snippets)))

    weak_ids = {tell.id for tell, _ in raw if tell.strength == "weak"}
    corroborated = len(weak_ids) >= 2
    hits: list[TellHit] = []
    for tell, snippets in raw:
        if tell.strength == "strong":
            active = True
        else:
            active = include_weak and corroborated
        hits.append(TellHit(tell=tell, matches=snippets, active=active))
    hits.sort(key=lambda hit: (hit.tell.strength != "strong", -hit.tell.weight, hit.tell.id))
    return hits


def active_hits(hits: Iterable[TellHit]) -> list[TellHit]:
    return [hit for hit in hits if hit.active]


def catalog(tell_id: str = "") -> list[Tell]:
    if tell_id:
        tell = BY_ID.get(tell_id)
        return [tell] if tell else []
    return list(TELLS)


def emoji_pressure(text: str) -> int:
    return emoji_count(text)
