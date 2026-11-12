# Tests for the service layer on the in-memory repository: no database,
# so they run in milliseconds. The same use cases are also tested against
# PostgreSQL in test_service.py.
# Run from the project root: python -m pytest -q tests/test_service_memory.py
from datetime import datetime, timedelta, timezone
import pytest
from app import auth, domain
from app.domain import Batch, BonusStock, Item
from app.memory_repository import MemoryRepository
from app.service import OrderService

HERO_SET = [{"itemId": "combo-hero-set", "qty": 1}]


@pytest.fixture
def service():
    """The demo menu: one burger batch and one soda batch on sale, 3 gifts."""
    an_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    repo = MemoryRepository(
        items=[Item("burger-hero", "Hero Burger", "single", "14.00", True, 2),
               Item("drink-blue-soda", "Blue Soda", "single", "5.50", True, None),
               Item("combo-hero-set", "Hero Set", "combo", "19.00", False, None,
                    {"burger-hero": 1, "drink-blue-soda": 1})],
        batches=[Batch("b-burger-1", "burger-hero", an_hour_ago, 10, 10),
                 Batch("b-soda-1", "drink-blue-soda", an_hour_ago, 10, 10)],
        bonus_stocks=[BonusStock("combo-hero-set", 3)])
    return OrderService(repo)


def stock(service):
    """(burgers on sale, sodas on sale, gifts left), as the menu shows them."""
    menu = {i["id"]: i for i in service.get_menu()["items"]}
    return (menu["burger-hero"]["available"], menu["drink-blue-soda"]["available"],
            menu["combo-hero-set"]["bonusRemaining"])


def test_order_takes_units_and_a_gift(service):
    out = service.place_order("u-alice", "k1", HERO_SET)
    assert out.ok and out.value["bonus"][0]["included"]
    assert stock(service) == (9, 9, 2)


def test_same_key_same_body_replays_one_order(service):
    first = service.place_order("u-alice", "k1", HERO_SET)
    again = service.place_order("u-alice", "k1", HERO_SET)
    assert again.replayed
    assert again.value["orderId"] == first.value["orderId"]
    assert len(service.list_orders("u-alice")["orders"]) == 1
    assert stock(service) == (9, 9, 2)


def test_same_key_different_body_is_refused(service):
    service.place_order("u-alice", "k1", HERO_SET)
    out = service.place_order("u-alice", "k1", [{"itemId": "burger-hero", "qty": 1}])
    assert out.code == "IDEMPOTENCY_KEY_REUSED"
    assert len(service.list_orders("u-alice")["orders"]) == 1


def test_same_key_from_another_customer_is_a_new_order(service):
    alice = service.place_order("u-alice", "k1", HERO_SET)
    bob = service.place_order("u-bob", "k1", HERO_SET)
    assert not bob.replayed
    assert bob.value["orderId"] != alice.value["orderId"]


def test_customer_cannot_read_another_customers_order(service):
    order_id = service.place_order("u-alice", "k1", HERO_SET).value["orderId"]
    with pytest.raises(domain.OrderNotFound):
        service.get_order("u-bob", order_id)


def test_customer_cannot_cancel_another_customers_order(service):
    order_id = service.place_order("u-alice", "k1", HERO_SET).value["orderId"]
    with pytest.raises(domain.OrderNotFound):
        service.cancel_order("u-bob", order_id)
    assert service.get_order("u-alice", order_id)["status"] == "PENDING_PAYMENT"
    assert stock(service) == (9, 9, 2)


def test_cancel_returns_units_and_the_gift(service):
    order_id = service.place_order("u-alice", "k1", HERO_SET).value["orderId"]
    assert service.cancel_order("u-alice", order_id)["status"] == "CANCELLED"
    assert stock(service) == (10, 10, 3)


def test_sold_out_order_changes_nothing(service):
    out = service.place_order("u-alice", "k1", [{"itemId": "drink-blue-soda", "qty": 11}])
    assert out.code == "SOLD_OUT"
    assert service.list_orders("u-alice")["orders"] == []
    assert stock(service) == (10, 10, 3)


def test_registered_user_is_a_customer_who_can_log_in(service):
    service.register("carol", "long-enough")
    token = service.login("carol", "long-enough")["accessToken"]
    assert auth.verify(token)["role"] == "customer"


def test_registering_a_taken_username_is_refused(service):
    service.register("carol", "long-enough")
    with pytest.raises(domain.UsernameTaken):
        service.register("carol", "another-password")
    with pytest.raises(auth.AuthError):                  # the first password still holds
        service.login("carol", "another-password")


def test_failed_transaction_leaves_no_trace(service):
    # An exception inside a unit of work throws away everything it did.
    with pytest.raises(RuntimeError):
        with service.repo.unit_of_work() as uow:
            batch = uow.load_released_batches(["burger-hero"], lock=True)[0]
            batch.remaining = 0
            uow.save_stock([batch], [])
            raise RuntimeError("crash before commit")
    assert stock(service) == (10, 10, 3)
