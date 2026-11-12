# Tests for the service layer against the real PostgreSQL database
# (DATABASE_URL from .env). Every test starts from the demo data, so these
# tests ERASE whatever is in that database.
# Run from the project root: python -m pytest -q tests/test_service.py
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from app import domain
from app.config import settings
from app.postgres_repository import PostgresRepository, make_engine
from app.service import OrderService
import seed

engine = make_engine(settings.database_url)
HERO_SET = [{"itemId": "combo-hero-set", "qty": 1}]


@pytest.fixture
def service():
    seed.reset(engine)
    return OrderService(PostgresRepository(engine))


def remaining(batch_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT remaining FROM batches WHERE id = :id"),
                            {"id": batch_id}).scalar()


def gifts_left():
    with engine.connect() as conn:
        return conn.execute(text("SELECT remaining FROM bonus_gifts"
                                 " WHERE combo_id = 'combo-hero-set'")).scalar()


def order_count():
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()


def test_order_takes_units_and_a_gift(service):
    out = service.place_order("u-alice", "k1", HERO_SET)
    assert out.ok and out.value["status"] == "PENDING_PAYMENT"
    assert (remaining("b-burger-1"), remaining("b-soda-1"), gifts_left()) == (9, 9, 2)


def test_same_key_same_body_replays_one_order(service):
    first = service.place_order("u-alice", "k1", HERO_SET)
    again = service.place_order("u-alice", "k1", HERO_SET)
    assert again.replayed
    assert again.value["orderId"] == first.value["orderId"]
    assert order_count() == 1
    assert remaining("b-burger-1") == 9


def test_same_key_different_body_is_refused(service):
    service.place_order("u-alice", "k1", HERO_SET)
    out = service.place_order("u-alice", "k1", [{"itemId": "fries", "qty": 1}])
    assert out.code == "IDEMPOTENCY_KEY_REUSED"
    assert order_count() == 1


def test_customer_cannot_read_another_customers_order(service):
    order_id = service.place_order("u-alice", "k1", HERO_SET).value["orderId"]
    with pytest.raises(domain.OrderNotFound):
        service.get_order("u-bob", order_id)


def test_customer_cannot_cancel_another_customers_order(service):
    order_id = service.place_order("u-alice", "k1", HERO_SET).value["orderId"]
    with pytest.raises(domain.OrderNotFound):
        service.cancel_order("u-bob", order_id)
    assert service.get_order("u-alice", order_id)["status"] == "PENDING_PAYMENT"
    assert (remaining("b-burger-1"), gifts_left()) == (9, 2)


def test_cancel_returns_units_to_their_batches_and_the_gift(service):
    out = service.place_order("u-alice", "k1", HERO_SET)
    service.cancel_order("u-alice", out.value["orderId"])
    assert (remaining("b-burger-1"), remaining("b-soda-1"), gifts_left()) == (10, 10, 3)


def test_concurrent_sign_ups_with_one_username_create_one_account(service):
    # 8 threads register "carol" at the same moment: the UNIQUE username with
    # ON CONFLICT DO NOTHING lets exactly one win; the others get
    # UsernameTaken (409), never a database error (500).
    def sign_up(n):
        try:
            service.register("carol", f"password-{n}")
            return "created"
        except domain.UsernameTaken:
            return "taken"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(sign_up, range(8)))
    assert sorted(results) == ["created"] + ["taken"] * 7
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'carol'")).scalar() == 1


def test_sold_out_order_changes_nothing(service):
    out = service.place_order("u-alice", "k1", [{"itemId": "drink-blue-soda", "qty": 11}])
    assert out.code == "SOLD_OUT"
    assert order_count() == 0
    assert remaining("b-soda-1") == 10


def test_new_limited_item_sells_after_staff_add_a_batch(service):
    service.add_menu_item("cake", "Cake", "single", "6.00", True, None, None, None)
    sold_out = service.place_order("u-alice", "k1", [{"itemId": "cake", "qty": 1}])
    assert sold_out.code == "SOLD_OUT"                    # no batch yet
    service.add_batch("cake", datetime.now(timezone.utc), 3)
    out = service.place_order("u-alice", "k2", [{"itemId": "cake", "qty": 1}])
    assert out.ok and out.value["claimedUnits"][0]["itemId"] == "cake"


def test_adding_gifts_while_orders_take_them_loses_nothing(service):
    # 20 Hero Set orders (only 10 burgers, so 10 succeed) race against
    # 10 staff requests that each add 1 gift. The orders lock the gift row
    # and write it back; the top-ups add in one UPDATE. If either side lost
    # an update, the books would not balance.
    def order(n):
        return service.place_order("u-alice", f"k{n}", HERO_SET)
    def top_up(_):
        return service.add_bonus_gifts("combo-hero-set", 1)
    with ThreadPoolExecutor(max_workers=30) as pool:
        orders = [pool.submit(order, n) for n in range(20)]
        top_ups = [pool.submit(top_up, n) for n in range(10)]
        results = [f.result() for f in orders] + [f.result() for f in top_ups]
    with engine.connect() as conn:
        given = conn.execute(text("SELECT COUNT(*) FROM order_bonuses WHERE included")).scalar()
    assert sum(1 for r in results[:20] if r.ok) == 10
    assert gifts_left() == 3 + 10 - given                 # start + added - handed out

