"""HTTP middleware.

One access log line per request, carrying the correlation id that every other
log line emitted during that request also carries.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.deps import TENANT_HEADER
from app.core.logging import get_logger, request_id_var, tenant_id_var

logger = get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"

# Health checks and docs would otherwise dominate the log in a demo.
QUIET_PATHS = frozenset({"/api/v1/health", "/favicon.ico"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, log the outcome, and never swallow an error.

    The ``try/finally`` here exists to guarantee the log line and the timing
    are emitted even when the handler raises — not to suppress the exception.
    It is deliberately re-raised: FastAPI's exception handlers are what turn
    it into a response, and catching it here would bypass them.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Honour an upstream id if a proxy or client supplied one, so a trace
        # survives across services; otherwise mint a short one.
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming[:64] if incoming else uuid.uuid4().hex[:12]

        request_token = request_id_var.set(request_id)
        tenant_token = tenant_id_var.set(request.headers.get(TENANT_HEADER, "").strip())

        started = time.perf_counter()
        quiet = request.url.path in QUIET_PATHS
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            # Logged here because this is the only place that still knows the
            # request's timing. Re-raised immediately so the registered
            # exception handlers produce the response.
            logger.exception(
                "%s %s failed with an unhandled exception",
                request.method,
                request.url.path,
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            if not quiet:
                # 5xx is our fault, 4xx is the caller's — different levels so
                # a log filter can separate "broken" from "rejected".
                level = (
                    logger.error
                    if status_code >= 500
                    else logger.warning
                    if status_code >= 400
                    else logger.info
                )
                level(
                    "%s %s -> %s in %.1fms",
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": status_code,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
            request_id_var.reset(request_token)
            tenant_id_var.reset(tenant_token)
