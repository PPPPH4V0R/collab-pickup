# Wiring: build the layers, create the FastAPI app, turn every error into
# the one error shape of the contract, add the health checks and serve
# the three test pages.
# Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
from pathlib import Path
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from app import api
from app.auth import AuthError
from app.config import settings
from app.domain import DomainError
from app.postgres_repository import PostgresRepository, make_engine
from app.service import OrderService, error_body

repo = PostgresRepository(make_engine(settings.database_url))   # the one place that picks the storage
api.service = OrderService(repo)

# The error catalog is part of the contract: each code, its status, and
# whether the same request may be retried.
DESCRIPTION = """
Pickup ordering for limited collab items, combos and bonus gifts.

Every error has the shape `{"error": {"code", "message", "details"}}`.

| Code | Status | Meaning | Retry? | What the client should do |
|---|---|---|---|---|
| `VALIDATION_ERROR` | 400 | The request does not match the schema (bad JSON, missing field or header, qty out of range) | No | Fix the request |
| `UNAUTHENTICATED` | 401 | No bearer token | After login | Log in, then send it with the token |
| `INVALID_TOKEN` | 401 | Token forged, tampered, expired, or for another audience | After login | Log in again for a new token |
| `INVALID_CREDENTIALS` | 401 | Wrong username or password | No | Ask the user again |
| `FORBIDDEN` | 403 | Your role may not do this | No | Use an account with the right role |
| `ORDER_NOT_FOUND` | 404 | No such order among yours | No | Check the order id |
| `ITEM_NOT_FOUND` | 404 | No such item | No | Check the item id |
| `HTTP_ERROR` | 404/405 | Unknown URL or wrong method | No | Check the URL and method |
| `SOLD_OUT` | 409 | Not enough units on sale now | No, not with the same key (it replays SOLD_OUT) | Order later with a NEW Idempotency-Key, e.g. when a batch opens |
| `ORDER_NOT_CANCELLABLE` | 409 | The order is past the point where it can be cancelled | No | Nothing to do |
| `USERNAME_TAKEN` | 409 | Someone already registered this username | No | Register with another username |
| `ITEM_ID_TAKEN` | 409 | A menu item with this id already exists | No | Choose another id |
| `PER_ORDER_LIMIT` | 422 | More units of an item than one order may take | No | Lower the quantity and use a NEW key |
| `UNKNOWN_ITEM` | 422 | An order line names an item not on the menu | No | Fix the line and use a NEW key |
| `IDEMPOTENCY_KEY_REUSED` | 422 | This key was already used with a different request | No | Use a NEW key for a new request |
| `BATCH_NOT_ALLOWED` | 422 | Batches only exist for limited single items | No | Pick a limited single item |
| `INVALID_ITEM` | 422 | The new item breaks a menu rule; `details.reason` says which | No | Fix the item as the reason says |
| `NOT_A_COMBO` | 422 | Bonus gifts can only be added to a combo | No | Pick a combo |
| `INTERNAL_ERROR` | 500 | Unexpected failure on our side | Yes, with the SAME Idempotency-Key | Retry later: an order is saved together with its key, so the retry either replays it or places it once |

`POST /orders` needs an `Idempotency-Key`. Resending the same key with the same body
returns the original answer with the header `Idempotency-Replayed: true`.
GET requests and `POST /orders/{id}/cancel` can always be retried safely.
"""

app = FastAPI(title="Collab Pickup API", version="0.1.0", description=DESCRIPTION)
app.include_router(api.router)


# ---------- one error shape for every failure ----------

@app.exception_handler(DomainError)
@app.exception_handler(AuthError)
def rule_error(request, exc):
    return api.error_response(exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
def invalid_input(request, exc):
    fields = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
              for e in exc.errors()]
    return api.error_response("VALIDATION_ERROR", "The request is not valid.", {"errors": fields})


@app.exception_handler(HTTPException)
def http_error(request, exc):
    # e.g. an unknown URL (404) or a wrong method (405)
    return JSONResponse({"error": error_body("HTTP_ERROR", str(exc.detail))},
                        status_code=exc.status_code)


@app.exception_handler(Exception)
def unexpected_error(request, exc):
    # Never send a stack trace to the caller.
    return JSONResponse({"error": error_body("INTERNAL_ERROR", "Something went wrong.")},
                        status_code=500)


# ---------- health checks ----------

@app.get("/healthz", tags=["health"])
def liveness():
    """Is the process alive? Checks nothing external on purpose."""
    return {"status": "alive"}


@app.get("/readyz", tags=["health"], responses={503: {"description": "Database unreachable"}})
def readiness():
    """Can we serve requests right now? Needs the database."""
    try:
        with repo.unit_of_work() as uow:
            uow.ping()
    except Exception:
        return JSONResponse({"status": "db_unreachable"}, status_code=503)
    return {"status": "ready"}


# ---------- test pages: login/register, customer, staff ----------
# Plain HTML clients of the API; not part of the contract.

STATIC = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")   # style.css and the pages' JS


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(STATIC / "login.html")


@app.get("/customer", include_in_schema=False)
def customer_page():
    return FileResponse(STATIC / "customer.html")


@app.get("/staff", include_in_schema=False)
def staff_page():
    return FileResponse(STATIC / "staff.html")
