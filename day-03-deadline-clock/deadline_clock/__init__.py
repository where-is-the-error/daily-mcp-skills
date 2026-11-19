"""deadline-clock — Time MCP 의 시간대 규칙 × SQLite MCP 의 저장 규칙.

마감을 "날짜"가 아니라 **시각 + 시간대**로 저장하고, 남은 시간·평일 수·D-day 를
한 번에 계산해 주는 MCP 서버입니다.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
