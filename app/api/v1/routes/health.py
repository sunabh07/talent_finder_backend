"""Liveness and readiness endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import DbSession

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service and database health")
def health(db: DbSession) -> dict[str, object]:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "database": "connected",
        "ai_enabled": settings.ai_enabled,
    }
