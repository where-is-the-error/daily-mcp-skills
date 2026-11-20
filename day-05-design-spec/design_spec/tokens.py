"""토큰 예산 — 응답이 길어질 때 자르는 규칙 하나만 담당한다.

정확한 토크나이저가 아니라 **보수적인 어림셈**입니다: 한글은 글자당 토큰이
영어보다 많으므로 1토큰 ≈ 2.8자로 잡습니다. 잘랐으면 잘랐다고 말합니다.
"""

from __future__ import annotations

__all__ = ["estimate_tokens", "trim_to_tokens"]

CHARS_PER_TOKEN = 2.8


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def trim_to_tokens(text: str, budget: int) -> tuple[str, bool]:
    """예산 안으로 자른다 — 줄 경계에서 자르고, 잘렸는지 함께 돌려준다."""
    if budget <= 0:
        return "", bool(text)
    if estimate_tokens(text) <= budget:
        return text, False
    limit = int(budget * CHARS_PER_TOKEN)
    cut = text[:limit]
    newline = cut.rfind("\n")
    if newline > limit * 0.6:
        cut = cut[:newline]
    return cut.rstrip(), True
