"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware

DESCRIPTION = """
Multi-tenant recruiter portal API.

**Tenant scope.** Endpoints that operate on tenant-owned data require an
`X-Tenant-ID` header. It is resolved and validated by a single dependency, and
every repository method takes the resolved tenant as a required argument.

**Layering.** `routes -> controllers -> services -> repositories`. Only
repositories build SQL; only services commit; only controllers map entities to
response schemas.
"""


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown. The modern replacement for @app.on_event."""
    logger.info(
        "%s starting | env=%s | ai=%s | log_level=%s",
        settings.app_name,
        settings.environment,
        "enabled" if settings.ai_enabled else "disabled",
        settings.log_level.upper(),
    )
    yield
    logger.info("%s shutting down", settings.app_name)


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Added last so it runs first: every other layer's log lines then carry
    # the request id this middleware sets.
    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
