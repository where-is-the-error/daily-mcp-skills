# day-07 · migrate-guard

> **실행 중인 DB에 마이그레이션을 걸기 전에 읽는다** — 어떤 락이, 무엇을, 얼마나 막는지.
> `ALTER TABLE` 한 줄이 `BEGIN … COMMIT` 안에서 12분을 잡고 있으면, 그 12분 동안은
> `SELECT` 도 줄을 선다. 이 도구는 그 시간을 실행 전에 숫자로 보여 준다.

```bash
migrate-guard summary examples/0012_add_email_verified.up.sql \
  --baseline examples/schema.sql --rows examples/stats.json
```

```text
# 0012_add_email_verified.up.sql
문장 8개 · 표 4개 · 판정 **보류** · 최대 잠금 12분 (events · ACCESS EXCLUSIVE)

- 바뀌는 표: users, orders, sessions, events
- 위험: 치명 3 · 심각 8 · 보통 1 · 참고 1
- BEGIN…COMMIT 하나로 묶여 있음 → 락이 커밋까지 유지 (합계 13분)
- 값이 사라지는 문장 2개: s6(drop_column), s7(update)

## 먼저 볼 문장
- s3 (줄 6) · 치명 · 값이 깨질 수 있는 타입 변경 — users
- s6 (줄 9) · 치명 · 컬럼 값을 지운다 — sessions
- s7 (줄 10) · 치명 · 조건 없는 UPDATE — users
- s2 (줄 5) · 심각 · 읽기까지 막는 잠금이 오래 유지된다 — users
```

## 오늘의 조합 — 공개 MCP 2개 → 새 MCP 1개

| 원본 | 라이선스 | 규모 | 툴 | 가져온 설계 |
|---|---|---|---|---|
| [**DBHub**](https://github.com/bytebase/dbhub) | MIT | ★ 3,940 · 마지막 푸시 2026-11-21 | 5 (기본 2 + 선택 3) | **토큰을 아끼는 작은 툴 셋**(기본 툴 정의 261토큰) · 읽기 전용·행 수 제한·타임아웃 가드레일 · "익숙한 것을 작게" |
| [**Postgres MCP Pro**](https://github.com/crystaldba/postgres-mcp) | MIT | ★ 3,494 · 마지막 푸시 2026-08-17 | 9 | **스키마를 먼저 이해하고 묻는다**(list_schemas → list_objects → get_object_details) · restricted/unrestricted 접근 모드 · 실행 전에 계획을 보는 태도 |

두 원본 모두 PostgreSQL 에 붙어 **쿼리를 실행하는** 서버다. 이 도구는 반대로
**실행하지 않고 읽는다** — 마이그레이션 파일과 기준 스키마만 있으면 되고, DB 접속이 없다.
원본 코드는 한 줄도 복사하지 않았다. 가져온 것은 위 표의 설계와 태도뿐이다.
툴 수 14 → 9.

## 왜 이 조합인가

- DBHub 는 "DB 앞에 작은 창구 하나"를 증명했다. 툴이 많을수록 모델이 헤매고 토큰을 태운다.
  그래서 여기서도 툴은 9개, 각 툴의 반환은 `max_tokens` 로 잘린다.
- Postgres MCP Pro 는 "스키마를 모르면 판단도 틀린다"를 증명했다. 그래서 `baseline` 스키마를
  읽어 **타입 변경이 재작성인지**를 정확히 가른다(`varchar(32) → varchar(16)` 는 재작성 + 실패 위험,
  `varchar(32) → text` 는 메타데이터만).
- 둘 다 "위험한 실행을 하기 전에 멈춘다"는 태도를 갖고 있다. 그 태도를 마이그레이션 리뷰로 옮겼다.

## 30초 실행

```bash
cd day-07-migrate-guard
pip install -e ".[dev]"
python -m pytest                     # 322 passed
migrate-guard summary examples/0012_add_email_verified.up.sql --baseline examples/schema.sql --rows examples/stats.json
migrate-guard risk    examples/0012_add_email_verified.up.sql --baseline examples/schema.sql --rows examples/stats.json
migrate-guard locks   examples/0012_add_email_verified.up.sql --rows examples/stats.json
migrate-guard rollout examples/0012_add_email_verified.up.sql --baseline examples/schema.sql --rows examples/stats.json
migrate-guard compare examples/0012_add_email_verified.up.sql examples/0012_add_email_verified.fixed.up.sql \
  --baseline examples/schema.sql --rows examples/stats.json
```

`examples/stats.json` 은 표별 행 수다(예: users 140만 · orders 820만 · events 4,200만).
행 수를 주지 않으면 표마다 **10만 행으로 가정**하고, 그 사실을 결과 첫 화면에 적는다.

## 판정 — 등급·근거·고치기

```text
# 0012_add_email_verified.up.sql — 판정 **보류**
치명 3 · 심각 8 · 보통 1 · 참고 1

**치명 · 값이 깨질 수 있는 타입 변경** — `s3` (줄 6) users
- 문장: users.phone 타입 축소
- 근거: varchar(32) → varchar(16)
- 근거: 1,400,000행 (실제 행 수)
- 근거: 테이블 재작성 1,400,000행 · 약 23초 (모델)
- 고치기: 먼저 대상 값이 범위 안에 있는지 세어 보고, 통과할 때만 바꾼다.

**치명 · 조건 없는 UPDATE** — `s7` (줄 10) users
- 문장: users 전체 갱신
- 근거: 1,400,000행 (실제 행 수)
- 근거: 전체 갱신 1,400,000행 · 약 12초 (모델)
- 근거: 되돌리기: 이전 값 없음

**심각 · 트랜잭션 하나라 락이 끝까지 유지된다** — `s2` (줄 5) users
- 문장: BEGIN ... COMMIT 하나로 묶여 있다
- 근거: 막는 문장 7개 · 합계 13분 동안 락 유지
- 근거: 가장 오래 걸리는 문장이 끝나도 커밋 전까지 앞의 락이 풀리지 않는다
```

- 모든 근거에 **숫자**(행 수, 예상 시간, 락 모드)를 붙인다. "위험함"만 쓰지 않는다.
- 판정은 세 단계: **보류**(치명 있음) · **주의**(심각 있음) · **통과**.
- `--fail-on 치명` 이면 CI 게이트로 쓸 수 있다(종료 코드 2).

## 잠금 — 무엇이 막히는지

```text
# 0012_add_email_verified.up.sql — 잠금 · 최대 12분 (events · ACCESS EXCLUSIVE)

- s2 줄 5 · users · ACCESS EXCLUSIVE · 읽기·쓰기 모두 막힘 · 약 23초
    휘발성 기본값 → 전체 재작성 · 1,400,000행 (실제 행 수)
- s4 줄 7 · users · SHARE · 쓰기 막힘 (읽기는 통과) · 약 16초
    인덱스 빌드 · 1,400,000행 (실제 행 수)
- s5 줄 8 · orders · SHARE ROW EXCLUSIVE · 쓰기 막힘 (읽기는 통과) · 약 33초
    기존 행 검증 · 8,200,000행 (실제 행 수)
- s8 줄 11 · events · ACCESS EXCLUSIVE · 읽기·쓰기 모두 막힘 · 약 12분
    USING 식 → 전체 재작성 · 42,000,000행 (실제 행 수)

**락 유지 합계** 13분 (BEGIN…COMMIT 하나)
```

문장마다 PostgreSQL 의 락 모드를 붙이고, 그 모드가 **읽기까지 막는지**를 따로 표시한다.
`SHARE`(인덱스 빌드)는 쓰기만 막고, `SHARE UPDATE EXCLUSIVE`(VALIDATE·CONCURRENTLY)는
쓰기도 통과시킨다 — 이 차이가 배포 가능/불가능을 가른다.

## 다시 쓴 단계 — 확장 → 백필 → 전환

```bash
migrate-guard rollout examples/0012_add_email_verified.up.sql \
  --baseline examples/schema.sql --rows examples/stats.json \
  --out examples/0012_add_email_verified.fixed.up.sql
```

`examples/0012_add_email_verified.fixed.up.sql` 은 **이 명령의 실제 출력**이다.
문장 8개 → 3단계 26개, 락 유지 13분 → 0.02초.

```sql
-- ===== 1단계 · 지금 배포 =====
-- 기본값 없이 추가 — 메타데이터만 바뀐다
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_source text;
...
CREATE INDEX CONCURRENTLY idx_users_signup_source ON users (signup_source);
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
ALTER TABLE sessions RENAME COLUMN legacy_token TO _deprecated_legacy_token;

-- ===== 2단계 · 백필 (트랜잭션 밖 · 나눠서) =====
UPDATE users SET signup_source = md5(random()::text)
 WHERE signup_source IS NULL
   AND id IN (SELECT id FROM users WHERE signup_source IS NULL LIMIT 5000);

-- ===== 3단계 · 다음 배포 =====
ALTER TABLE users VALIDATE CONSTRAINT users_signup_source_not_null;
ALTER TABLE users ALTER COLUMN signup_source SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_signup_source_not_null;
```

바꾸는 규칙:

| 원본 | 다시 쓴 것 |
|---|---|
| `ADD COLUMN … NOT NULL DEFAULT <휘발성>` | 기본값 없이 추가 → 배치 백필 → `SET DEFAULT` → `CHECK NOT VALID` → `VALIDATE` → `SET NOT NULL` |
| `SET NOT NULL` | `CHECK (col IS NOT NULL) NOT VALID` → `VALIDATE` → `SET NOT NULL` → 임시 제약 삭제 |
| `CREATE INDEX` | `CREATE INDEX CONCURRENTLY` (트랜잭션 밖) |
| `DROP INDEX` | `DROP INDEX CONCURRENTLY` |
| `ADD CONSTRAINT … FOREIGN KEY / CHECK` | `NOT VALID` 로 달고 → `VALIDATE` |
| `ADD CONSTRAINT … UNIQUE / PRIMARY KEY` | `CREATE UNIQUE INDEX CONCURRENTLY` → `USING INDEX` 로 승격 |
| `ALTER COLUMN … TYPE` (재작성) | 새 컬럼 + 배치 백필 + 이름 교체(3단계) |
| `DROP COLUMN` / `DROP TABLE` | 이름만 `_deprecated_*` 로 바꿔 두고 다음 배포에서 삭제 |
| `UPDATE` / `DELETE` (조건 없음) | 키 범위 배치(`:last_key`)로 나눔 |
| `TRUNCATE` | `ctid` 배치 `DELETE` |

**숨기지 않는 것**: 배치를 나눠도 *값이 사라지는* 변경(컬럼·테이블 삭제)은 그대로 사라진다.
`rollout` 결과는 "3단계에서 값이 사라진다 · 필요하면 먼저 백업" 이라고 적는다.

## 되돌리기 — 되돌릴 수 있는 것만 SQL 로

```text
-- 되돌리기 단계 8개 · 값이 사라진 문장 2개
-- 값이 사라진 문장: s6(drop_column), s7(update)

-- s8 (줄 11) events
-- ⚠️ 역방향도 재작성이며, 축소 방향이면 값이 깨질 수 있다
ALTER TABLE events ALTER COLUMN payload TYPE text;

-- s6 (줄 9) sessions
-- ⚠️ 스키마만 되살아난다 · 값은 복구되지 않는다
ALTER TABLE sessions ADD COLUMN legacy_token text;
```

`DROP COLUMN` 은 컬럼을 되살릴 수는 있어도 **값은 되살리지 못한다**. 그 구분을 문장마다 적는다.
`CREATE INDEX CONCURRENTLY`·`VALIDATE CONSTRAINT` 는 트랜잭션 밖에서 실행해야 하므로
되돌리기 SQL 도 트랜잭션으로 묶지 않는다.

## 스키마 변화 — 적용 전후

```text
# 스키마 변화 — examples/0012_add_email_verified.up.sql

- 새 컬럼: users.signup_source
- 사라지는 컬럼: sessions.legacy_token
- 바뀌는 컬럼: events.payload · type text → jsonb
- 바뀌는 컬럼: users.phone · type varchar(32) → varchar(16)
- 새 인덱스: idx_users_signup_source
- 사라지는 인덱스: orders_created_at_idx
- 새 제약: orders.orders_user_fk
```

`CREATE TABLE`·`CREATE INDEX`·`ALTER TABLE` 을 읽어 스키마 모델을 만들고, 마이그레이션을
얹어 본 뒤 비교한다. **실행은 하지 않는다** — 파일과 모델만으로 계산한다.

## 비교 — 고친 파일이 정말 나아졌는지

```text
- 이전: 문장 8개 · 판정 **보류** · 락 유지 13분
- 이후: 문장 26개 · 판정 **통과** · 락 유지 0.02초

## 등급별
- 치명: 3 → 0 (감소)
- 심각: 8 → 0 (감소)

## 가장 긴 잠금
- 이전: events · ACCESS EXCLUSIVE · 12분
- 이후: users · ACCESS EXCLUSIVE · 0.02초

- 트랜잭션 묶음: 이전은 BEGIN…COMMIT 하나, 이후는 문장별로 분리
```

## 9개 툴

| 툴 | 하는 일 |
|---|---|
| `read_migration` | 한 화면 요약 — 판정·최대 잠금·먼저 볼 문장 |
| `list_statements` | 문장 목록(ref `s1`…, 줄 번호, 종류, 락 모드) |
| `lock_report` | 문장별 락 모드·막히는 대상·예상 유지 시간 |
| `risk_report` | 등급·근거 값·고치는 문장 (`severity` 로 거르기) |
| `rollout_plan` | 확장·백필·전환으로 다시 쓴 SQL |
| `rollback_plan` | 역순 되돌리기 SQL + 되돌릴 수 없는 표시 |
| `schema_change` | 기준 스키마에 얹은 뒤의 변화 |
| `compare_migrations` | 두 파일의 등급·락 비교 |
| `rule_catalog` | 규칙 24종과 **판정하지 않는 것** |

## 규칙 24종

| 등급 | 규칙 |
|---|---|
| 치명 6 | 테이블 삭제 · 컬럼 삭제 · `TRUNCATE` · 조건 없는 `DELETE` · 조건 없는 `UPDATE` · 값이 깨지는 타입 축소 |
| 심각 10 | 기본값 없는 `NOT NULL` 추가 · 휘발성 기본값 재작성 · 타입 변경 재작성 · 읽기까지 막는 긴 잠금 · `SET NOT NULL` 스캔 · 인덱스 빌드가 쓰기 차단 · 트랜잭션 안 `CONCURRENTLY` · `NOT VALID` 없는 외래키 · 제약 추가가 인덱스 빌드 · 트랜잭션 하나라 락이 끝까지 |
| 보통 5 | `NOT VALID` 없는 `CHECK` · 컬럼 이름 변경 · 테이블 이름 변경 · 인덱스 삭제 · 예고된 정리 삭제 |
| 참고 3 | 마이그레이션 안의 데이터 변경 · `lock_timeout` 없음 · 제약 삭제 |

## 어떻게 만들었나

1. **문장 나누기** (`splitter.py`) — 글자 단위 상태 기계. `--` 주석, 중첩 `/* */`,
   `'문자열'` 의 `''`, `"식별자"`, `$$ … $$`·`$tag$ … $tag$` 안의 세미콜론은 문장을 끊지 않는다.
   나눈 문장은 **원본 줄 번호**를 들고 다닌다 — 근거가 곧 줄 번호다.
2. **분류** (`operations.py`) — 문장 하나를 종류·대상·락 모드·비용으로. PostgreSQL 이 실제로 하는 일을 따른다:
   `ADD COLUMN … DEFAULT 0` 은 메타데이터만, `DEFAULT random()` 은 전체 재작성,
   `SET NOT NULL` 은 유효한 `CHECK (col IS NOT NULL)` 이 있으면 스캔을 건너뛴다(12+).
3. **스키마 모델** (`schema.py`) — `CREATE TABLE`·`CREATE INDEX`·`ALTER TABLE` 을 읽어 표·컬럼·제약·인덱스로.
   마이그레이션을 얹어 본 결과와 비교하면 파일만 봐서는 안 보이는 변화가 보인다.
4. **비용 모델** (`dialect.py`) — 재작성 60,000행/초 · 스캔 250,000행/초 · 인덱스 90,000행/초.
   **가정**이며 결과에도 그렇게 적는다. `--rows` 로 실제 행 수를 주면 곱해서 계산한다.
5. **다시 쓰기** (`rollout.py`) · **되돌리기** (`rollback.py`) — 원본을 지우지 않고 같은 뜻의 안전한 단계로.

## 검증 (2026-11-23)

| 무엇 | 어떻게 | 결과 |
|---|---|---|
| 단위 테스트 | `python -m pytest` | **322 passed** (3.4초) — splitter 31 · dialect 38 · schema 53 · operations 51 · risks 51 · rollout 30 · rollback 21 · compare 8 · cli 22 · server 17 |
| MCP 서버 | in-memory 클라이언트 + **stdio 서브프로세스** | 9개 툴 목록 일치, 실제 호출 확인 |
| 실제 마이그레이션 | [mattermost/mattermost](https://github.com/mattermost/mattermost) `server/channels/db/migrations/postgres/*.up.sql` **241개** 파일 · **612문장** (`tools/corpus_probe.py`) | 예외 **0** · 분류 밖 **0** · 판정 통과 162 / 주의 64 / 보류 15 |
| 실제 DB 카탈로그 | SQLite 에 DDL 을 넣고 `PRAGMA` 와 대조 (`tools/schema_probe.py`) | 표 4 · 컬럼 20 · 인덱스 2 — **불일치 0** |

실제 코퍼스에서 가장 많이 걸린 규칙: `create-index-blocks-writes` 154회 ·
`no-lock-timeout` 131회 · `drop-index` 39회 · `drop-column`(치명) 15회 · `rewrite-type` 14회.
남의 저장소 파일은 내려받아 분석만 하고 **저장소에 넣지 않는다**.

## MCP 클라이언트 설정

```json
{"mcpServers": {"migrate-guard": {
  "command": "python", "args": ["-m", "migrate_guard.server"],
  "env": {"MIGRATE_GUARD_ROOT": "/Users/me/app/db"}}}}
```

`MIGRATE_GUARD_ROOT` 를 주면 `source`·`baseline`·`rows` 를 상대 경로로 쓸 수 있다.

## 판정하지 않는 것

- **실행 시간의 실측** — 행/초 가정으로만 계산한다. 테이블 크기·I/O·캐시에 따라 몇 배씩 달라진다.
- **지금 잡혀 있는 락·대기열** — 접속하지 않으므로 `pg_locks` 를 보지 않는다.
- **복제 지연·디스크·WAL 크기** — 재작성의 부수 비용은 계산하지 않는다.
- **데이터 값의 분포** — 타입 축소가 실제로 실패할지는 세어 보지 않는다(확인 쿼리를 제안만 한다).
- **다른 방언** — PostgreSQL 문법 기준이다(MySQL·Oracle 은 판정하지 않는다).
- **마이그레이션 도구의 트랜잭션 래핑** — Flyway·Alembic 이 씌우는지는 도구 설정을 봐야 한다.
  파일에 `BEGIN` 이 있으면 "묶였다"고 판정하지만, 도구가 몰래 씌우는 것은 알 수 없다.
- **이름 없는 제약의 실제 이름** — PostgreSQL 이 붙이는 이름은 미리 알 수 없다.

## 출처와 라이선스

- [bytebase/dbhub](https://github.com/bytebase/dbhub) — MIT License. 툴 셋·가드레일 설계 참고(코드 복사 없음).
- [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) — MIT License. 스키마 우선 탐색·접근 모드 설계 참고(코드 복사 없음).
- 이 저장소의 코드: MIT License (`../LICENSE`).

---

```bash
migrate-guard rules    # 규칙 24종 전체와 판정하지 않는 것
```
