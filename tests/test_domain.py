# Unit tests for the business rules in app/domain.py.
# Plain Python objects only: no database, no web framework.
# Run from the project root: python -m pytest -q tests/test_domain.py
from datetime import datetime, timezone
import pytest
from app.domain import (Batch, BonusStock, Item, Order, BatchNotAllowed, InvalidItem,
                        NotACombo, OrderNotCancellable, PerOrderLimit, SoldOut, UnknownItem,
                        available, check_per_order_limits, check_takes_bonus_gifts, give_back,
                        new_batch, new_menu_item, place_order, units_needed,
                        PENDING_PAYMENT, CANCELLED)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

# The demo menu: burger (limited, max 2 per order), soda (limited), fries (unlimited),
# and the Hero Set combo = 1 burger + 1 soda.
ITEMS = {
    "burger": Item("burger", "Hero Burger", "single", "14.00", True, 2),
    "soda": Item("soda", "Blue Soda", "single", "5.50", True, None),
    "fries": Item("fries", "Fries", "single", "4.50", False, None),
    "set": Item("set", "Hero Set", "combo", "19.00", False, None, {"burger": 1, "soda": 1}),
}


def order(wanted, batches, gifts):
    """Run the domain's place_order on the demo menu."""
    units = units_needed(wanted, ITEMS)
    return place_order("ord_1", "u-alice", wanted, units, ITEMS, batches, gifts, NOW)


# ---------- expanding combos and per-order limits ----------

def test_combo_expands_into_its_items():
    assert units_needed([("set", 2), ("soda", 1)], ITEMS) == {"burger": 2, "soda": 3}


def test_unknown_item_is_rejected():
    with pytest.raises(UnknownItem):
        units_needed([("pizza", 1)], ITEMS)


def test_per_order_limit_on_single_item():
    with pytest.raises(PerOrderLimit):
        check_per_order_limits(units_needed([("burger", 3)], ITEMS), ITEMS)


def test_per_order_limit_counts_items_inside_combos():
    # 2 burgers alone + 1 burger inside the combo = 3 > limit 2
    with pytest.raises(PerOrderLimit):
        check_per_order_limits(units_needed([("burger", 2), ("set", 1)], ITEMS), ITEMS)


def test_order_at_the_limit_is_allowed():
    check_per_order_limits(units_needed([("burger", 1), ("set", 1)], ITEMS), ITEMS)


# ---------- taking units from batches ----------

def test_units_come_from_the_earliest_batch():
    early = Batch("b1", "burger", NOW, 10, 10)
    late = Batch("b2", "burger", NOW, 6, 6)
    placed = order([("burger", 2)], [early, late], {})
    assert [(c.batch_id, c.qty) for c in placed.claims] == [("b1", 2)]
    assert (early.remaining, late.remaining) == (8, 6)


def test_units_can_span_two_batches():
    early = Batch("b1", "burger", NOW, 10, 1)
    late = Batch("b2", "burger", NOW, 6, 6)
    placed = order([("burger", 2)], [early, late], {})
    assert [(c.batch_id, c.qty) for c in placed.claims] == [("b1", 1), ("b2", 1)]
    assert (early.remaining, late.remaining) == (0, 5)


def test_sold_out_leaves_all_stock_untouched():
    burgers = Batch("b1", "burger", NOW, 10, 5)
    sodas = Batch("s1", "soda", NOW, 10, 0)
    gifts = {"set": BonusStock("set", 3)}
    with pytest.raises(SoldOut):
        order([("set", 1)], [burgers, sodas], gifts)
    assert (burgers.remaining, sodas.remaining, gifts["set"].remaining) == (5, 0, 3)


def test_limited_item_with_no_released_batch_is_sold_out():
    with pytest.raises(SoldOut):
        order([("burger", 1)], [], {})


def test_unlimited_item_needs_no_batch():
    placed = order([("fries", 3)], [], {})
    assert placed.claims == []
    assert str(placed.total) == "13.50"


def test_new_order_waits_for_payment_and_has_a_total():
    placed = order([("set", 1), ("soda", 1)],
                   [Batch("b1", "burger", NOW, 10, 10), Batch("s1", "soda", NOW, 10, 10)], {})
    assert placed.status == PENDING_PAYMENT
    assert str(placed.total) == "24.50"


# ---------- bonus gifts ----------

def test_combo_gets_a_gift_while_gifts_last():
    gifts = {"set": BonusStock("set", 3)}
    placed = order([("set", 1)], [Batch("b1", "burger", NOW, 10, 10),
                                  Batch("s1", "soda", NOW, 10, 10)], gifts)
    assert [b.included for b in placed.bonuses] == [True]
    assert gifts["set"].remaining == 2


def test_combo_still_sells_when_gifts_run_out():
    gifts = {"set": BonusStock("set", 0)}
    placed = order([("set", 1)], [Batch("b1", "burger", NOW, 10, 10),
                                  Batch("s1", "soda", NOW, 10, 10)], gifts)
    assert [b.included for b in placed.bonuses] == [False]
    assert placed.status == PENDING_PAYMENT


def test_gifts_are_given_one_per_combo_unit():
    gifts = {"set": BonusStock("set", 1)}
    placed = order([("set", 2)], [Batch("b1", "burger", NOW, 10, 10),
                                  Batch("s1", "soda", NOW, 10, 10)], gifts)
    assert [b.included for b in placed.bonuses] == [True, False]
    assert gifts["set"].remaining == 0


# ---------- cancelling ----------

def test_cancel_gives_units_and_gift_back():
    burgers, sodas = Batch("b1", "burger", NOW, 10, 10), Batch("s1", "soda", NOW, 10, 10)
    gifts = {"set": BonusStock("set", 3)}
    placed = order([("set", 1)], [burgers, sodas], gifts)
    assert placed.cancel() is True
    give_back(placed, {"b1": burgers, "s1": sodas}, gifts)
    assert (burgers.remaining, sodas.remaining, gifts["set"].remaining) == (10, 10, 3)
    assert placed.status == CANCELLED


def test_cancelling_twice_gives_nothing_back_the_second_time():
    placed = order([("fries", 1)], [], {})
    assert placed.cancel() is True
    assert placed.cancel() is False


def test_only_pending_orders_can_be_cancelled():
    paid = Order("ord_1", "u-alice", "PAID", 0, "CAD", NOW, NOW, [], [], [])
    with pytest.raises(OrderNotCancellable):
        paid.cancel()


# ---------- menu availability and staff rules ----------

def test_combo_availability_is_its_scarcest_component():
    batches = [Batch("b1", "burger", NOW, 10, 7), Batch("s1", "soda", NOW, 10, 3)]
    assert available(ITEMS["set"], ITEMS, batches) == 3


def test_unlimited_item_has_no_availability_number():
    assert available(ITEMS["fries"], ITEMS, []) is None


def test_new_batch_for_limited_single_item():
    batch = new_batch("b9", ITEMS["burger"], NOW, 5)
    assert (batch.item_id, batch.quantity, batch.remaining) == ("burger", 5, 5)


def test_new_batch_refused_for_a_combo():
    with pytest.raises(BatchNotAllowed):
        new_batch("b9", ITEMS["set"], NOW, 5)


def test_new_batch_refused_for_an_unlimited_item():
    with pytest.raises(BatchNotAllowed):
        new_batch("b9", ITEMS["fries"], NOW, 5)


# ---------- staff adding items and combos ----------

def new_combo(components, **changes):
    fields = dict(item_id="duo", name="Duo", kind="combo", price="9.50", limited=None,
                  per_order_limit=None, components=components, bonus_gifts=2, items=ITEMS)
    fields.update(changes)
    return new_menu_item(**fields)


def test_new_combo_with_its_gifts():
    combo, gifts = new_combo([("soda", 2)])
    assert combo.is_combo and combo.components == {"soda": 2}
    assert (gifts.combo_id, gifts.remaining) == ("duo", 2)


def test_new_limited_single_item_has_no_stock_until_a_batch_is_added():
    item, gifts = new_menu_item("cake", "Cake", "single", "6.00", True, 1, [], None, ITEMS)
    assert item.limited and gifts is None
    assert available(item, {**ITEMS, "cake": item}, []) == 0


def test_combo_needs_components():
    with pytest.raises(InvalidItem):
        new_combo([])


def test_combo_cannot_contain_a_combo():
    with pytest.raises(InvalidItem):
        new_combo([("set", 1)])


def test_combo_components_must_exist():
    with pytest.raises(InvalidItem):
        new_combo([("pizza", 1)])


def test_combo_lists_each_component_once():
    with pytest.raises(InvalidItem):
        new_combo([("soda", 1), ("soda", 1)])


def test_combo_has_no_per_order_limit_of_its_own():
    with pytest.raises(InvalidItem):
        new_combo([("soda", 1)], per_order_limit=2)


def test_single_item_cannot_have_components():
    with pytest.raises(InvalidItem):
        new_menu_item("x", "X", "single", "1.00", False, None, [("soda", 1)], None, ITEMS)


def test_price_must_be_above_zero():
    with pytest.raises(InvalidItem):
        new_combo([("soda", 1)], price="0.00")


def test_only_combos_take_bonus_gifts():
    check_takes_bonus_gifts(ITEMS["set"])
    with pytest.raises(NotACombo):
        check_takes_bonus_gifts(ITEMS["burger"])
