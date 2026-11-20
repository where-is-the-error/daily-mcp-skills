"""토큰 예산 — 정확한 토크나이저 없이 세는 근사치 (Day 01·02 와 같은 규칙).

ASCII 4글자 ≈ 1토큰, 그 외(한글·한자 등) 1글자 ≈ 1토큰.
"""

from __future__ import annotations

import math

__all__ = ["estimate", "trim_to_tokens"]


def estimate(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    wide_chars = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / 4) + wide_chars)


def trim_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    if max_tokens <= 0:
        return "", bool(text)
    if estimate(text) <= max_tokens:
        return text, False
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo], True
