"""규칙 색인 — 파일·화면·훅·캡션 규칙의 id 와 설명, 그리고 AI 글투 목록."""

from __future__ import annotations

from dataclasses import dataclass

from .tells import TELLS


@dataclass(frozen=True)
class RuleDoc:
    id: str
    category: str
    severity: str
    title: str
    doc: str


FILE_RULES: tuple[RuleDoc, ...] = (
    RuleDoc("duration-over", "file", "block", "길이 상한 초과", "플랫폼이 짧은 영상으로 받지 않거나 잘라내는 길이."),
    RuleDoc("duration-over-reach", "file", "warn", "도달 권고선 초과", "규정은 아니지만 새 시청자에게 덜 권해지는 길이(Reels 3분)."),
    RuleDoc("duration-under", "file", "block", "길이 하한 미달", "업로드 API 가 거부하는 최소 길이."),
    RuleDoc("not-vertical", "file", "block", "세로가 아님", "Shorts 는 세로·정사각만 짧은 영상으로 분류한다."),
    RuleDoc("resolution-below-min", "file", "block", "해상도 하한 미달", "플랫폼이 요구하는 최소 폭보다 작다."),
    RuleDoc("resolution-above-max", "file", "note", "상한보다 큰 해상도", "업로드해도 줄어드는 해상도."),
    RuleDoc("fps-below-min", "file", "warn", "프레임레이트 낮음", "플랫폼 최소 fps 보다 낮다."),
    RuleDoc("fps-above-max", "file", "warn", "프레임레이트 높음", "플랫폼 상한 fps 보다 높다."),
    RuleDoc("file-too-big", "file", "block", "파일 크기 초과", "API 업로드 상한을 넘는다."),
    RuleDoc("no-audio", "file", "warn", "오디오 없음", "오디오 스트림이 없다."),
    RuleDoc("loudness-unmeasured", "file", "note", "음량 미측정", "오디오는 있는데 통합 음량을 읽지 못했다."),
    RuleDoc("silent-audio", "file", "block", "무음 트랙", "오디오는 있지만 완전 무음이다."),
    RuleDoc("loudness-hot", "file", "warn", "소리가 크다", "목표 -14 LUFS 보다 1.5 LU 이상 크다."),
    RuleDoc("loudness-quiet", "file", "warn", "소리가 작다", "목표 -14 LUFS 보다 1.5 LU 이상 작다."),
    RuleDoc("true-peak-over", "file", "block", "트루피크 초과", "+-1.0 dBTP 를 넘어 인코딩에서 찌그러질 수 있다."),
    RuleDoc("true-peak-near", "file", "warn", "트루피크 여유 없음", "-1.5 dBTP 보다 높아 여유가 없다."),
    RuleDoc("head-silence", "file", "warn", "앞이 조용하다", "시작 0.5초 넘게 무음이다."),
    RuleDoc("tail-silence", "file", "warn", "끝이 조용하다", "마지막 1초 넘게 무음이라 루프가 끊긴다."),
    RuleDoc("rotation-metadata", "file", "warn", "회전 메타데이터", "회전 플래그에 기대고 있어 플랫폼이 무시하면 눕는다."),
    RuleDoc("codec-uncommon", "file", "note", "덜 흔한 코덱", "세 플랫폼 모두 H.264 를 권한다."),
    RuleDoc("pixfmt-uncommon", "file", "note", "픽셀 포맷", "yuv420p 가 가장 안전하다."),
    RuleDoc("audio-codec", "file", "note", "오디오 코덱", "AAC-LC 가 가장 안전하다."),
    RuleDoc("audio-sample-rate", "file", "note", "샘플레이트", "44.1/48kHz 가 일반적이다."),
    RuleDoc("low-bitrate", "file", "note", "낮은 비트레이트", "정지 화면 위주면 정상일 수 있는 낮은 비트레이트."),
    RuleDoc("safe-zone-*", "safe", "block", "문구가 UI 에 걸림", "선언된 문구 상자가 상단·하단·우측 버튼 영역과 겹친다."),
    RuleDoc("box-outside-canvas", "safe", "warn", "화면 밖 문구", "상자 일부가 화면 밖으로 나갔다."),
    RuleDoc("hook-empty", "hook", "block", "훅 없음", "첫 1.5초에 띄울 문구가 없다."),
    RuleDoc("hook-too-long", "hook", "warn", "훅이 길다", "1.5초 안에 읽히지 않는 길이."),
    RuleDoc("hook-vague-opener", "hook", "block", "인사로 시작", "인사·배경으로 첫 1.5초를 쓴다."),
    RuleDoc("hook-passive-promise", "hook", "block", "'알아보겠습니다'형 예고", "결론 대신 예고를 놓는다."),
    RuleDoc("hook-no-concrete", "hook", "warn", "숫자·비교 없음", "훅에 잰 값이나 대비가 없다."),
    RuleDoc("hook-question", "hook", "note", "질문형 훅", "질문으로 끝나 결론이 늦다."),
    RuleDoc("hook-duplicated", "hook", "note", "캡션과 겹침", "훅이 캡션 첫 줄에 그대로 들어 있다."),
    RuleDoc("caption-empty", "copy", "block", "캡션 없음", "올릴 글이 없다."),
    RuleDoc("caption-too-long", "copy", "block", "캡션 길이 초과", "플랫폼 캡션 상한을 넘는다."),
    RuleDoc("hashtag-over-limit", "copy", "block", "해시태그 상한 초과", "플랫폼이 받지 않는 개수."),
    RuleDoc("hashtag-spam", "copy", "warn", "해시태그가 많다", "권고 개수를 넘어 검색 신호가 흐려진다."),
    RuleDoc("hashtag-none", "copy", "warn", "해시태그 없음", "검색으로 발견될 단서가 없다."),
    RuleDoc("hashtag-generic", "copy", "warn", "아무 데나 붙는 해시태그", "#fyp #shorts #reels 처럼 주제를 가리지 않는 태그."),
    RuleDoc("link-in-caption", "copy", "note", "캡션 안 링크", "Reels 캡션의 링크는 눌리지 않는다."),
    RuleDoc("first-line-hashtag", "copy", "warn", "첫 줄이 해시태그", "접힌 캡션에서 보이는 유일한 줄을 해시태그에 쓴다."),
    RuleDoc("emoji-spam", "copy", "note", "이모지가 많다", "이모지가 8개를 넘는다."),
    RuleDoc("keyword-missing", "copy", "warn", "앞부분에 키워드 없음", "찾을 말이 캡션 앞 125자에 없다."),
)


def rules() -> tuple[RuleDoc, ...]:
    tell_rules = tuple(
        RuleDoc(
            id=f"tell-{tell.id}",
            category="copy",
            severity="warn" if tell.strength == "strong" else "note",
            title=tell.title,
            doc=(
                f"{tell.why} ({'한 번만 봐도 고침' if tell.strength == 'strong' else '둘 이상 겹칠 때만 고침'}) "
                f"예: '{tell.example_before}' → '{tell.example_after}'"
            ),
        )
        for tell in TELLS
    )
    return FILE_RULES + tell_rules


def catalog(rule_id: str = "") -> list[RuleDoc]:
    if rule_id:
        return [rule for rule in rules() if rule.id == rule_id]
    return list(rules())


def counts() -> dict[str, int]:
    out = {"file": 0, "safe": 0, "hook": 0, "copy": 0, "total": 0}
    for rule in rules():
        out[rule.category] += 1
        out["total"] += 1
    return out
