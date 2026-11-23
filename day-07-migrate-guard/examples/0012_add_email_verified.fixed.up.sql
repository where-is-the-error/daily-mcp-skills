-- migrate-guard 가 다시 쓴 마이그레이션 (확장 → 백필 → 전환)
-- 각 단계는 서로 다른 배포에서 실행합니다. 한 트랜잭션에 묶지 마세요.

-- ===== 1단계 · 지금 배포 =====
-- 바꾼 이유: users.signup_source 를 기본값 없이 추가하고 백필로 나눴다
-- 바꾼 이유: users.phone 타입 변경을 새 컬럼 + 백필로 나눴다
-- 바꾼 이유: idx_users_signup_source 를 CONCURRENTLY 로 바꿨다
-- 바꾼 이유: orders foreign_key 제약을 NOT VALID → VALIDATE 로 나눴다
-- 바꾼 이유: sessions.legacy_token 삭제를 이름 변경으로 미뤘다
-- 바꾼 이유: 전체 갱신·삭제를 배치로 바꿨다
-- 바꾼 이유: events.payload 타입 변경을 새 컬럼 + 백필로 나눴다
-- 바꾼 이유: DROP INDEX 를 CONCURRENTLY 로 바꿨다
-- 기본값 없이 추가 — 메타데이터만 바뀐다
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_source text;
-- 축소 변환은 값에 따라 실패한다 · 0건일 때만 진행
-- 먼저 길이를 넘는 값이 있는지 센다 (0 이어야 진행)
SELECT count(*) FROM users WHERE length(phone) > 16;
-- 새 컬럼은 메타데이터만
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_new varchar(16);
-- CONCURRENTLY — 빌드 동안에도 쓰기가 지나간다 · 트랜잭션 밖에서
CREATE INDEX CONCURRENTLY idx_users_signup_source ON users (signup_source);
-- 지금은 기존 행을 보지 않는다
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
-- 값은 그대로 두고 이름만 바꾼다 — 코드에서 참조를 지우는 동안
ALTER TABLE sessions RENAME COLUMN legacy_token TO _deprecated_legacy_token;
-- :last_key 를 갱신하며 마지막 id 까지 반복 · 사이사이 커밋
-- 조건 없는 UPDATE 대신 나눠서
UPDATE users SET last_seen_at = now() WHERE id IN (SELECT id FROM users WHERE id > :last_key ORDER BY id LIMIT 5000);
-- 새 컬럼은 메타데이터만
ALTER TABLE events ADD COLUMN IF NOT EXISTS payload_new jsonb;
-- CONCURRENTLY — 지우는 동안에도 쓰기가 지나간다 · 트랜잭션 밖
DROP INDEX CONCURRENTLY IF EXISTS orders_created_at_idx;

-- ===== 2단계 · 백필 (트랜잭션 밖 · 나눠서) =====
-- 5000행씩 · 같은 문장을 0행이 될 때까지 반복
UPDATE users SET signup_source = md5(random()::text)
 WHERE signup_source IS NULL
   AND id IN (SELECT id FROM users WHERE signup_source IS NULL LIMIT 5000);
-- 5000행씩 · 실패한 행이 있으면 그 행만 따로 본다
UPDATE users SET phone_new = phone::varchar(16)
 WHERE phone_new IS NULL
   AND id IN (SELECT id FROM users WHERE phone_new IS NULL LIMIT 5000);
-- 5000행씩 · 실패한 행이 있으면 그 행만 따로 본다
UPDATE events SET payload_new = payload::jsonb
 WHERE payload_new IS NULL
   AND id IN (SELECT id FROM events WHERE payload_new IS NULL LIMIT 5000);

-- ===== 3단계 · 다음 배포 =====
-- 이제부터 들어오는 행에만 기본값이 붙는다
ALTER TABLE users ALTER COLUMN signup_source SET DEFAULT md5(random()::text);
-- 새로 들어온 행이 NULL 이면 여기서 채운다
-- 3단계 전에 백필을 한 번 더 (1~3단계 사이에 들어온 NULL 행)
UPDATE users SET signup_source = md5(random()::text)
 WHERE signup_source IS NULL
   AND id IN (SELECT id FROM users WHERE signup_source IS NULL LIMIT 5000);
ALTER TABLE users ADD CONSTRAINT users_signup_source_not_null CHECK (signup_source IS NOT NULL) NOT VALID;
-- 기존 행 검증 — 이때는 쓰기를 막지 않는다
ALTER TABLE users VALIDATE CONSTRAINT users_signup_source_not_null;
-- 검증된 CHECK 가 있으면 전체 스캔을 건너뛴다
ALTER TABLE users ALTER COLUMN signup_source SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_signup_source_not_null;
-- 코드가 새 컬럼을 읽기 시작한 뒤에
ALTER TABLE users RENAME COLUMN phone TO phone_old;
ALTER TABLE users RENAME COLUMN phone_new TO phone;
-- 한 배포 더 지나고
ALTER TABLE users DROP COLUMN phone_old;
-- 쓰기를 막지 않고 기존 행을 검증한다
ALTER TABLE orders VALIDATE CONSTRAINT orders_user_fk;
-- 이 시점에 값이 사라진다 · 필요하면 먼저 백업
ALTER TABLE sessions DROP COLUMN _deprecated_legacy_token;
-- 코드가 새 컬럼을 읽기 시작한 뒤에
ALTER TABLE events RENAME COLUMN payload TO payload_old;
ALTER TABLE events RENAME COLUMN payload_new TO payload;
-- 한 배포 더 지나고
ALTER TABLE events DROP COLUMN payload_old;
