# The in-memory implementation of the repository interface: the test double.
# All data sits in dictionaries. A unit of work copies the data when it
# starts, works on that copy, and on commit makes the copy the new data;
# on rollback the copy is simply thrown away. Every read hands out a fresh
# copy of the object, so a change the service does not save is lost, just
# as with a database row.
import copy
from datetime import datetime, timezone
from app.repository import DuplicateRequest, Repository, UnitOfWork


class MemoryRepository(Repository):
    def __init__(self, users=(), items=(), batches=(), bonus_stocks=()):
        """users: dicts with id, username, password_hash, role;
        items, batches, bonus_stocks: domain objects."""
        self.data = {
            "users": {u["username"]: dict(u) for u in users},
            "items": {i.id: i for i in items},
            "batches": {b.id: b for b in batches},
            "bonus": {s.combo_id: s for s in bonus_stocks},
            "orders": {},
            "outcomes": {},              # (user_id, key) -> (request_hash, outcome)
        }

    def unit_of_work(self):
        return MemoryUnitOfWork(self)


class MemoryUnitOfWork(UnitOfWork):
    # The lock arguments are ignored: these tests run on one thread, so
    # nothing can interleave. Correctness under concurrency is proven on
    # PostgreSQL (postgres_repository.py and scripts/race.py).

    def __init__(self, repo):
        self.repo = repo

    def __enter__(self):
        self.data = copy.deepcopy(self.repo.data)
        return self

    def commit(self):
        self.repo.data = self.data

    def rollback(self):
        pass                              # the copy is discarded

    # ---------- health and users ----------

    def ping(self):
        pass

    def find_user(self, username):
        return copy.deepcopy(self.data["users"].get(username))

    def add_user(self, user):
        if user["username"] in self.data["users"]:
            return False
        self.data["users"][user["username"]] = dict(user)
        return True

    # ---------- menu and stock ----------

    def load_items(self):
        return copy.deepcopy(self.data["items"])

    def load_released_batches(self, item_ids, lock):
        now = datetime.now(timezone.utc)
        wanted = set(item_ids)
        batches = [b for b in self.data["batches"].values()
                   if b.item_id in wanted and b.release_at <= now]
        batches.sort(key=lambda b: (b.item_id, b.release_at, b.id))
        return copy.deepcopy(batches)

    def lock_batches(self, batch_ids):
        return {i: copy.deepcopy(self.data["batches"][i]) for i in batch_ids}

    def load_bonus_stock(self, combo_ids, lock):
        return {i: copy.deepcopy(self.data["bonus"][i])
                for i in combo_ids if i in self.data["bonus"]}

    def save_stock(self, batches, bonus_stocks):
        for b in batches:
            self.data["batches"][b.id] = copy.deepcopy(b)
        for s in bonus_stocks:
            self.data["bonus"][s.combo_id] = copy.deepcopy(s)

    def add_batch(self, batch):
        self.data["batches"][batch.id] = copy.deepcopy(batch)

    # ---------- orders ----------

    def add_order(self, order):
        self.data["orders"][order.id] = copy.deepcopy(order)

    def get_order(self, order_id, user_id, lock=False):
        order = self.data["orders"].get(order_id)
        if order is None or order.user_id != user_id:     # by id AND owner
            return None
        return copy.deepcopy(order)

    def list_orders(self, user_id):
        mine = [o for o in self.data["orders"].values() if o.user_id == user_id]
        mine.sort(key=lambda o: o.created_at, reverse=True)
        return copy.deepcopy(mine)

    def save_order_status(self, order):
        self.data["orders"][order.id].status = order.status

    # ---------- idempotency records ----------

    def find_outcome(self, user_id, key):
        return copy.deepcopy(self.data["outcomes"].get((user_id, key)))

    def record_outcome(self, user_id, key, request_hash, outcome):
        if (user_id, key) in self.data["outcomes"]:
            raise DuplicateRequest()
        self.data["outcomes"][(user_id, key)] = (request_hash, copy.deepcopy(outcome))
