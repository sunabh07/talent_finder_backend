"""Candidate request and response schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.normalization import normalize_display_name

MAX_EXPERIENCE_YEARS = Decimal("60")


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CandidateBase(BaseModel):
    """Fields shared by create and update.

    Required set follows the assignment's Add Candidate form: Full Name,
    Location, Total Experience and at least one Skill. Email and phone are
    optional - the brief lists them among the fields a parsed CV auto-fills,
    so they need somewhere to live and be edited.
    """

    full_name: str = Field(min_length=1, max_length=150, examples=["Asha Rao"])
    location: str = Field(min_length=1, max_length=150, examples=["Bengaluru"])
    total_experience_years: Decimal = Field(ge=0, le=MAX_EXPERIENCE_YEARS, examples=["6.5"])
    skills: list[str] = Field(min_length=1, examples=[["Python", "FastAPI", "PostgreSQL"]])

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    current_role: str | None = Field(default=None, max_length=150)
    professional_summary: str | None = None

    @field_validator("full_name", "location")
    @classmethod
    def _require_text(cls, value: str) -> str:
        cleaned = normalize_display_name(value)
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("email", "phone", "current_role", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """An empty form input means "not provided", not an empty string."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("total_experience_years")
    @classmethod
    def _quantize(cls, value: Decimal) -> Decimal:
        # The column is NUMERIC(4,1); round here so that 6.55 is rejected
        # consistently rather than silently truncated by the database.
        return value.quantize(Decimal("0.1"))


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    """Partial update. Only the fields present in the body are changed.

    ``skills``, when supplied, replaces the whole set rather than appending -
    anything else would make removing a skill impossible through this endpoint.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, min_length=1, max_length=150)
    total_experience_years: Decimal | None = Field(default=None, ge=0, le=MAX_EXPERIENCE_YEARS)
    skills: list[str] | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    current_role: str | None = Field(default=None, max_length=150)
    professional_summary: str | None = None

    @field_validator("full_name", "location")
    @classmethod
    def _require_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_display_name(value)
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("email", "phone", "current_role", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CandidateListItem(BaseModel):
    """Row shape for the Candidate List table.

    Carries no CV bytes - only whether a CV exists. The column itself is
    mapped ``deferred``, so the bytes are never even fetched for this query.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    location: str
    total_experience_years: Decimal
    current_role: str | None
    skills: list[SkillRead]
    has_cv: bool
    created_at: datetime


class CandidateSubmissionLink(BaseModel):
    """A job order this candidate has been shortlisted for (Story 4)."""

    submission_id: int
    job_order_id: int
    job_title: str
    client_name: str | None
    status: str
    created_at: datetime


class CandidateDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    location: str
    total_experience_years: Decimal
    email: str | None
    phone: str | None
    current_role: str | None
    professional_summary: str | None
    skills: list[SkillRead]

    has_cv: bool
    cv_filename: str | None
    cv_mime_type: str | None
    cv_size_bytes: int | None

    submissions: list[CandidateSubmissionLink] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime


class CandidateStats(BaseModel):
    """Summary cards above the Candidate List table."""

    total: int
    added_this_week: int
    with_cv: int


class CvUploadResult(BaseModel):
    candidate_id: int
    cv_filename: str
    cv_mime_type: str
    cv_size_bytes: int
