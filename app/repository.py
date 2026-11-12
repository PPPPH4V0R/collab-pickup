# Data layer: all SQL lives here. It turns rows into domain objects and
# back. A UnitOfWork is one database transaction: everything done through
# it commits together, or rolls back together if an exception escapes.
import json
from sqlalchemy import create_engine, text
from app.domain import Item, Batch, BonusStock, Order, OrderLine, Claim, Bonus


class DuplicateRequest(Exception):
    """Another request with the same idempotency key committed first.
    Our transaction is rolled back; the caller replays the winner's outcome."""


def make_engine(url):
    # READ COMMITTED is PostgreSQL's default; we set it explicitly because
    # the locking design depends on it: after waiting for a FOR UPDATE lock,
    # a statement sees the row as the previous holder committed it.
    # The pool is large enough for the 100-thread race demo to make progress.
    return create_engine(url, isolation_level="READ COMMITTED",
                         pool_size=10, max_overflow=20)


class Repository:
    def __init__(self, engine):
        self.engine = engine

    def unit_of_work(self):
        return UnitOfWork(self.engine)


class UnitOfWork:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        self.conn = self.engine.connect()
        self.conn.begin()
        return self

    def __exit__(self, exc_type, *args):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()
        return False                      # let the exception continue

    def _run(self, sql, params=None):
        return self.conn.execute(text(sql), params or {})

    # ---------- health ----------

    def ping(self):
        self._run("SELECT 1")

    # ---------- users ----------

    def find_user(self, username):
        return self._run("SELECT id, username, password_hash, role FROM users"
                         " WHERE username = :u", {"u": username}).mappings().first()

    # ---------- menu ----------

    def load_items(self):
        """Every menu entry, with each combo's components. Returns {id: Item}."""
        items = {}
        for r in self._run("SELECT id, name, kind, price, limited, per_order_limit"
                           " FROM items ORDER BY kind DESC, id").mappings():
            items[r["id"]] = Item(r["id"], r["name"], r["kind"], r["price"],
                                  r["limited"], r["per_order_limit"])
        for r in self._run("SELECT combo_id, item_id, qty FROM combo_components").mappings():
            items[r["combo_id"]].components[r["item_id"]] = r["qty"]
        return items

    def load_released_batches(self, item_ids, lock):
        """Batches of these items that are already on sale, earliest first.
        With lock=True the rows are locked with FOR UPDATE until commit, in
        the fixed order item_id -> release_at -> id. Every transaction locks
        batch rows in this same order, so two orders can never wait on each
        other in a circle (no deadlock)."""
        sql = ("SELECT id, item_id, release_at, quantity, remaining FROM batches"
               " WHERE item_id = ANY(:ids) AND release_at <= now()"
               " ORDER BY item_id, release_at, id")
        if lock:
            sql += " FOR UPDATE"
        return [Batch(**r) for r in self._run(sql, {"ids": list(item_ids)}).mappings()]

    def lock_batches(self, batch_ids):
        """Lock specific batches (used by cancel), in the same order as above.
        Returns {batch_id: Batch}."""
        rows = self._run("SELECT id, item_id, release_at, quantity, remaining FROM batches"
                         " WHERE id = ANY(:ids)"
                         " ORDER BY item_id, release_at, id FOR UPDATE",
                         {"ids": list(batch_ids)}).mappings()
        return {r["id"]: Batch(**r) for r in rows}

    def load_bonus_stock(self, combo_ids, lock):
        """Bonus gift counts for these combos, locked in combo_id order when
        lock=True. Bonus rows are always locked after batch rows.
        Returns {combo_id: BonusStock}."""
        sql = ("SELECT combo_id, remaining FROM bonus_gifts"
               " WHERE combo_id = ANY(:ids) ORDER BY combo_id")
        if lock:
            sql += " FOR UPDATE"
        rows = self._run(sql, {"ids": list(combo_ids)}).mappings()
        return {r["combo_id"]: BonusStock(r["combo_id"], r["remaining"]) for r in rows}

    def save_stock(self, batches, bonus_stocks):
        for b in batches:
            self._run("UPDATE batches SET remaining = :r WHERE id = :id",
                      {"r": b.remaining, "id": b.id})
        for s in bonus_stocks:
            self._run("UPDATE bonus_gifts SET remaining = :r WHERE combo_id = :id",
                      {"r": s.remaining, "id": s.combo_id})

    def add_batch(self, batch):
        self._run("INSERT INTO batches (id, item_id, release_at, quantity, remaining)"
                  " VALUES (:id, :item_id, :release_at, :quantity, :remaining)",
                  {"id": batch.id, "item_id": batch.item_id, "release_at": batch.release_at,
                   "quantity": batch.quantity, "remaining": batch.remaining})

    # ---------- orders ----------

    def add_order(self, order):
        self._run("INSERT INTO orders (id, user_id, status, total, currency,"
                  " payment_due_by, created_at)"
                  " VALUES (:id, :u, :s, :t, :c, :due, :at)",
                  {"id": order.id, "u": order.user_id, "s": order.status,
                   "t": order.total, "c": order.currency,
                   "due": order.payment_due_by, "at": order.created_at})
        for line in order.lines:
            self._run("INSERT INTO order_lines (order_id, item_id, qty, unit_price)"
                      " VALUES (:o, :i, :q, :p)",
                      {"o": order.id, "i": line.item_id, "q": line.qty, "p": line.unit_price})
        for claim in order.claims:
            self._run("INSERT INTO order_claims (order_id, batch_id, item_id, qty)"
                      " VALUES (:o, :b, :i, :q)",
                      {"o": order.id, "b": claim.batch_id, "i": claim.item_id, "q": claim.qty})
        for bonus in order.bonuses:
            self._run("INSERT INTO order_bonuses (order_id, combo_id, included)"
                      " VALUES (:o, :c, :inc)",
                      {"o": order.id, "c": bonus.combo_id, "inc": bonus.included})

    def get_order(self, order_id, user_id, lock=False):
        """An order is always looked up by its id AND its owner, so one
        customer can never load another customer's order."""
        sql = ("SELECT * FROM orders WHERE id = :id AND user_id = :u")
        if lock:
            sql += " FOR UPDATE"
        row = self._run(sql, {"id": order_id, "u": user_id}).mappings().first()
        return self._to_order(row) if row else None

    def list_orders(self, user_id):
        rows = self._run("SELECT * FROM orders WHERE user_id = :u ORDER BY created_at DESC",
                         {"u": user_id}).mappings().all()
        return [self._to_order(r) for r in rows]

    def save_order_status(self, order):
        self._run("UPDATE orders SET status = :s WHERE id = :id",
                  {"s": order.status, "id": order.id})

    def _to_order(self, row):
        p = {"o": row["id"]}
        lines = [OrderLine(r["item_id"], r["qty"], r["unit_price"]) for r in self._run(
            "SELECT item_id, qty, unit_price FROM order_lines WHERE order_id = :o ORDER BY id",
            p).mappings()]
        claims = [Claim(r["batch_id"], r["item_id"], r["qty"]) for r in self._run(
            "SELECT batch_id, item_id, qty FROM order_claims WHERE order_id = :o ORDER BY id",
            p).mappings()]
        bonuses = [Bonus(r["combo_id"], r["included"]) for r in self._run(
            "SELECT combo_id, included FROM order_bonuses WHERE order_id = :o ORDER BY id",
            p).mappings()]
        return Order(row["id"], row["user_id"], row["status"], row["total"], row["currency"],
                     row["payment_due_by"], row["created_at"], lines, claims, bonuses)

    # ---------- idempotency records ----------

    def find_outcome(self, user_id, key):
        """Returns (request_hash, stored outcome) or None."""
        row = self._run("SELECT request_hash, ok, code, value_json FROM idempotency_records"
                        " WHERE user_id = :u AND key = :k",
                        {"u": user_id, "k": key}).mappings().first()
        if row is None:
            return None
        return row["request_hash"], {"ok": row["ok"], "code": row["code"],
                                     "value": row["value_json"]}

    def record_outcome(self, user_id, key, request_hash, outcome):
        """Store the outcome in THIS transaction, next to the order it
        describes. The primary key (user_id, key) decides who wins: if a
        concurrent request already inserted the same key, PostgreSQL makes
        this INSERT wait until that transaction ends, then skips it (0 rows)."""
        inserted = self._run(
            "INSERT INTO idempotency_records (user_id, key, request_hash, ok, code, value_json)"
            " VALUES (:u, :k, :h, :ok, :code, CAST(:v AS jsonb))"
            " ON CONFLICT (user_id, key) DO NOTHING",
            {"u": user_id, "k": key, "h": request_hash, "ok": outcome["ok"],
             "code": outcome["code"], "v": json.dumps(outcome["value"])}).rowcount
        if inserted == 0:
            raise DuplicateRequest()
