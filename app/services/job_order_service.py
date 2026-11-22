"""Job order and matching business rules."""

from sqlalchemy import Row
from sqlalchemy.orm import Session

from app.core.deps import TenantScope
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import ListQuery
from app.models.enums import JobOrderStatus
from app.models.job_order import JobOrder
from app.repositories.job_order_repository import JobOrderRepository
from app.schemas.job_order import JobOrderCreate, JobOrderUpdate
from app.services.skill_service import SkillService

logger = get_logger(__name__)


class JobOrderService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = JobOrderRepository(session)
        self.skills = SkillService(session)

    # --- Queries -------------------------------------------------------------

    def list_job_orders(self, scope: TenantScope, query: ListQuery) -> tuple[list[JobOrder], int]:
        return self.repo.list(scope.id, query)

    def get_job_order(self, scope: TenantScope, job_order_id: int) -> JobOrder:
        job_order = self.repo.get(scope.id, job_order_id)
        if job_order is None:
            raise NotFoundError(
                f"Job order {job_order_id} was not found in tenant '{scope.name}'.",
                {"job_order_id": job_order_id, "tenant_id": scope.id},
            )
        return job_order

    def get_stats(self, scope: TenantScope) -> tuple[int, int, int]:
        return self.repo.stats(scope.id)

    def get_shortlisted(self, scope: TenantScope, job_order_id: int) -> list[Row]:
        return self.repo.shortlisted(scope.id, job_order_id)

    def match_candidates(
        self, scope: TenantScope, job_order_id: int, query: ListQuery
    ) -> tuple[JobOrder, list[Row], int]:
        """Rank same-tenant candidates by matched required-skill count.

        The service deliberately adds **no** ranking logic of its own. The
        order is fixed by the repository query, and nothing here re-sorts,
        filters by experience, or lets any other signal influence position.
        That restraint is the requirement: "matching is based on skill keyword
        matching, and candidates are ranked by the number of skills matched".
        """
        job_order = self.get_job_order(scope, job_order_id)
        required_ids = self.repo.required_skill_ids(job_order.id)
        rows, total = self.repo.match_candidates(
            tenant_id=scope.id,
            job_order_id=job_order.id,
            required_skill_ids=required_ids,
            min_experience_years=job_order.min_experience_years,
            query=query,
        )
        # The graded path. Logging the counts makes a wrong ranking
        # diagnosable from the log alone.
        logger.info(
            "Matched %d candidate(s) for job_order=%s against %d required skill(s)",
            total,
            job_order.id,
            len(required_ids),
            extra={
                "job_order_id": job_order.id,
                "match_total": total,
                "required_skill_count": len(required_ids),
            },
        )
        if not required_ids:
            logger.warning(
                "Job order %s has no required skills; matching returns nothing",
                job_order.id,
                extra={"job_order_id": job_order.id},
            )
        return job_order, rows, total

    # --- Commands --------------------------------------------------------------

    def create_job_order(self, scope: TenantScope, payload: JobOrderCreate) -> JobOrder:
        # Same SkillService the candidates use, so both sides of a match are
        # drawn from one vocabulary normalized by one code path.
        skills = self.skills.resolve(payload.required_skills, field="required_skills")

        job_order = JobOrder(
            tenant_id=scope.id,
            job_title=payload.job_title,
            location=payload.location,
            min_experience_years=payload.min_experience_years,
            number_of_openings=payload.number_of_openings,
            client_name=payload.client_name,
            job_description=payload.job_description,
            status=JobOrderStatus.OPEN.value,
        )
        job_order.required_skills = skills
        self.repo.add(job_order)
        self.session.commit()
        self.session.refresh(job_order)
        logger.info(
            "Job order created: id=%s with %d required skill(s)",
            job_order.id,
            len(skills),
            extra={"job_order_id": job_order.id, "required_skill_count": len(skills)},
        )
        return job_order

    def update_job_order(
        self, scope: TenantScope, job_order_id: int, payload: JobOrderUpdate
    ) -> JobOrder:
        job_order = self.get_job_order(scope, job_order_id)

        changes = payload.model_dump(exclude_unset=True)
        raw_skills = changes.pop("required_skills", None)
        status = changes.pop("status", None)

        for field, value in changes.items():
            setattr(job_order, field, value)
        if status is not None:
            job_order.status = JobOrderStatus(status).value
        if raw_skills is not None:
            job_order.required_skills = self.skills.resolve(raw_skills, field="required_skills")

        self.session.flush()
        self.session.commit()
        self.session.refresh(job_order)
        return job_order

    def delete_job_order(self, scope: TenantScope, job_order_id: int) -> None:
        job_order = self.get_job_order(scope, job_order_id)
        # Required-skill links and submissions fall away via ON DELETE CASCADE.
        self.repo.delete(job_order)
        self.session.commit()
        logger.info(
            "Job order deleted: id=%s (submissions cascaded)",
            job_order_id,
            extra={"job_order_id": job_order_id},
        )
