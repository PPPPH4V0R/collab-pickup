# Wiring: build the layers, create the FastAPI app, turn every error into
# the one error shape of the contract, and add the health checks.
# Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app import api
from app.auth import AuthError
from app.config import settings
from app.domain import DomainError
from app.repository import Repository, make_engine
from app.service import OrderService, error_body

repo = Repository(make_engine(settings.database_url))
api.service = OrderService(repo)

app = FastAPI(
    title="Collab Pickup API",
    version="0.1.0",
    description="Pickup ordering for limited collab items, combos and bonus gifts. "
                "Every error has the shape {\"error\": {\"code\", \"message\", \"details\"}}.")
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


@app.get("/readyz", tags=["health"])
def readiness():
    """Can we serve requests right now? Needs the database."""
    try:
        with repo.unit_of_work() as uow:
            uow.ping()
    except Exception:
        return JSONResponse({"status": "db_unreachable"}, status_code=503)
    return {"status": "ready"}
