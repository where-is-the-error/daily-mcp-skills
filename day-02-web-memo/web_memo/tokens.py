"""토큰 예산 — 정확한 토크나이저 없이 세는 근사치.

Day 01과 같은 규칙을 쓴다: ASCII 4글자 ≈ 1토큰, 그 외(한글·한자 등) 1글자 ≈ 1토큰.
목적은 "이 페이지를 통째로 넣을까, 바뀐 줄만 넣을까"를 가르는 것이지
과금 예측이 아니므로 근사로 충분하다.
"""

from __future__ import annotations

import math

__all__ = ["estimate", "trim_to_tokens"]


def estimate(text: str) -> int:
    """텍스트의 추정 토큰 수."""
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    wide_chars = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / 4) + wide_chars)


def trim_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """토큰 예산에 맞춰 자른다. (잘린 텍스트, 잘렸는지) 를 돌려준다."""
    if max_tokens <= 0:
        return "", bool(text)
    if estimate(text) <= max_tokens:
        return text, False

    # 이진 탐색으로 예산에 들어가는 가장 긴 접두사
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo], True
