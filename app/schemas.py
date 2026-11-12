# Request and response shapes of the contract. FastAPI turns these
# Pydantic models into the JSON Schemas of openapi.json, and rejects a
# request that does not match them before any of our code runs.
from pydantic import AwareDatetime, BaseModel, Field

# Item ids, order ids and usernames are short slugs. Saying so in the
# contract also rejects control characters such as NUL (which a PostgreSQL
# text value cannot hold) with a 400 before they reach the database.
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


# ---------- errors ----------

class ErrorBody(BaseModel):
    code: str = Field(examples=["SOLD_OUT"])
    message: str
    details: dict


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------- auth ----------

class LoginRequest(BaseModel):
    username: str = Field(pattern=ID_PATTERN, examples=["alice"])
    password: str


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = Field(examples=["Bearer"])
    expiresIn: int = Field(description="Seconds until the token expires.")


# ---------- menu ----------

class ComboComponent(BaseModel):
    itemId: str
    qty: int


class MenuItem(BaseModel):
    id: str
    name: str
    kind: str = Field(description="'single' or 'combo'")
    price: str = Field(examples=["19.00"])
    perOrderLimit: int | None
    available: int | None = Field(description="Units on sale now; null = unlimited.")
    components: list[ComboComponent] | None = None
    bonusRemaining: int | None = None
    bonusAvailable: bool | None = None


class MenuResponse(BaseModel):
    items: list[MenuItem]


# ---------- orders ----------

class OrderLineIn(BaseModel):
    itemId: str = Field(pattern=ID_PATTERN, examples=["combo-hero-set"])
    qty: int = Field(ge=1, le=50)


class PlaceOrderRequest(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1, max_length=20)


class OrderLineOut(BaseModel):
    itemId: str
    qty: int
    unitPrice: str


class ClaimedUnit(BaseModel):
    itemId: str
    batchId: str
    qty: int


class BonusResult(BaseModel):
    comboId: str
    included: bool
    message: str


class OrderResponse(BaseModel):
    orderId: str = Field(examples=["ord_81f2c09a3b7d4e15"])
    status: str = Field(examples=["PENDING_PAYMENT"])
    total: str = Field(examples=["24.50"])
    currency: str = Field(examples=["CAD"])
    paymentDueBy: str
    createdAt: str
    lines: list[OrderLineOut]
    claimedUnits: list[ClaimedUnit]
    bonus: list[BonusResult]


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]


# ---------- staff ----------

class BatchRequest(BaseModel):
    releaseAt: AwareDatetime = Field(description="With a time zone, e.g. 2026-11-13T14:00:00-05:00")
    quantity: int = Field(ge=1, le=1000)


class BatchResponse(BaseModel):
    batchId: str
    itemId: str
    releaseAt: str
    quantity: int
    remaining: int
