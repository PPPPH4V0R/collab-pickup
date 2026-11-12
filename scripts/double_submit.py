# Idempotency demo against the running service.
#  1. Alice's app sends the SAME order with the SAME Idempotency-Key 8 times
#     at once (a double-click plus retries). Exactly one order is placed;
#     the others replay its answer with "Idempotency-Replayed: true".
#  2. The same key with a DIFFERENT body is refused with 422.
#
# Start the service first, then from the project root:
#   python scripts/double_submit.py
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # import app/ and seed.py

import httpx
from sqlalchemy import create_engine
from app.config import settings
import seed
from seed import DEMO_PASSWORD

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
CLICKS = 8


def login(username):
    r = httpx.post(f"{API}/auth/login",
                   json={"username": username, "password": DEMO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def menu_available(item_id):
    items = httpx.get(f"{API}/menu").json()["items"]
    return next(i["available"] for i in items if i["id"] == item_id)


seed.reset(create_engine(settings.database_url))
alice = login("alice")
key = str(uuid.uuid4())
body = {"lines": [{"itemId": "combo-hero-set", "qty": 1}]}
headers = {**alice, "Idempotency-Key": key}

print(f"1) {CLICKS} identical requests at once, Idempotency-Key {key}")
with ThreadPoolExecutor(max_workers=CLICKS) as pool:
    responses = list(pool.map(lambda _: httpx.post(f"{API}/orders", json=body, headers=headers),
                              range(CLICKS)))
for n, r in enumerate(responses, 1):
    tag = "replayed" if r.headers.get("Idempotency-Replayed") == "true" else "placed"
    print(f"   request {n}: {r.status_code} {r.json()['orderId']}  ({tag})")

order_ids = {r.json()["orderId"] for r in responses}
my_orders = httpx.get(f"{API}/orders", headers=alice).json()["orders"]
print(f"   -> {len(order_ids)} distinct order id(s); Alice has {len(my_orders)} order(s); "
      f"Hero Set available: {menu_available('combo-hero-set')} of 10")

print("2) same key, different body (2 Hero Sets instead of 1)")
r = httpx.post(f"{API}/orders", json={"lines": [{"itemId": "combo-hero-set", "qty": 2}]},
               headers=headers)
print(f"   {r.status_code} {r.json()['error']['code']}")
