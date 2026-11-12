# Resets the database to the demo data. Every demo script calls reset()
# first, so each run starts from the same state.
# Run: python seed.py
import os
import bcrypt
from sqlalchemy import create_engine, text
from app.config import settings

# Demo users all get the same password, read from the environment (.env).
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

USERS = [("u-alice", "alice", "customer"),
         ("u-bob", "bob", "customer"),
         ("u-staff", "staff", "staff")]

# id, name, kind, price, limited, per_order_limit
ITEMS = [("burger-hero", "Hero Burger", "single", "14.00", True, 2),
         ("drink-blue-soda", "Blue Soda", "single", "5.50", True, None),
         ("fries", "Fries", "single", "4.50", False, None),
         ("combo-hero-set", "Hero Set (burger + soda)", "combo", "19.00", False, None)]

COMBO_COMPONENTS = [("combo-hero-set", "burger-hero", 1),
                    ("combo-hero-set", "drink-blue-soda", 1)]

# Release times are relative to "now" so the demo looks the same at any
# time of day: one burger batch is already on sale, the second is not.
BATCHES = [("b-burger-1", "burger-hero", "-1 hour", 10),
           ("b-burger-2", "burger-hero", "+1 day", 6),
           ("b-soda-1", "drink-blue-soda", "-1 hour", 10)]

BONUS_GIFTS = [("combo-hero-set", 3)]       # 3 coasters for the Hero Set


def reset(engine):
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE users, items, combo_components, batches, bonus_gifts,"
            " orders, order_lines, order_claims, order_bonuses,"
            " idempotency_records, waitlist_entries, outbox"
            " RESTART IDENTITY CASCADE"))
        password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        for user_id, username, role in USERS:
            conn.execute(text("INSERT INTO users (id, username, password_hash, role)"
                              " VALUES (:id, :u, :h, :r)"),
                         {"id": user_id, "u": username, "h": password_hash, "r": role})
        for item_id, name, kind, price, limited, limit in ITEMS:
            conn.execute(text("INSERT INTO items (id, name, kind, price, limited, per_order_limit)"
                              " VALUES (:id, :n, :k, :p, :l, :lim)"),
                         {"id": item_id, "n": name, "k": kind, "p": price,
                          "l": limited, "lim": limit})
        for combo_id, item_id, qty in COMBO_COMPONENTS:
            conn.execute(text("INSERT INTO combo_components (combo_id, item_id, qty)"
                              " VALUES (:c, :i, :q)"),
                         {"c": combo_id, "i": item_id, "q": qty})
        for batch_id, item_id, offset, quantity in BATCHES:
            conn.execute(text("INSERT INTO batches (id, item_id, release_at, quantity, remaining)"
                              " VALUES (:id, :i, now() + CAST(:off AS interval), :q, :q)"),
                         {"id": batch_id, "i": item_id, "off": offset, "q": quantity})
        for combo_id, remaining in BONUS_GIFTS:
            conn.execute(text("INSERT INTO bonus_gifts (combo_id, remaining) VALUES (:c, :r)"),
                         {"c": combo_id, "r": remaining})


if __name__ == "__main__":
    reset(create_engine(settings.database_url))
    print("Demo data loaded: users alice, bob (customers) and staff; "
          "Hero Burger, Blue Soda, Fries, Hero Set with 3 bonus gifts.")
