"""공통 픽스처 — '지금'을 2026-11-19(목) 10:00 KST 로 고정한다."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)  # 2026-11-19(목) 10:00 KST


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "deadlines.db"
    monkeypatch.setenv("DEADLINE_CLOCK_DB", str(path))
    return path


@pytest.fixture
def conn(db_path):
    from deadline_clock import store

    connection = store.connect(db_path)
    try:
        yield connection
    finally:
        connection.close()
