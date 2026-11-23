-- 0012: 가입 경로를 남기고, 전화번호를 짧게 줄이고, 이벤트 본문을 JSON 으로 바꾼다.
-- 리뷰에서 "한 트랜잭션에 넣으면 안전" 이라는 말을 듣고 그대로 묶은 파일.
BEGIN;

ALTER TABLE users ADD COLUMN signup_source text NOT NULL DEFAULT md5(random()::text);
ALTER TABLE users ALTER COLUMN phone TYPE varchar(16);
CREATE INDEX idx_users_signup_source ON users (signup_source);
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id);
ALTER TABLE sessions DROP COLUMN legacy_token;
UPDATE users SET last_seen_at = now();
ALTER TABLE events ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
DROP INDEX orders_created_at_idx;

COMMIT;
