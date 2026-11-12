# Race demo: 100 customers order at the same moment from a burger batch
# of 10 units. Half order a Hero Burger, half order a Hero Set (burger +
# soda), so a single and a combo compete for the same burger stock, and
# the combos also compete for 3 bonus gifts.
#
#   unsafe : stock rows are read WITHOUT FOR UPDATE      -> more than 10 sold
#   locked : stock rows are locked with FOR UPDATE      -> exactly 10 sold
#
# Run from the project root: python scripts/race.py unsafe | locked
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # import app/ and seed.py

from sqlalchemy import text
from app.config import settings
from app.postgres_repository import PostgresRepository, make_engine
from app.service import OrderService
import seed

CUSTOMERS = 100
DEMO_DELAY = 0.2       # seconds between "check stock" and "write stock back"

engine = make_engine(settings.database_url)
service = OrderService(PostgresRepository(engine))


def order_lines(i):
    item_id = "burger-hero" if i % 2 == 0 else "combo-hero-set"
    return [{"itemId": item_id, "qty": 1}]


def place(mode, i):
    lines = order_lines(i)
    if mode == "unsafe":
        return service.place_order_unsafe("u-alice", lines, demo_delay=DEMO_DELAY)
    return service.place_order("u-alice", f"race-{i}", lines, demo_delay=DEMO_DELAY)


def count(sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def run(mode):
    seed.reset(engine)
    print(f"[{mode}] {CUSTOMERS} concurrent orders; burger batch b-burger-1 has 10 units, "
          f"Hero Set has 3 bonus gifts")

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CUSTOMERS) as pool:
        outcomes = list(pool.map(lambda i: place(mode, i), range(CUSTOMERS)))
    elapsed = time.perf_counter() - t0

    placed = sum(1 for o in outcomes if o.ok)
    sold_out = sum(1 for o in outcomes if o.code == "SOLD_OUT")
    burgers_sold = count("SELECT COALESCE(SUM(qty), 0) FROM order_claims"
                         " WHERE batch_id = 'b-burger-1'")
    remaining = count("SELECT remaining FROM batches WHERE id = 'b-burger-1'")
    gifts_given = count("SELECT COUNT(*) FROM order_bonuses WHERE included")
    gifts_left = count("SELECT remaining FROM bonus_gifts WHERE combo_id = 'combo-hero-set'")
    combos_sold = count("SELECT COUNT(*) FROM order_bonuses")

    print(f"  orders placed : {placed}   SOLD_OUT: {sold_out}   (elapsed {elapsed:.1f}s)")
    print(f"  burgers sold  : {burgers_sold} of 10   remaining in batch: {remaining}")
    print(f"  combos sold   : {combos_sold}   bonus gifts given: {gifts_given} of 3   "
          f"gifts left: {gifts_left}")
    if burgers_sold > 10 or gifts_given > 3:
        print(f"  RESULT: OVERSOLD -- {burgers_sold - 10} burgers that do not exist were sold"
              f" (lost update: each order wrote back its own stale 'remaining')")
    else:
        print("  RESULT: CORRECT -- never more than 10 burgers or 3 gifts; "
              "every other order got SOLD_OUT")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "unsafe")
