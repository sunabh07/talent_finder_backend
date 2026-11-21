"""Database-level integrity tests.

These assert that the *schema itself* refuses invalid data, with no application
code in the path. That distinction matters: a rule enforced only in a service
survives exactly as long as nobody deletes the service.
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Candidate, JobOrder, Skill, Submission, Tenant
from app.models.enums import SubmissionStatus


def _tenant(session: Session, name: str) -> Tenant:
    tenant = Tenant(name=name)
    session.add(tenant)
    session.flush()
    return tenant


def _candidate(session: Session, tenant: Tenant, name: str) -> Candidate:
    candidate = Candidate(
        tenant_id=tenant.id,
        full_name=name,
        location="Bengaluru",
        total_experience_years=Decimal("5.0"),
    )
    session.add(candidate)
    session.flush()
    return candidate


def _job(session: Session, tenant: Tenant, title: str) -> JobOrder:
    job = JobOrder(
        tenant_id=tenant.id,
        job_title=title,
        location="Bengaluru",
        min_experience_years=Decimal("3.0"),
        number_of_openings=2,
    )
    session.add(job)
    session.flush()
    return job


# --- The headline guarantee ------------------------------------------------


def test_cross_tenant_submission_is_rejected_by_the_database(db_session: Session) -> None:
    """A candidate from tenant A may not be submitted to tenant B's job order.

    No service code runs here. The composite foreign keys
    ``(tenant_id, candidate_id)`` and ``(tenant_id, job_order_id)`` share one
    ``tenant_id`` column, so this row cannot satisfy both.
    """
    tenant_a = _tenant(db_session, "Tenant A")
    tenant_b = _tenant(db_session, "Tenant B")
    candidate_a = _candidate(db_session, tenant_a, "Asha Rao")
    job_b = _job(db_session, tenant_b, "Backend Engineer")

    db_session.add(
        Submission(
            tenant_id=tenant_b.id,
            candidate_id=candidate_a.id,  # belongs to tenant A
            job_order_id=job_b.id,
            status=SubmissionStatus.SHORTLISTED.value,
        )
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "fk_submissions_tenant_candidate" in str(exc.value)


def test_same_tenant_submission_is_accepted(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    candidate = _candidate(db_session, tenant, "Asha Rao")
    job = _job(db_session, tenant, "Backend Engineer")

    db_session.add(Submission(tenant_id=tenant.id, candidate_id=candidate.id, job_order_id=job.id))
    db_session.flush()
    assert db_session.query(Submission).count() == 1


def test_duplicate_submission_is_rejected(db_session: Session) -> None:
    """Backs idempotent shortlisting in Story 4."""
    tenant = _tenant(db_session, "Tenant A")
    candidate = _candidate(db_session, tenant, "Asha Rao")
    job = _job(db_session, tenant, "Backend Engineer")

    for _ in range(2):
        db_session.add(
            Submission(tenant_id=tenant.id, candidate_id=candidate.id, job_order_id=job.id)
        )
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "uq_submissions_candidate_job" in str(exc.value)


def test_submission_defaults_to_shortlisted(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    candidate = _candidate(db_session, tenant, "Asha Rao")
    job = _job(db_session, tenant, "Backend Engineer")

    submission = Submission(tenant_id=tenant.id, candidate_id=candidate.id, job_order_id=job.id)
    db_session.add(submission)
    db_session.flush()
    db_session.refresh(submission)
    assert submission.status == SubmissionStatus.SHORTLISTED.value


# --- Field-level constraints ----------------------------------------------


def test_tenant_name_is_unique_case_insensitively(db_session: Session) -> None:
    _tenant(db_session, "LinkedIn")
    db_session.add(Tenant(name="linkedin"))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "uq_tenants_name_lower" in str(exc.value)


def test_blank_tenant_name_is_rejected(db_session: Session) -> None:
    db_session.add(Tenant(name="   "))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "name_not_blank" in str(exc.value)


def test_negative_experience_is_rejected(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    db_session.add(
        Candidate(
            tenant_id=tenant.id,
            full_name="Asha Rao",
            location="Pune",
            total_experience_years=Decimal("-1.0"),
        )
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "experience_in_range" in str(exc.value)


def test_zero_openings_is_rejected(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    db_session.add(
        JobOrder(
            tenant_id=tenant.id,
            job_title="Backend Engineer",
            location="Pune",
            min_experience_years=Decimal("2.0"),
            number_of_openings=0,
        )
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "openings_at_least_one" in str(exc.value)


def test_job_order_defaults_to_open(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    job = _job(db_session, tenant, "Backend Engineer")
    db_session.refresh(job)
    assert job.status == "Open"


def test_cv_bytes_require_filename_and_mime_type(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    db_session.add(
        Candidate(
            tenant_id=tenant.id,
            full_name="Asha Rao",
            location="Pune",
            total_experience_years=Decimal("4.0"),
            cv_data=b"%PDF-1.4 fake",
        )
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "cv_metadata_complete" in str(exc.value)


def test_skill_normalized_name_is_unique(db_session: Session) -> None:
    db_session.add(Skill(name="Python", normalized_name="python"))
    db_session.flush()
    db_session.add(Skill(name="python", normalized_name="python"))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert "uq_skills_normalized_name" in str(exc.value)


def test_deleting_a_candidate_cascades_to_submissions(db_session: Session) -> None:
    tenant = _tenant(db_session, "Tenant A")
    candidate = _candidate(db_session, tenant, "Asha Rao")
    job = _job(db_session, tenant, "Backend Engineer")
    db_session.add(Submission(tenant_id=tenant.id, candidate_id=candidate.id, job_order_id=job.id))
    db_session.flush()

    db_session.delete(candidate)
    db_session.flush()
    assert db_session.query(Submission).count() == 0


def test_tenant_with_candidates_cannot_be_deleted(db_session: Session) -> None:
    """RESTRICT on tenant foreign keys prevents orphaning a tenant's data."""
    tenant = _tenant(db_session, "Tenant A")
    _candidate(db_session, tenant, "Asha Rao")

    db_session.delete(tenant)
    with pytest.raises(IntegrityError):
        db_session.flush()
