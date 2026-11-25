from __future__ import annotations

from pathlib import Path

import pytest

from log_triage.parse import decode_bytes, load_log, parse_text, read_whole

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
BEFORE = EXAMPLES / "api-before.log"
AFTER = EXAMPLES / "api-after.log"
FORMATS = EXAMPLES / "formats.log"
MESSY = EXAMPLES / "messy-export.log"
KOREAN = EXAMPLES / "korean-cp949.log"


def make(text: str, **kwargs):
    """메모리 문자열 → LogFile. 테스트마다 파일을 만들지 않는다."""
    kwargs.setdefault("path", "mem:test")
    return parse_text(text, **kwargs)


@pytest.fixture()
def before():
    return load_log(BEFORE)


@pytest.fixture()
def after():
    return load_log(AFTER)


@pytest.fixture()
def formats():
    return load_log(FORMATS)


@pytest.fixture()
def messy():
    return load_log(MESSY)


@pytest.fixture()
def korean():
    return load_log(KOREAN)


@pytest.fixture()
def simple():
    return make(
        "2026-11-25 09:00:01,100 INFO  [api] request_id=aaa111bbb222 path=/v1/orders status=200\n"
        "2026-11-25 09:00:02,200 INFO  [api] request_id=ccc333ddd444 path=/v1/cart status=200\n"
        "2026-11-25 09:00:03,300 ERROR [api] PoolTimeoutError: pool 7 after 5000ms request_id=eee555\n"
        "Traceback (most recent call last):\n"
        '  File "/srv/app/db/pool.py", line 64, in acquire\n'
        "    raise PoolTimeoutError()\n"
        "app.db.pool.PoolTimeoutError: pool 7 after 5000ms\n"
    )


def raw_lines(path: Path) -> list[str]:
    text, _, _, _ = decode_bytes(path.read_bytes())
    return text.splitlines()


__all__ = ["make", "raw_lines", "read_whole", "BEFORE", "AFTER", "FORMATS", "MESSY", "KOREAN"]
