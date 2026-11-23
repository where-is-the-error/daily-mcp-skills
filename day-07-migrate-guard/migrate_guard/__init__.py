"""migrate-guard — 실행 중인 DB에 마이그레이션을 걸기 전에 읽는 도구.

공개 MCP 두 개(DBHub · Postgres MCP Pro)의 설계를 가져와 새로 구현했다.
원본 코드는 복사하지 않았다. 자세한 출처는 README 참고.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .operations import Migration, analyze, load_migration      # noqa: F401
from .schema import Schema, parse_schema                        # noqa: F401

__all__ = ["__version__", "Migration", "analyze", "load_migration", "Schema", "parse_schema"]
