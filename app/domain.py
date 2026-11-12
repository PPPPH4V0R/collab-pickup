# Domain layer: the menu, release batches, bonus gifts, orders, and every
# business rule about them. This module imports no web framework and no
# database code; it works on plain Python objects that the service layer
# loads and saves.
from datetime import timedelta
from decimal import Decimal

PENDING_PAYMENT = "PENDING_PAYMENT"
CANCELLED = "CANCELLED"
CURRENCY = "CAD"
PAYMENT_WINDOW = timedelta(minutes=15)    # how long the customer has to pay


# ---------- errors: each rule violation has a stable, machine-readable code ----------

class DomainError(Exception):
    code = "DOMAIN_ERROR"
    message = "A business rule was violated."

    def __init__(self, **details):
        super().__init__(self.message)
        self.details = details


class UnknownItem(DomainError):
    code = "UNKNOWN_ITEM"
    message = "The order refers to an item that is not on the menu."


class PerOrderLimit(DomainError):
    code = "PER_ORDER_LIMIT"
    message = "The order asks for more units of an item than one order may take."


class SoldOut(DomainError):
    code = "SOLD_OUT"
    message = "Not enough units of an item are on sale right now."


class OrderNotFound(DomainError):
    code = "ORDER_NOT_FOUND"
    message = "No such order."


class ItemNotFound(DomainError):
    code = "ITEM_NOT_FOUND"
    message = "No such item."


class OrderNotCancellable(DomainError):
    code = "ORDER_NOT_CANCELLABLE"
    message = "Only an order that is still waiting for payment can be cancelled."


class BatchNotAllowed(DomainError):
    code = "BATCH_NOT_ALLOWED"
    message = "Release batches can only be added to limited single items."


class UsernameTaken(DomainError):
    code = "USERNAME_TAKEN"
    message = "This username is already taken."


# ---------- accounts ----------

def new_customer(user_id, username, password_hash):
    """Anyone may sign up, but only as a customer: staff accounts are
    created by the shop, never through registration."""
    return {"id": user_id, "username": username,
            "password_hash": password_hash, "role": "customer"}


# ---------- the objects ----------

class Item:
    def __init__(self, id, name, kind, price, limited, per_order_limit, components=None):
        self.id, self.name, self.kind = id, name, kind
        self.price = Decimal(price)
        self.limited = limited                     # sold only from release batches?
        self.per_order_limit = per_order_limit     # None = no limit
        self.components = components or {}         # combo only: item_id -> qty

    @property
    def is_combo(self):
        return self.kind == "combo"


class Batch:
    """Units of one limited item released at one time (contended resource 1)."""
    def __init__(self, id, item_id, release_at, quantity, remaining):
        self.id, self.item_id, self.release_at = id, item_id, release_at
        self.quantity, self.remaining = quantity, remaining


class BonusStock:
    """Bonus gifts left for one combo (contended resource 2)."""
    def __init__(self, combo_id, remaining):
        self.combo_id, self.remaining = combo_id, remaining


class OrderLine:
    def __init__(self, item_id, qty, unit_price):
        self.item_id, self.qty, self.unit_price = item_id, qty, unit_price


class Claim:
    """qty units of item_id taken from batch_id; a cancel puts them back there."""
    def __init__(self, batch_id, item_id, qty):
        self.batch_id, self.item_id, self.qty = batch_id, item_id, qty


class Bonus:
    """One combo unit in an order, and whether it came with a bonus gift."""
    def __init__(self, combo_id, included):
        self.combo_id, self.included = combo_id, included


class Order:
    def __init__(self, id, user_id, status, total, currency, payment_due_by,
                 created_at, lines, claims, bonuses):
        self.id, self.user_id, self.status = id, user_id, status
        self.total, self.currency = total, currency
        self.payment_due_by, self.created_at = payment_due_by, created_at
        self.lines, self.claims, self.bonuses = lines, claims, bonuses

    def cancel(self):
        """Move the order to CANCELLED. Returns True when its units and bonus
        gifts must be given back, False when it was already cancelled
        (cancelling twice is not an error, and gives nothing back twice)."""
        if self.status == CANCELLED:
            return False
        if self.status != PENDING_PAYMENT:
            raise OrderNotCancellable(orderId=self.id, status=self.status)
        self.status = CANCELLED
        return True


# ---------- rules for placing an order ----------

def units_needed(wanted, items):
    """Turn the order lines into single-item unit counts. A combo is
    expanded into its components, so a Hero Set and a Hero Burger both
    count against the same burger stock.
    wanted: list of (item_id, qty). Returns {single item_id: qty}."""
    units = {}
    for item_id, qty in wanted:
        item = items.get(item_id)
        if item is None:
            raise UnknownItem(itemId=item_id)
        parts = item.components if item.is_combo else {item_id: 1}
        for part_id, part_qty in parts.items():
            units[part_id] = units.get(part_id, 0) + part_qty * qty
    return units


def check_per_order_limits(units, items):
    """An item's per-order limit counts every unit of it in the order,
    whether ordered alone or inside a combo."""
    for item_id, qty in sorted(units.items()):
        limit = items[item_id].per_order_limit
        if limit is not None and qty > limit:
            raise PerOrderLimit(itemId=item_id, limit=limit, requested=qty)


def units_left(item_id, batches):
    """Units of an item still on sale: the sum over its released batches."""
    return sum(b.remaining for b in batches if b.item_id == item_id)


def place_order(order_id, user_id, wanted, units, items, batches, bonus_stock, now):
    """Build the order and take its units and bonus gifts.
    batches: the released batches of the ordered limited items, earliest first.
    bonus_stock: {combo_id: BonusStock} for the ordered combos.
    Changes batches and bonus_stock in place; the caller saves them."""
    # 1. Check every limited item before taking anything, so a sold-out
    #    item leaves all stock untouched.
    for item_id, qty in sorted(units.items()):
        if items[item_id].limited and units_left(item_id, batches) < qty:
            raise SoldOut(itemId=item_id, requested=qty,
                          available=units_left(item_id, batches))

    # 2. Take units, starting with the earliest released batch.
    claims = []
    for item_id, qty in sorted(units.items()):
        if items[item_id].limited:
            claims += _take_from_batches(item_id, qty, batches)

    # 3. Each combo unit gets a bonus gift if one is left. Running out of
    #    gifts never blocks the order; it is recorded as included=False.
    bonuses = []
    for item_id, qty in wanted:
        if items[item_id].is_combo:
            for _ in range(qty):
                stock = bonus_stock.get(item_id)
                included = stock is not None and stock.remaining > 0
                if included:
                    stock.remaining -= 1
                bonuses.append(Bonus(item_id, included))

    # 4. Price the order.
    lines = [OrderLine(item_id, qty, items[item_id].price) for item_id, qty in wanted]
    total = sum((line.unit_price * line.qty for line in lines), Decimal("0.00"))

    return Order(order_id, user_id, PENDING_PAYMENT, total, CURRENCY,
                 now + PAYMENT_WINDOW, now, lines, claims, bonuses)


def _take_from_batches(item_id, qty, batches):
    claims = []
    for batch in batches:
        if qty == 0:
            break
        if batch.item_id != item_id or batch.remaining == 0:
            continue
        taken = min(qty, batch.remaining)
        batch.remaining -= taken
        qty -= taken
        claims.append(Claim(batch.id, item_id, taken))
    return claims


# ---------- rules for cancelling ----------

def give_back(order, batches, bonus_stock):
    """Return a cancelled order's units to the batches they came from,
    and its bonus gifts to the combo's count.
    batches: {batch_id: Batch}; bonus_stock: {combo_id: BonusStock}."""
    for claim in order.claims:
        batches[claim.batch_id].remaining += claim.qty
    for bonus in order.bonuses:
        if bonus.included:
            bonus_stock[bonus.combo_id].remaining += 1


# ---------- rules for the menu and for staff ----------

def available(item, items, batches):
    """How many of this menu entry can be ordered now; None = unlimited.
    A combo is limited by its scarcest limited component."""
    if not item.is_combo:
        return units_left(item.id, batches) if item.limited else None
    counts = [units_left(part_id, batches) // qty
              for part_id, qty in item.components.items() if items[part_id].limited]
    return min(counts) if counts else None


def new_batch(batch_id, item, release_at, quantity):
    """Staff schedule a release batch. Only limited single items are sold
    from batches; a combo always draws on its components' batches."""
    if item.is_combo or not item.limited:
        raise BatchNotAllowed(itemId=item.id)
    return Batch(batch_id, item.id, release_at, quantity, quantity)
