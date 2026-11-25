"""예제 로그 만들기 — 실제 장애 모양을 손으로 흉내 낸 파일.

여기서 만드는 파일은 **합성**이다(사람이 읽도록 만든 것). 실제 공개 코퍼스로
측정한 결과는 `tools/corpus_probe.py` 로 따로 뽑는다 — README 의 '실측' 표가 그것이다.

    python examples/build_examples.py

만들어지는 것
    api-before.log   배포 전 30분: 정상 트래픽 + 드문 클라이언트 오류 12건
    api-after.log    배포 후 30분: 고친 것 + 새로 생긴 PoolTimeoutError 폭주
    formats.log      한 파일에 섞인 6가지 시각 표기 + JSON 줄 + 스택
    korean-cp949.log CP949 로 저장된 한국어 로그 (인코딩 판별용)
    messy-export.log 넘기기 전에 걸리는 것들: 비밀·개인정보·긴 줄·깨진 글자·시각 역행
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = datetime(2026, 11, 25, 9, 0, 0)
DEPLOY = datetime(2026, 11, 25, 14, 0, 0)
USERS = ["kim", "lee", "park", "choi", "jung", "han", "seo", "yoon"]
PATHS = ["/v1/orders", "/v1/orders/1042", "/v1/cart", "/v1/users/me", "/v1/search", "/health"]
CLIENTS = ["10.0.4.18", "10.0.4.22", "10.0.7.9", "172.16.3.40", "203.0.113.77"]


def _rid(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(12))


def _line(ts: datetime, level: str, message: str) -> str:
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{ts.microsecond // 1000:03d} {level:<5} [api] {message}"


def build_before() -> str:
    rng = random.Random(20261125)
    out: list[str] = []
    t = BASE
    end = BASE + timedelta(minutes=30)
    error_at = {7, 15, 23}              # 드문 클라이언트 오류가 나는 분
    slow_at = {11, 26}
    while t < end:
        minute = int((t - BASE).total_seconds() // 60)
        for _ in range(rng.randint(34, 46)):
            t += timedelta(milliseconds=rng.randint(900, 2100))
            if t >= end:
                break
            path = rng.choice(PATHS)
            status = 200 if path != "/v1/search" else rng.choice([200, 200, 200, 304])
            out.append(_line(t, "INFO",
                             f"request_id={_rid(rng)} method=GET path={path} "
                             f"status={status} duration_ms={rng.randint(8, 90)} user={rng.choice(USERS)}"))
            if rng.random() < 0.18:
                out.append(_line(t + timedelta(milliseconds=rng.randint(1, 6)), "INFO",
                                 f"request_id={_rid(rng)} db=orders rows={rng.randint(1, 40)} "
                                 f"duration_ms={rng.randint(2, 24)}"))
        if minute in error_at:
            client = rng.choice(CLIENTS)
            out.append(_line(t, "ERROR",
                             f"ConnectionResetError: connection reset by peer client={client} "
                             f"request_id={_rid(rng)} path=/v1/orders"))
            out.append("Traceback (most recent call last):")
            out.append('  File "/srv/app/handlers/orders.py", line 142, in create')
            out.append("    return gateway.forward(request)")
            out.append('  File "/srv/app/gateway.py", line 88, in forward')
            out.append("    raise ConnectionResetError(\"connection reset by peer\")")
            out.append("ConnectionResetError: connection reset by peer")
            t += timedelta(seconds=3)
        if minute in slow_at:
            out.append(_line(t, "WARN",
                             f"slow query: 1{rng.randint(2, 9)}00ms table=orders request_id={_rid(rng)}"))
            t += timedelta(seconds=2)
    return "\n".join(out) + "\n"


POOL_TRACE = """Traceback (most recent call last):
  File "/srv/app/handlers/orders.py", line 142, in create
    order = service.create(request)
  File "/srv/app/service/orders.py", line 57, in create
    with pool.acquire(timeout=self.timeout) as conn:
  File "/srv/app/db/pool.py", line 64, in acquire
    raise PoolTimeoutError(f"could not get connection from pool {self.in_use} after {self.timeout * 1000:.0f}ms")
app.db.pool.PoolTimeoutError: could not get connection from pool 7 after 5000ms"""


def build_after() -> str:
    rng = random.Random(20261126)
    out: list[str] = []
    t = DEPLOY
    end = DEPLOY + timedelta(minutes=30)
    while t < end:
        minute = int((t - DEPLOY).total_seconds() // 60)
        # 14:10 배포 이후 커넥션 풀이 마른다: 분당 요청은 그대로인데 오류가 계단처럼 는다
        stress = 0.0 if minute < 10 else 0.30
        if 16 <= minute < 19:
            stress = 0.62
        for _ in range(rng.randint(34, 46)):
            t += timedelta(milliseconds=rng.randint(900, 2100))
            if t >= end:
                break
            path = rng.choice(PATHS)
            if stress and rng.random() < stress:
                pool = rng.randint(3, 12)
                out.append(_line(t, "ERROR",
                                 f"PoolTimeoutError: could not get connection from pool {pool} "
                                 f"after 5000ms request_id={_rid(rng)} path={path}"))
                out.extend(POOL_TRACE.splitlines())
                continue
            out.append(_line(t, "INFO",
                             f"request_id={_rid(rng)} method=GET path={path} status=200 "
                             f"duration_ms={rng.randint(8, 140)} user={rng.choice(USERS)}"))
            if rng.random() < 0.15:
                out.append(_line(t, "WARN",
                                 f"pool in_use={rng.randint(4, 9)}/10 wait_ms={rng.randint(40, 900)}"))
            if rng.random() < 0.16:
                out.append(_line(t, "INFO",
                                 f"request_id={_rid(rng)} db=orders rows={rng.randint(1, 40)} "
                                 f"duration_ms={rng.randint(2, 30)}"))
        t += timedelta(milliseconds=rng.randint(200, 900))
    return "\n".join(out) + "\n"


def build_formats() -> str:
    lines = [
        "2026-11-25 09:00:01,123 INFO  [boot] iso with comma — service starting",
        "2026-11-25T09:00:02.456+09:00 INFO  [boot] iso with offset — config loaded in 12ms",
        '{"@timestamp":"2026-11-25T09:00:03.100Z","level":"info","message":"json line: worker 3 ready","service":"api"}',
        '{"@timestamp":"2026-11-25T09:00:04.250Z","level":"error","message":"json line: cache miss storm","service":"api","error":{"stack":"CacheMissError: 41 misses in 1s\\n    at cache.get (/srv/app/cache.js:22:9)"}}',
        "Nov 25 09:00:05 combo sshd(pam_unix)[19939]: session opened for user deploy",
        "10.0.4.18 - - [25/Nov/2026:09:00:06 +0900] \"GET /v1/orders HTTP/1.1\" 200 512",
        "10.0.4.18 - - [25/Nov/2026:09:00:07 +0900] \"POST /v1/orders HTTP/1.1\" 502 128",
        "261125 090008 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_38865049064139660 terminating",
        "26/11/25 09:00:09 INFO SparkContext: Running Spark version 3.5.1",
        "11-25 09:00:10.445  1842  1842 I ActivityManager: Start proc com.example.app",
        "09:00:11 INFO  [boot] time only — date comes from the previous line",
        "2026-11-25 09:00:12.900 ERROR [worker] unhandled exception in job 8842",
        "Traceback (most recent call last):",
        '  File "/srv/app/jobs/export.py", line 88, in run',
        "    rows = fetch(job.range)",
        '  File "/srv/app/jobs/export.py", line 61, in fetch',
        "    raise ExportRangeError(f\"range too large: {size}\")",
        "app.jobs.export.ExportRangeError: range too large: 4200000",
        "2026-11-25 09:00:14,001 INFO  [boot] ready",
    ]
    return "\n".join(lines) + "\n"


def build_korean() -> str:
    lines = [
        "2026-11-25 09:01:00,001 INFO  [주문] 주문 접수 완료 - 주문번호 202611250001",
        "2026-11-25 09:01:02,334 WARN  [재고] 재고가 부족합니다: 상품 A-1042, 남은 수량 2",
        "2026-11-25 09:01:05,777 ERROR [결제] 결제 승인 실패: 카드사 응답 지연 (3,000ms)",
        "Traceback (most recent call last):",
        '  File "/srv/app/pay/card.py", line 44, in authorize',
        "    raise PaymentTimeoutError(\"카드사 응답 지연\")",
        "app.pay.card.PaymentTimeoutError: 카드사 응답 지연",
        "2026-11-25 09:01:09,010 INFO  [주문] 주문 취소 처리 - 주문번호 202611250001",
    ]
    return "\n".join(lines) + "\n"


def build_messy() -> str:
    rng = random.Random(7)
    lines = [
        "2026-11-25 10:00:00,000 INFO  [export] nightly export started",
        "2026-11-25 10:00:01,100 INFO  [export] source=postgres db=orders rows=128400 duration_ms=842",
        '2026-11-25 10:00:02,200 INFO  [auth] login user=kim@example.com password=hunter2 token=abcdef123456',
        "2026-11-25 10:00:02,900 DEBUG [export] payload={\"card\":\"4242 4242 4242 4242\",\"phone\":\"010-3156-8044\"}",
        "2026-11-25 10:00:03,000 INFO  [http] Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dQw4w9WgXcQ",
        "2026-11-25 10:00:03,400 INFO  [aws] using key AKIAIOSFODNN7EXAMPLE region=ap-northeast-2",
        "2026-11-25 10:00:04,000 INFO  [export] " + "SELECT * FROM orders WHERE " + " AND ".join(
            f"col_{i} IS NOT NULL" for i in range(120)) + " -- 1 row(s) returned",
        "2026-11-25 10:00:05,000 WARN  [export] row skipped \x07 control char inside message",
        "2026-11-25 10:00:06,000 INFO  [export] 파일 이름: 2026년_11월_주문내역.csv",
        "2026-11-25 10:00:06,500 INFO  [export] 깨진 글자 □□□ — 인코딩이 섞였습니다",
        "2026-11-25 10:05:30,000 ERROR [export] upload failed: 503 from storage (retry 1)",
        "2026-11-25 10:05:30,000 ERROR [export] upload failed: 503 from storage (retry 2)",
        "2026-11-25 10:05:30,000 ERROR [export] upload failed: 503 from storage (retry 3)",
        "2026-11-25 10:05:30,000 ERROR [export] upload failed: 503 from storage (retry 4)",
        "2026-11-25 10:05:30,000 ERROR [export] upload failed: 503 from storage (retry 5)",
        "2026-11-25 10:05:31,000 ERROR [export] upload failed: 503 from storage (retry 6)",
        "2026-11-25 10:04:00,000 INFO  [export] clock went backwards — buffer flush",
        "2026-11-25 10:09:00,000 ",
        "2026-11-25 10:09:00,100 INFO  [export] retrying with smaller batch size",
    ]
    while len(lines) < 60:
        offset = len(lines) - 19
        stamp = (datetime(2026, 11, 25, 10, 10, 0) + timedelta(seconds=offset)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{stamp},000 INFO  [export] batch={rng.randint(1, 900)} rows={rng.randint(10, 900)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    files = {
        "api-before.log": build_before().encode("utf-8"),
        "api-after.log": build_after().encode("utf-8"),
        "formats.log": build_formats().encode("utf-8"),
        "korean-cp949.log": build_korean().encode("cp949"),
        "messy-export.log": build_messy().encode("utf-8"),
    }
    for name, data in files.items():
        (HERE / name).write_bytes(data)
        print(f"{name:20} {len(data):>8,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
