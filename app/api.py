# Interface layer: each route only translates HTTP <-> service call.
# No business rule lives here. The table below is the one place where
# an error code becomes an HTTP status.
from fastapi import APIRouter, Depends, Header, Path
from fastapi.responses import JSONResponse
from app import schemas
from app.auth import User, current_user, require_role
from app.service import error_body

router = APIRouter()
service = None             # the OrderService; main.py plugs it in at startup

STATUS = {
    "VALIDATION_ERROR": 400,
    "UNAUTHENTICATED": 401,
    "INVALID_TOKEN": 401,
    "INVALID_CREDENTIALS": 401,
    "FORBIDDEN": 403,
    "ORDER_NOT_FOUND": 404,
    "ITEM_NOT_FOUND": 404,
    "SOLD_OUT": 409,
    "ORDER_NOT_CANCELLABLE": 409,
    "PER_ORDER_LIMIT": 422,
    "UNKNOWN_ITEM": 422,
    "IDEMPOTENCY_KEY_REUSED": 422,
    "BATCH_NOT_ALLOWED": 422,
}


def error_response(code, message, details=None):
    return JSONResponse({"error": error_body(code, message, details)}, status_code=STATUS[code])


def errors(*statuses):
    """Document which error statuses a route can return (for openapi.json).
    'default' says any other status has the same error shape. It also keeps
    FastAPI from documenting its own 422 body: invalid input gets our 400."""
    documented = {s: {"model": schemas.ErrorResponse} for s in statuses}
    documented["default"] = {"model": schemas.ErrorResponse, "description": "Error"}
    return documented


# ---------- public ----------

@router.post("/auth/login", response_model=schemas.TokenResponse, responses=errors(400, 401),
             tags=["auth"])
def login(body: schemas.LoginRequest):
    return service.login(body.username, body.password)


@router.get("/menu", response_model=schemas.MenuResponse, tags=["menu"])
def get_menu():
    """Items and combos with live availability and whether each combo
    still comes with its bonus gift."""
    return service.get_menu()


# ---------- customers ----------

@router.post("/orders", status_code=201, response_model=schemas.OrderResponse,
             responses=errors(400, 401, 403, 409, 422), tags=["orders"])
def place_order(body: schemas.PlaceOrderRequest,
                idempotency_key: str = Header(min_length=1, max_length=255),
                user: User = Depends(require_role("customer"))):
    """Place a pickup order. Sending the same Idempotency-Key and body again
    returns the original answer with the header Idempotency-Replayed: true."""
    out = service.place_order(user.id, idempotency_key, [line.model_dump() for line in body.lines])
    if out.ok:
        response = JSONResponse(out.value, status_code=201)
    else:
        response = JSONResponse({"error": out.value}, status_code=STATUS[out.code])
    if out.replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return response


@router.get("/orders", response_model=schemas.OrderListResponse,
            responses=errors(401, 403), tags=["orders"])
def list_orders(user: User = Depends(require_role("customer"))):
    return service.list_orders(user.id)


@router.get("/orders/{order_id}", response_model=schemas.OrderResponse,
            responses=errors(401, 403, 404), tags=["orders"])
def get_order(order_id: str = Path(pattern=schemas.ID_PATTERN),
              user: User = Depends(require_role("customer"))):
    return service.get_order(user.id, order_id)


@router.post("/orders/{order_id}/cancel", response_model=schemas.OrderResponse,
             responses=errors(401, 403, 404, 409), tags=["orders"])
def cancel_order(order_id: str = Path(pattern=schemas.ID_PATTERN),
                 user: User = Depends(require_role("customer"))):
    """Cancel your own order; its units and bonus gifts go back to stock.
    Cancelling an already cancelled order returns it unchanged."""
    return service.cancel_order(user.id, order_id)


# ---------- staff ----------

@router.post("/items/{item_id}/batches", status_code=201, response_model=schemas.BatchResponse,
             responses=errors(400, 401, 403, 404, 422), tags=["staff"])
def add_batch(body: schemas.BatchRequest,
              item_id: str = Path(pattern=schemas.ID_PATTERN),
              user: User = Depends(require_role("staff"))):
    """Schedule a release batch for a limited single item."""
    return service.add_batch(item_id, body.releaseAt, body.quantity)
