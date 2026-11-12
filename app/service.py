# Service layer: one method per use case. It opens the transaction,
# loads domain objects through the repository, lets the domain apply the
# rules, saves the result, and returns plain dicts (the shapes promised by
# the contract). It does not know about HTTP status codes.
# Idempotency and the per-user ownership check also live here.
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from app import domain
from app.repository import DuplicateRequest


class Outcome:
    """Result of placing an order: the order, or a coded error, plus whether
    it was replayed from the idempotency record. It is stored as-is so a
    retry gets exactly the same answer."""
    def __init__(self, ok, value, code=None, replayed=False):
        self.ok, self.value, self.code, self.replayed = ok, value, code, replayed

    def stored(self):
        return {"ok": self.ok, "code": self.code, "value": self.value}


def error_body(code, message, details=None):
    """The one error shape of the contract: {code, message, details}."""
    return {"code": code, "message": message, "details": details or {}}


class OrderService:
    def __init__(self, repo):
        self.repo = repo

    # ---------- queries ----------

    def get_menu(self):
        with self.repo.unit_of_work() as uow:
            items = uow.load_items()
            batches = uow.load_released_batches(items.keys(), lock=False)
            gifts = uow.load_bonus_stock(items.keys(), lock=False)
        return {"items": [self._menu_entry(item, items, batches, gifts)
                          for item in items.values()]}

    def list_orders(self, user_id):
        with self.repo.unit_of_work() as uow:
            return {"orders": [self._order_dto(o) for o in uow.list_orders(user_id)]}

    def get_order(self, user_id, order_id):
        with self.repo.unit_of_work() as uow:
            order = uow.get_order(order_id, user_id)
        if order is None:
            # Someone else's order looks exactly like a missing one, so the
            # caller learns nothing about which order ids exist.
            raise domain.OrderNotFound(orderId=order_id)
        return self._order_dto(order)

    # ---------- placing an order ----------

    def place_order(self, user_id, key, lines, demo_delay=0.0):
        """lines: [{"itemId": ..., "qty": ...}]. One transaction locks the
        stock rows, places the order, and stores the idempotency record,
        so a retried request can never place a second order."""
        request_hash = self._fingerprint(lines)

        def attempt():
            with self.repo.unit_of_work() as uow:
                outcome = self._place(uow, user_id, lines, lock=True, demo_delay=demo_delay)
                uow.record_outcome(user_id, key, request_hash, outcome.stored())
                return outcome                                   # COMMIT on exit
        return self._idempotent(user_id, key, request_hash, attempt)

    def place_order_unsafe(self, user_id, lines, demo_delay=0.0):
        """Control group for the race demo ONLY (never called by the API).
        Exactly the same steps, except the stock rows are read without
        FOR UPDATE: concurrent orders all read the same 'remaining', and
        each writes back its own result (a lost update, i.e. overselling)."""
        with self.repo.unit_of_work() as uow:
            return self._place(uow, user_id, lines, lock=False, demo_delay=demo_delay)

    def _place(self, uow, user_id, lines, lock, demo_delay):
        wanted = [(line["itemId"], line["qty"]) for line in lines]
        try:
            items = uow.load_items()
            units = domain.units_needed(wanted, items)                 # expand combos
            domain.check_per_order_limits(units, items)                # per-order limits
            batches = uow.load_released_batches(units.keys(), lock=lock)   # lock batches
            combo_ids = [item_id for item_id, _ in wanted if items[item_id].is_combo]
            gifts = uow.load_bonus_stock(combo_ids, lock=lock)         # then lock gifts
            order = domain.place_order(self._new_order_id(), user_id, wanted, units,
                                       items, batches, gifts, datetime.now(timezone.utc))
        except domain.DomainError as err:
            return Outcome(False, error_body(err.code, err.message, err.details), err.code)
        if demo_delay:
            time.sleep(demo_delay)        # demo only: widen the gap between check and write
        uow.save_stock(batches, gifts.values())
        uow.add_order(order)
        return Outcome(True, self._order_dto(order))

    def _idempotent(self, user_id, key, request_hash, attempt):
        seen = self._find_outcome(user_id, key)          # fast path: seen this key before?
        if seen is None:
            try:
                return attempt()                         # records its own outcome
            except DuplicateRequest:                     # a twin request committed first;
                seen = self._find_outcome(user_id, key)  # our work was rolled back
        stored_hash, stored = seen
        if stored_hash != request_hash:
            return Outcome(False, error_body(
                "IDEMPOTENCY_KEY_REUSED",
                "This Idempotency-Key was already used with a different request."),
                "IDEMPOTENCY_KEY_REUSED")
        return Outcome(stored["ok"], stored["value"], stored["code"], replayed=True)

    def _find_outcome(self, user_id, key):
        with self.repo.unit_of_work() as uow:
            return uow.find_outcome(user_id, key)

    def _fingerprint(self, lines):
        """Bind the key to WHAT was requested: the operation and the body.
        The same key with a different body is a reuse, not a retry."""
        body = json.dumps(lines, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"POST /orders\n{body}".encode()).hexdigest()

    # ---------- cancelling ----------

    def cancel_order(self, user_id, order_id):
        with self.repo.unit_of_work() as uow:
            # Ownership check: looked up by id AND owner, locked so two
            # cancels of the same order cannot both give units back.
            order = uow.get_order(order_id, user_id, lock=True)
            if order is None:
                raise domain.OrderNotFound(orderId=order_id)
            if order.cancel():
                # Same lock order as placing an order: batches, then gifts.
                batches = uow.lock_batches(c.batch_id for c in order.claims)
                gifts = uow.load_bonus_stock(
                    (b.combo_id for b in order.bonuses if b.included), lock=True)
                domain.give_back(order, batches, gifts)
                uow.save_stock(batches.values(), gifts.values())
                uow.save_order_status(order)
        return self._order_dto(order)

    # ---------- staff ----------

    def add_batch(self, item_id, release_at, quantity):
        with self.repo.unit_of_work() as uow:
            item = uow.load_items().get(item_id)
            if item is None:
                raise domain.ItemNotFound(itemId=item_id)
            batch = domain.new_batch(self._new_batch_id(), item, release_at, quantity)
            uow.add_batch(batch)
        return {"batchId": batch.id, "itemId": batch.item_id,
                "releaseAt": _iso(batch.release_at),
                "quantity": batch.quantity, "remaining": batch.remaining}

    # ---------- ids and DTOs: the shapes the contract promises ----------

    def _new_order_id(self):
        return f"ord_{secrets.token_hex(8)}"      # random, so ids cannot be guessed

    def _new_batch_id(self):
        return f"b-{secrets.token_hex(4)}"

    def _menu_entry(self, item, items, batches, gifts):
        entry = {"id": item.id, "name": item.name, "kind": item.kind,
                 "price": _money(item.price), "perOrderLimit": item.per_order_limit,
                 "available": domain.available(item, items, batches)}
        if item.is_combo:
            gift = gifts.get(item.id)
            entry["components"] = [{"itemId": i, "qty": q} for i, q in item.components.items()]
            entry["bonusRemaining"] = gift.remaining if gift else 0
            entry["bonusAvailable"] = gift is not None and gift.remaining > 0
        return entry

    def _order_dto(self, order):
        return {
            "orderId": order.id,
            "status": order.status,
            "total": _money(order.total),
            "currency": order.currency,
            "paymentDueBy": _iso(order.payment_due_by),
            "createdAt": _iso(order.created_at),
            "lines": [{"itemId": l.item_id, "qty": l.qty, "unitPrice": _money(l.unit_price)}
                      for l in order.lines],
            "claimedUnits": [{"itemId": c.item_id, "batchId": c.batch_id, "qty": c.qty}
                             for c in order.claims],
            "bonus": [{"comboId": b.combo_id, "included": b.included,
                       "message": "Bonus gift included." if b.included
                       else "Bonus gifts for this combo have run out."}
                      for b in order.bonuses],
        }


def _money(amount):
    return f"{amount:.2f}"


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
