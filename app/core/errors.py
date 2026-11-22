"""Application error hierarchy and the handlers that render it as JSON.

Every error the API returns has the same envelope::

    {"error": {"code": "NOT_FOUND", "message": "...", "details": {...}}}

Services and repositories raise these domain errors; they never import FastAPI
or raise ``HTTPException``. Translating a domain error into an HTTP status code
happens once, here, which is what keeps the inner layers framework-agnostic.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

# Starlette renamed its 422 constant between versions; pinning the literal
# keeps this stable and the meaning is not in doubt.
HTTP_422 = 422


class AppError(Exception):
    """Base class for every expected, client-visible error."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class AiUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "AI_UNAVAILABLE"


class ValidationError(AppError):
    status_code = HTTP_422
    code = "VALIDATION_ERROR"


class ConflictError(AppError):
    """A uniqueness or state conflict, e.g. duplicate tenant name."""

    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class TenantScopeError(AppError):
    """A record was requested or mutated outside the active tenant scope."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "TENANT_SCOPE_VIOLATION"


class MissingTenantError(AppError):
    """The request did not carry a usable tenant scope."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "MISSING_TENANT"


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=HTTP_422,
            content=_envelope(
                "VALIDATION_ERROR",
                "One or more fields are invalid.",
                {"fields": fields},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        """Database constraints are the last line of defence.

        Reaching this handler means a service-level check was missing or lost a
        race. We still answer with a clean 409 rather than a 500.
        """
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope(
                "CONSTRAINT_VIOLATION",
                "The operation violates a database constraint.",
                {"constraint": constraint} if constraint else {},
            ),
        )
