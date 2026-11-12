# Tests for the HTTP layer with FastAPI's TestClient (no server needed).
# Tokens are made with auth.issue(), so no password is needed; these
# requests are all refused at the door before they reach the database.
# Run from the project root: python -m pytest -q tests/test_api.py
import secrets
from fastapi.testclient import TestClient
from app.auth import issue, verify
from app.main import app

client = TestClient(app)
ALICE = {"Authorization": f"Bearer {issue('u-alice', 'customer')}"}
STAFF = {"Authorization": f"Bearer {issue('u-staff', 'staff')}"}
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


# ---------- registration (these four reach the database) ----------

def new_username():
    return f"carol_{secrets.token_hex(4)}"     # unique on every run


def test_register_gives_201_and_a_token_that_can_order():
    response = client.post("/auth/register",
                           json={"username": new_username(), "password": "long-enough"})
    assert response.status_code == 201
    carol = {"Authorization": f"Bearer {response.json()['accessToken']}"}
    order = client.post("/orders", json={"lines": [{"itemId": "fries", "qty": 1}]},
                        headers={**carol, "Idempotency-Key": secrets.token_hex(8)})
    assert order.status_code == 201


def test_register_taken_username_gives_409():
    body = {"username": new_username(), "password": "long-enough"}
    client.post("/auth/register", json=body)
    response = client.post("/auth/register", json=body)
    assert response.status_code == 409
    assert_error_shape(response, "USERNAME_TAKEN")


def test_register_short_password_gives_400():
    response = client.post("/auth/register", json={"username": new_username(), "password": "short"})
    assert response.status_code == 400
    assert_error_shape(response, "VALIDATION_ERROR")


def test_register_cannot_ask_for_the_staff_role():
    response = client.post("/auth/register", json={
        "username": new_username(), "password": "long-enough", "role": "staff"})
    assert response.status_code == 201
    assert verify(response.json()["accessToken"])["role"] == "customer"


# ---------- staff: new menu items (the 201 / 409 / 422 ones reach the database) ----------

def new_combo_body():
    return {"id": f"duo_{secrets.token_hex(4)}", "name": "Blue Duo", "kind": "combo",
            "price": "9.50", "components": [{"itemId": "drink-blue-soda", "qty": 2}],
            "bonusGifts": 2}


def test_customer_cannot_add_menu_items():
    response = client.post("/items", json=new_combo_body(), headers=ALICE)
    assert response.status_code == 403
    assert_error_shape(response, "FORBIDDEN")


def test_staff_add_a_combo_gives_201_and_a_menu_entry():
    body = new_combo_body()
    response = client.post("/items", json=body, headers=STAFF)
    assert response.status_code == 201
    entry = response.json()
    assert (entry["id"], entry["kind"], entry["bonusRemaining"]) == (body["id"], "combo", 2)


def test_staff_add_an_existing_id_gives_409():
    body = new_combo_body()
    client.post("/items", json=body, headers=STAFF)
    response = client.post("/items", json=body, headers=STAFF)
    assert response.status_code == 409
    assert_error_shape(response, "ITEM_ID_TAKEN")


def test_combo_inside_a_combo_gives_422():
    body = {**new_combo_body(), "components": [{"itemId": "combo-hero-set", "qty": 1}]}
    response = client.post("/items", json=body, headers=STAFF)
    assert response.status_code == 422
    assert_error_shape(response, "INVALID_ITEM")


def test_price_must_be_a_money_string():
    response = client.post("/items", json={**new_combo_body(), "price": "9.999"}, headers=STAFF)
    assert response.status_code == 400
    assert_error_shape(response, "VALIDATION_ERROR")


def test_liveness_needs_nothing():
    assert client.get("/healthz").json() == {"status": "alive"}
