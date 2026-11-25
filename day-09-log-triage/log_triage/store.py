"""ref 보관소 — MCP 한 세션 안에서 파일을 다시 읽지 않기.

파일 경로 대신 ref 를 쓰는 이유: 같은 파일을 세 번 분석하면 세 번 읽고 세 번
디코딩한다. 40만 줄이면 그게 체감된다. ref 는 (경로, 지문)을 들고 있어서
파일이 바뀌면 알려 준다 — 조용히 옛 분석을 돌려주지 않는다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .types import LogFile


def fingerprint(path: str | Path) -> str:
    file_path = Path(path)
    try:
        data = file_path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha1(data[:65536] + str(len(data)).encode()).hexdigest()[:16]


class Store:
    def __init__(self) -> None:
        self._items: dict[str, LogFile] = {}
        self._counter = 0

    def put(self, log: LogFile) -> str:
        self._counter += 1
        ref = f"lg-{self._counter}"
        self._items[ref] = log
        return ref

    def get(self, ref: str) -> LogFile:
        key = (ref or "").strip()
        if key not in self._items:
            known = ", ".join(sorted(self._items)) or "없음"
            raise KeyError(f"ref '{key}' 를 찾을 수 없습니다 (가진 ref: {known}). read_logs 로 먼저 읽으세요.")
        return self._items[key]

    def source_changed(self, ref: str) -> bool:
        log = self._items[ref]
        current = fingerprint(log.path)
        return bool(current and log.fingerprint and current != log.fingerprint)

    def clear(self) -> None:
        self._items.clear()
        self._counter = 0

    def __len__(self) -> int:
        return len(self._items)


STORE = Store()
