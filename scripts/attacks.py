# Security demo against the running service.
#  A. Tampered token: Alice edits her token's payload to say role=staff
#     but cannot re-sign it -> 401.
#  B. alg=none token: an unsigned token claiming to be staff -> 401.
#  C. IDOR: Bob tries to read and cancel Alice's order -> 404, exactly as
#     for an order that does not exist; Alice's order and stock are untouched.
#
# Start the service first, then from the project root:
#   python scripts/attacks.py
import base64
import datetime
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # import app/ and seed.py

import httpx
import jwt
from sqlalchemy import create_engine
from app import auth
from app.config import settings
import seed

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
NEW_BATCH = {"releaseAt": "2026-11-13T09:00:00-05:00", "quantity": 100}


def login(username):
    r = httpx.post(f"{API}/auth/login",
                   json={"username": username, "password": os.environ["DEMO_PASSWORD"]})
    return r.json()["accessToken"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def show(label, r):
    body = r.json()
    print(f"   {label}: {r.status_code} {body['error']['code'] if 'error' in body else 'OK'}")


def stock():
    items = {i["id"]: i for i in httpx.get(f"{API}/menu").json()["items"]}
    return (f"burger {items['burger-hero']['available']}, soda {items['drink-blue-soda']['available']}, "
            f"bonus gifts {items['combo-hero-set']['bonusRemaining']}")


seed.reset(create_engine(settings.database_url))
alice, bob = login("alice"), login("bob")

print("A) Tampered token: Alice changes role 'customer' -> 'staff' in the payload")
header, payload, signature = alice.split(".")
claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
claims["role"] = "staff"
forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
tampered = f"{header}.{forged_payload}.{signature}"
show("Alice's real token, add a batch  ", httpx.post(f"{API}/items/burger-hero/batches",
                                                      json=NEW_BATCH, headers=bearer(alice)))
show("tampered token, add a batch      ", httpx.post(f"{API}/items/burger-hero/batches",
                                                      json=NEW_BATCH, headers=bearer(tampered)))

print("B) alg=none: an unsigned token that claims to be staff")
now = datetime.datetime.now(datetime.timezone.utc)
unsigned = jwt.encode({"iss": auth.ISSUER, "aud": auth.AUDIENCE, "sub": "u-staff",
                       "role": "staff", "iat": now, "exp": now + datetime.timedelta(hours=1)},
                      key=None, algorithm="none")
show("unsigned token, add a batch      ", httpx.post(f"{API}/items/burger-hero/batches",
                                                      json=NEW_BATCH, headers=bearer(unsigned)))

print("C) IDOR: Bob goes after Alice's order")
r = httpx.post(f"{API}/orders", json={"lines": [{"itemId": "combo-hero-set", "qty": 1}]},
               headers={**bearer(alice), "Idempotency-Key": str(uuid.uuid4())})
order_id = r.json()["orderId"]
print(f"   Alice placed {order_id}; stock now: {stock()}")
show("Bob reads Alice's order          ", httpx.get(f"{API}/orders/{order_id}", headers=bearer(bob)))
show("Bob cancels Alice's order        ", httpx.post(f"{API}/orders/{order_id}/cancel",
                                                     headers=bearer(bob)))
show("Bob cancels a made-up order id   ", httpx.post(f"{API}/orders/ord_0000000000000000/cancel",
                                                     headers=bearer(bob)))
status = httpx.get(f"{API}/orders/{order_id}", headers=bearer(alice)).json()["status"]
print(f"   Alice's order is still {status}; stock still: {stock()}")
