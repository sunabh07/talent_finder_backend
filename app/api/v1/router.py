"""Aggregates every v1 route module into a single router."""

from fastapi import APIRouter

from app.api.v1.routes import candidates, health, job_orders, skills, submissions, tenants

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tenants.router)
api_router.include_router(skills.router)
api_router.include_router(candidates.router)
api_router.include_router(job_orders.router)
api_router.include_router(submissions.router)
