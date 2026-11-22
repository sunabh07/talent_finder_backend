"""Candidate business rules."""

from sqlalchemy.orm import Session

from app.core.deps import TenantScope
from app.core.errors import NotFoundError, ValidationError
from app.core.files import ValidatedUpload, validate_cv
from app.core.logging import get_logger
from app.core.pagination import ListQuery
from app.models.candidate import Candidate
from app.repositories.candidate_repository import CandidateRepository
from app.schemas.candidate import CandidateCreate, CandidateUpdate
from app.services.skill_service import SkillService

logger = get_logger(__name__)


class CandidateService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CandidateRepository(session)
        self.skills = SkillService(session)

    # --- Queries -----------------------------------------------------------

    def list_candidates(self, scope: TenantScope, query: ListQuery) -> tuple[list[Candidate], int]:
        return self.repo.list(scope.id, query)

    def get_candidate(self, scope: TenantScope, candidate_id: int) -> Candidate:
        candidate = self.repo.get(scope.id, candidate_id)
        if candidate is None:
            # 404 rather than 403 for a candidate that exists in another
            # tenant: confirming its existence would itself be a leak.
            raise NotFoundError(
                f"Candidate {candidate_id} was not found in tenant '{scope.name}'.",
                {"candidate_id": candidate_id, "tenant_id": scope.id},
            )
        return candidate

    def get_submissions(self, scope: TenantScope, candidate_id: int) -> list[tuple]:
        return self.repo.submissions_for(scope.id, candidate_id)

    def get_stats(self, scope: TenantScope) -> tuple[int, int, int]:
        return self.repo.stats(scope.id)

    # --- Commands ----------------------------------------------------------

    def create_candidate(self, scope: TenantScope, payload: CandidateCreate) -> Candidate:
        skills = self.skills.resolve(payload.skills)
        candidate = Candidate(
            tenant_id=scope.id,
            full_name=payload.full_name,
            location=payload.location,
            total_experience_years=payload.total_experience_years,
            email=payload.email,
            phone=payload.phone,
            current_role=payload.current_role,
            professional_summary=payload.professional_summary,
        )
        candidate.skills = skills
        self.repo.add(candidate)
        self.session.commit()
        self.session.refresh(candidate)
        logger.info(
            "Candidate created: id=%s with %d skill(s)",
            candidate.id,
            len(skills),
            extra={"candidate_id": candidate.id, "skill_count": len(skills)},
        )
        return candidate

    def update_candidate(
        self, scope: TenantScope, candidate_id: int, payload: CandidateUpdate
    ) -> Candidate:
        candidate = self.get_candidate(scope, candidate_id)

        # exclude_unset distinguishes "field omitted" from "field set to null",
        # which is what makes this a true partial update.
        changes = payload.model_dump(exclude_unset=True)
        raw_skills = changes.pop("skills", None)

        for field, value in changes.items():
            setattr(candidate, field, value)

        if raw_skills is not None:
            # Replace rather than append; otherwise a skill could never be
            # removed through this endpoint.
            candidate.skills = self.skills.resolve(raw_skills)

        self.session.flush()
        self.session.commit()
        self.session.refresh(candidate)
        logger.info(
            "Candidate updated: id=%s fields=%s",
            candidate.id,
            sorted(changes) + (["skills"] if raw_skills is not None else []),
            extra={"candidate_id": candidate.id},
        )
        return candidate

    def delete_candidate(self, scope: TenantScope, candidate_id: int) -> None:
        candidate = self.get_candidate(scope, candidate_id)
        # Skill links and submissions fall away via ON DELETE CASCADE; the
        # shared skill rows themselves are protected by RESTRICT.
        self.repo.delete(candidate)
        self.session.commit()
        # Worth a log line: this cascades to skill links and submissions.
        logger.info(
            "Candidate deleted: id=%s (submissions cascaded)",
            candidate_id,
            extra={"candidate_id": candidate_id},
        )

    # --- CV --------------------------------------------------------------

    def attach_cv(
        self,
        scope: TenantScope,
        candidate_id: int,
        filename: str | None,
        content: bytes,
        evidence: list[str] | None = None,
    ) -> Candidate:
        candidate = self.get_candidate(scope, candidate_id)
        upload: ValidatedUpload = validate_cv(filename, content)

        # All four CV columns are written together, which keeps `has_cv`
        # truthful and satisfies ck_candidates_cv_metadata_complete.
        candidate.cv_filename = upload.filename
        candidate.cv_mime_type = upload.mime_type
        candidate.cv_size_bytes = upload.size_bytes
        candidate.cv_data = upload.content
        candidate.cv_evidence = evidence or None

        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def get_cv(self, scope: TenantScope, candidate_id: int) -> tuple[str, str, bytes]:
        candidate = self.repo.load_with_cv(scope.id, candidate_id)
        if candidate is None:
            raise NotFoundError(
                f"Candidate {candidate_id} was not found in tenant '{scope.name}'.",
                {"candidate_id": candidate_id, "tenant_id": scope.id},
            )
        if candidate.cv_data is None:
            raise NotFoundError(
                f"Candidate {candidate_id} has no CV on file.",
                {"candidate_id": candidate_id},
            )
        return (
            candidate.cv_filename or f"candidate-{candidate_id}",
            candidate.cv_mime_type or "application/octet-stream",
            candidate.cv_data,
        )

    def delete_cv(self, scope: TenantScope, candidate_id: int) -> None:
        candidate = self.get_candidate(scope, candidate_id)
        if candidate.cv_filename is None:
            raise ValidationError(
                f"Candidate {candidate_id} has no CV to remove.",
                {"candidate_id": candidate_id},
            )
        candidate.cv_filename = None
        candidate.cv_mime_type = None
        candidate.cv_size_bytes = None
        candidate.cv_data = None
        candidate.cv_evidence = None
        self.session.commit()
