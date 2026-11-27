"""첫 1.5초 훅 검사 — 첫 줄이 결론인지, 예고인지.

영상의 첫 프레임에 실제로 무엇이 보이는지는 읽지 않는다. 편집본이 선언한 훅 문구만 본다.
"""

from __future__ import annotations

import re

from .types import Finding

VAGUE_OPENERS = re.compile(
    r"^(?:안녕하세요|안녕하십니까|반갑습니다|오늘은|요즘|여러분|이번\s*영상|이번\s*시간"
    r"|\bhi\b|\bhello\b|\bhey\b|\bwelcome\b|\bwhat'?s up\b)",
    re.IGNORECASE,
)
PASSIVE_OPENERS = re.compile(
    r"알아보겠습니다|살펴보겠습니다|소개합니다|다뤄보겠습니다|정리해\s*보겠습니다"
    r"|\blet'?s talk about\b|\bwe'?ll look at\b|\bin this video\b",
    re.IGNORECASE,
)
CONCRETE = re.compile(r"\d|%|→|->|×|vs\.?|=", re.IGNORECASE)

KO_LIMIT = 18
EN_LIMIT = 48


def check_hook(hook: str, first_line: str = "", language: str = "ko", window_s: float = 1.5) -> list[Finding]:
    hook = (hook or "").strip()
    first_line = (first_line or "").strip()
    plain = re.sub(r"\s+", "", hook)
    findings: list[Finding] = []

    if not hook:
        return [
            Finding(
                rule="hook-empty",
                category="hook",
                severity="block",
                weight=20,
                title="첫 줄이 비었다",
                message=f"첫 {window_s}초에 띄울 문구가 없다. 이 시리즈의 훅 규칙은 '첫 1.5초 안에 결론'이다.",
                fix="숫자나 결과가 들어간 결론 한 줄을 첫 프레임에 넣는다 (한글 12자 안팎).",
            )
        ]

    limit = EN_LIMIT if language == "en" else KO_LIMIT
    if len(plain) > limit:
        findings.append(
            Finding(
                rule="hook-too-long",
                category="hook",
                severity="warn",
                weight=8,
                title="훅이 길다",
                message=f"공백 제외 {len(plain)}자 (권고 {limit}자 이하). 1.5초 안에 다 읽히지 않는다.",
                fix="결론만 남기고 수식·인사·배경을 걷어낸다.",
            )
        )

    if VAGUE_OPENERS.search(hook):
        findings.append(
            Finding(
                rule="hook-vague-opener",
                category="hook",
                severity="block",
                weight=15,
                title="인사·배경으로 시작한다",
                message=f"'{VAGUE_OPENERS.search(hook).group(0)}'(으)로 시작한다. 첫 1.5초를 인사에 쓴다.",
                fix="인사를 지우고 결론부터 말한다.",
            )
        )

    if PASSIVE_OPENERS.search(hook):
        findings.append(
            Finding(
                rule="hook-passive-promise",
                category="hook",
                severity="block",
                weight=12,
                title="'알아보겠습니다'형 예고",
                message="무엇을 말할지 예고만 하고 결론은 뒤로 미룬다.",
                fix="예고를 결론으로 바꾼다. 예: '알아보겠습니다' → '피크가 넘으면 소리가 깨진다'.",
            )
        )

    if not CONCRETE.search(hook):
        findings.append(
            Finding(
                rule="hook-no-concrete",
                category="hook",
                severity="warn",
                weight=6,
                title="숫자·비교가 없다",
                message="훅에 숫자·비교·결과 기호가 하나도 없다. 무엇이 달라지는지 보이지 않는다.",
                fix="잰 값이나 0→100 같은 대비를 하나 넣는다.",
            )
        )

    if hook.endswith("?"):
        findings.append(
            Finding(
                rule="hook-question",
                category="hook",
                severity="note",
                weight=2,
                title="질문형 훅",
                message="질문으로 끝난다. 나쁘지 않지만 결론을 먼저 보여주는 편이 이 시리즈 규칙에 가깝다.",
                fix="질문 뒤에 답을 붙이거나 평서문으로 바꾼다.",
            )
        )

    if first_line and hook and hook != first_line and hook in first_line:
        findings.append(
            Finding(
                rule="hook-duplicated",
                category="hook",
                severity="note",
                weight=1,
                title="캡션 첫 줄과 겹친다",
                message="훅이 캡션 첫 줄 안에 그대로 들어 있다. 화면과 캡션이 같은 말을 두 번 한다.",
                fix="캡션 첫 줄은 훅 이후의 내용으로 시작한다.",
            )
        )

    return findings
