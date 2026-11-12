# Tests for the HTTP layer with FastAPI's TestClient (no server needed).
# Tokens are made with auth.issue(), so no password is needed; these
# requests are all refused at the door before they reach the database.
# Run from the project root: python -m pytest -q tests/test_api.py
from fastapi.testclient import TestClient
from app.auth import issue
from app.main import app

client = TestClient(app)
ALICE = {"Authorization": f"Bearer {issue('u-alice', 'customer')}"}
NEW_BATCH = {"releaseAt": "2026-11-13T09:00:00-05:00", "quantity": 5}
HERO_SET = {"lines": [{"itemId": "combo-hero-set", "qty": 1}]}


def assert_error_shape(response, code):
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code


def test_no_token_gives_401():
    response = client.get("/orders")
    assert response.status_code == 401
    assert_error_shape(response, "UNAUTHENTICATED")


def test_garbage_token_gives_401():
    response = client.get("/orders", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401
    assert_error_shape(response, "INVALID_TOKEN")


def test_customer_on_staff_route_gives_403():
    response = client.post("/items/burger-hero/batches", json=NEW_BATCH, headers=ALICE)
    assert response.status_code == 403
    assert_error_shape(response, "FORBIDDEN")


def test_missing_idempotency_key_gives_400():
    response = client.post("/orders", json=HERO_SET, headers=ALICE)
    assert response.status_code == 400
    assert_error_shape(response, "VALIDATION_ERROR")


def test_quantity_zero_gives_400():
    response = client.post("/orders", json={"lines": [{"itemId": "fries", "qty": 0}]},
                           headers={**ALICE, "Idempotency-Key": "k1"})
    assert response.status_code == 400
    assert_error_shape(response, "VALIDATION_ERROR")


def test_control_character_in_an_id_gives_400_not_500():
    # PostgreSQL text cannot hold NUL; the contract's id pattern stops it first.
    response = client.post("/orders", json={"lines": [{"itemId": "fries\x00", "qty": 1}]},
                           headers={**ALICE, "Idempotency-Key": "k1"})
    assert response.status_code == 400
    assert_error_shape(response, "VALIDATION_ERROR")


def test_unknown_url_uses_the_same_error_shape():
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert_error_shape(response, "HTTP_ERROR")


def test_liveness_needs_nothing():
    assert client.get("/healthz").json() == {"status": "alive"}
