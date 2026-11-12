-- Expand-only migration: new tables, nothing existing is changed, so code
-- written for 001 keeps working. The logic that uses these tables
-- (waitlist promotion, the payment worker) comes after the Milestone.

-- Customers waiting for a sold-out limited item, served in arrival order.
CREATE TABLE waitlist_entries (
    id         BIGSERIAL PRIMARY KEY,
    item_id    TEXT NOT NULL REFERENCES items(id),
    user_id    TEXT NOT NULL REFERENCES users(id),
    status     TEXT NOT NULL DEFAULT 'WAITING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (item_id, user_id)
);

-- Messages to send to the payment provider. Written in the same
-- transaction as the order; a background worker sends them later.
CREATE TABLE outbox (
    id           BIGSERIAL PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(id),
    kind         TEXT NOT NULL,              -- e.g. 'CHARGE', 'REFUND'
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ                 -- NULL = not sent yet
);
