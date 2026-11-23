-- 기준 스키마: 작은 커머스 서비스의 지금 모습 (PostgreSQL 16)
-- migrate-guard 는 이 파일을 '적용 전' 으로 두고 마이그레이션을 얹어 본다.

CREATE TABLE users (
    id            bigint PRIMARY KEY,
    email         varchar(255) NOT NULL,
    phone         varchar(32),
    name          varchar(80),
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz
);

CREATE UNIQUE INDEX users_email_key ON users (email);

CREATE TABLE orders (
    id          bigint PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users (id),
    total_cents integer NOT NULL,
    status      varchar(24) NOT NULL DEFAULT 'pending',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX orders_user_id_idx ON orders (user_id);
CREATE INDEX orders_created_at_idx ON orders (created_at);

CREATE TABLE events (
    id         bigint PRIMARY KEY,
    user_id    bigint,
    kind       varchar(48) NOT NULL,
    payload    text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id          uuid PRIMARY KEY,
    user_id     bigint NOT NULL,
    legacy_token text,
    expires_at  timestamptz NOT NULL
);

CREATE TABLE invoices (
    id           bigint PRIMARY KEY,
    order_id     bigint NOT NULL,
    amount_cents integer NOT NULL,
    issued_at    date NOT NULL
);

CREATE TABLE products (
    id          bigint PRIMARY KEY,
    sku         varchar(48) NOT NULL,
    price_cents integer NOT NULL,
    active      boolean NOT NULL DEFAULT true
);
