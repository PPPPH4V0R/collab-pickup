# Data layer as an interface: what the service layer may ask of storage.
# The service depends only on these abstract classes. Two implementations:
#   postgres_repository.py -- PostgreSQL, the real one (row locks, SQL)
#   memory_repository.py   -- dictionaries, the test double
# main.py is the only place that chooses which one runs.
from abc import ABC, abstractmethod


class DuplicateRequest(Exception):
    """Another request with the same idempotency key committed first.
    Our transaction is rolled back; the caller replays the winner's outcome."""


class Repository(ABC):
    @abstractmethod
    def unit_of_work(self):
        """A new UnitOfWork (one transaction)."""


class UnitOfWork(ABC):
    """One use case, one transaction: everything done through it commits
    together when the with-block ends normally, and is rolled back when an
    exception escapes. Lock order, wherever lock=True: batches first, then
    bonus gifts (cancel locks its order row before both)."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *args):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False                      # let the exception continue

    @abstractmethod
    def commit(self): ...

    @abstractmethod
    def rollback(self): ...

    # ---------- health and users ----------

    @abstractmethod
    def ping(self):
        """Fails if the storage cannot be reached."""

    @abstractmethod
    def find_user(self, username):
        """{"id", "username", "password_hash", "role"} or None."""

    # ---------- menu and stock ----------

    @abstractmethod
    def load_items(self):
        """Every menu entry with its combo components: {item_id: Item}."""

    @abstractmethod
    def load_released_batches(self, item_ids, lock):
        """Batches of these items already on sale, ordered by item_id,
        release_at, id. lock=True: rivals wait until we commit."""

    @abstractmethod
    def lock_batches(self, batch_ids):
        """These batches, locked, in the same order: {batch_id: Batch}."""

    @abstractmethod
    def load_bonus_stock(self, combo_ids, lock):
        """Bonus gift counts by combo_id order: {combo_id: BonusStock}."""

    @abstractmethod
    def save_stock(self, batches, bonus_stocks):
        """Write back the remaining counts."""

    @abstractmethod
    def add_batch(self, batch): ...

    # ---------- orders ----------

    @abstractmethod
    def add_order(self, order):
        """The order with its lines, claims and bonuses."""

    @abstractmethod
    def get_order(self, order_id, user_id, lock=False):
        """The order only if it belongs to user_id, else None."""

    @abstractmethod
    def list_orders(self, user_id):
        """The user's orders, newest first."""

    @abstractmethod
    def save_order_status(self, order): ...

    # ---------- idempotency records ----------

    @abstractmethod
    def find_outcome(self, user_id, key):
        """(request_hash, stored outcome) or None."""

    @abstractmethod
    def record_outcome(self, user_id, key, request_hash, outcome):
        """Store the outcome in this transaction; raises DuplicateRequest if
        another request already holds (user_id, key)."""
