"""읽은 표를 세션 안에서 ref로 붙잡아 둔다.

MCP 툴은 호출 사이에 상태를 들고 있지 않으므로, `read_table` 이 돌려준 ref로 다시
찾아올 수 있어야 한다. 파일이 바뀌면 예전 ref와 내용이 달라지므로 원본 바이트의
지문을 함께 보관하고, 다시 읽을 때 달라졌으면 알린다.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from .table import Table


class Store:
    def __init__(self, limit: int = 24):
        self._items: dict[str, Table] = {}
        self._fingerprints: dict[str, str] = {}
        self._order: list[str] = []
        self._limit = limit
        self._lock = threading.Lock()
        self._counter = 0

    def put(self, table: Table, fingerprint: str = "") -> str:
        with self._lock:
            self._counter += 1
            ref = f"t{self._counter}"
            self._items[ref] = table
            self._fingerprints[ref] = fingerprint
            self._order.append(ref)
            while len(self._order) > self._limit:
                old = self._order.pop(0)
                self._items.pop(old, None)
                self._fingerprints.pop(old, None)
            return ref

    def get(self, ref: str) -> Table:
        table = self._items.get(ref)
        if table is None:
            known = ", ".join(self._order) or "없음"
            raise KeyError(f"'{ref}' 표를 찾을 수 없습니다. 지금 있는 ref: {known}. read_table 로 다시 읽으세요.")
        return table

    def fingerprint(self, ref: str) -> str:
        return self._fingerprints.get(ref, "")

    def refs(self) -> list[str]:
        return list(self._order)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._fingerprints.clear()
            self._order.clear()


def file_fingerprint(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


STORE = Store()
