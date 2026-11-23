"""숫자를 사람이 읽는 말로 — 초·분·행. 반올림은 크게, 작은 값은 소수점 하나."""

from __future__ import annotations

__all__ = ["duration", "rows", "secs"]


def duration(seconds: float) -> str:
    if seconds <= 0:
        return "0초"
    if seconds < 0.01:
        return "즉시"
    if seconds < 1:
        return f"{seconds:.2f}초"
    if seconds < 10:
        return f"{seconds:.1f}초"
    if seconds < 60:
        return f"{seconds:.0f}초"
    minutes = seconds / 60
    if minutes < 10:
        return f"{minutes:.1f}분"
    if minutes < 60:
        return f"{minutes:.0f}분"
    hours = int(seconds // 3600)
    rest = int((seconds - hours * 3600) // 60)
    return f"{hours}시간 {rest}분" if rest else f"{hours}시간"


def secs(seconds: float) -> str:
    """`12.0s` 같은 짧은 표기 — 표 안에서 쓴다."""
    if seconds <= 0:
        return "0s"
    if seconds < 1:
        return f"{seconds:.2f}s"
    if seconds < 10:
        return f"{seconds:.1f}s"
    return f"{seconds:.0f}s"


def rows(count: int) -> str:
    return f"{int(count):,}"
