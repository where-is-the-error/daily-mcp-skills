"""sheet-guard — 표를 LLM·엑셀에 넣기 전에 읽는다.

공개 MCP 서버(Excel MCP Server)와 문서 변환기(MarkItDown)의 설계를 조합해 만든
표 점검 도구. 코드는 원본에서 가져오지 않았고 설계·태도만 참고했다(README 참고).
"""

from __future__ import annotations

from .table import Table, load_table

__version__ = "0.1.0"
__all__ = ["Table", "load_table", "__version__"]
