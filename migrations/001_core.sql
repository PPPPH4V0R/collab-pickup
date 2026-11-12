-- Core schema: users, menu, release batches, bonus gifts, orders,
-- and the idempotency records for POST /orders.

CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('customer', 'staff'))
);

-- A menu entry is either a single item or a combo.
-- limited = true means the item is sold only from release batches;
-- an unlimited single item (e.g. fries) has no batches at all.
CREATE TABLE items (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('single', 'combo')),
    price           NUMERIC(8, 2) NOT NULL,
    limited         BOOLEAN NOT NULL DEFAULT false,
    per_order_limit INTEGER            -- NULL = no limit
);

-- Which single items a combo is made of. A combo has no stock of its own:
-- selling one takes units from the batches of its components.
CREATE TABLE combo_components (
    combo_id TEXT NOT NULL REFERENCES items(id),
    item_id  TEXT NOT NULL REFERENCES items(id),
    qty      INTEGER NOT NULL CHECK (qty > 0),
    PRIMARY KEY (combo_id, item_id)
);

-- Contended resource 1: units of a limited item released at a given time.
-- The CHECK is the database's last line of defence against overselling.
CREATE TABLE batches (
    id         TEXT PRIMARY KEY,
    item_id    TEXT NOT NULL REFERENCES items(id),
    release_at TIMESTAMPTZ NOT NULL,
    quantity   INTEGER NOT NULL,
    remaining  INTEGER NOT NULL CHECK (remaining >= 0)
);

-- Contended resource 2: bonus gifts handed out with a combo.
CREATE TABLE bonus_gifts (
    combo_id  TEXT PRIMARY KEY REFERENCES items(id),
    remaining INTEGER NOT NULL CHECK (remaining >= 0)
);

CREATE TABLE orders (
    id             TEXT PRIMARY KEY,          -- random, e.g. ord_3f9a1c...
    user_id        TEXT NOT NULL REFERENCES users(id),
    status         TEXT NOT NULL,
    total          NUMERIC(10, 2) NOT NULL,
    currency       TEXT NOT NULL,
    payment_due_by TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL
);

-- What the customer asked for.
CREATE TABLE order_lines (
    id         BIGSERIAL PRIMARY KEY,
    order_id   TEXT NOT NULL REFERENCES orders(id),
    item_id    TEXT NOT NULL REFERENCES items(id),
    qty        INTEGER NOT NULL,
    unit_price NUMERIC(8, 2) NOT NULL
);

-- Which batch each unit came from, so a cancel can put it back.
CREATE TABLE order_claims (
    id       BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    batch_id TEXT NOT NULL REFERENCES batches(id),
    item_id  TEXT NOT NULL REFERENCES items(id),
    qty      INTEGER NOT NULL
);

-- One row per combo unit: did it come with a bonus gift?
CREATE TABLE order_bonuses (
    id       BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    combo_id TEXT NOT NULL REFERENCES items(id),
    included BOOLEAN NOT NULL
);

-- One outcome per (user, Idempotency-Key). The primary key decides which
-- of two concurrent requests with the same key wins.
CREATE TABLE idempotency_records (
    user_id      TEXT NOT NULL REFERENCES users(id),
    key          TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    ok           BOOLEAN NOT NULL,
    code         TEXT,
    value_json   JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);
