"""Model package.

Importing every model here guarantees that ``Base.metadata`` is fully populated
before Alembic autogenerates a migration or the test suite creates tables.
"""

from app.models.base import Base, TimestampMixin
from app.models.candidate import Candidate, candidate_skills
from app.models.enums import JobOrderStatus, SubmissionStatus, TenantStatus
from app.models.job_order import JobOrder, job_order_skills
from app.models.skill import Skill, SkillAlias
from app.models.submission import Submission
from app.models.tenant import Tenant

__all__ = [
    "Base",
    "Candidate",
    "JobOrder",
    "JobOrderStatus",
    "Skill",
    "SkillAlias",
    "Submission",
    "SubmissionStatus",
    "Tenant",
    "TenantStatus",
    "TimestampMixin",
    "candidate_skills",
    "job_order_skills",
]
