"""Job order, matching and submission schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.normalization import normalize_display_name
from app.models.enums import JobOrderStatus
from app.schemas.candidate import SkillRead

MAX_EXPERIENCE_YEARS = Decimal("60")


class JobOrderBase(BaseModel):
    """Required set follows the assignment's Create Job Order form."""

    job_title: str = Field(min_length=1, max_length=150, examples=["Senior Backend Engineer"])
    location: str = Field(min_length=1, max_length=150, examples=["Bengaluru"])
    min_experience_years: Decimal = Field(ge=0, le=MAX_EXPERIENCE_YEARS, examples=["4"])
    number_of_openings: int = Field(ge=1, le=9999, examples=[3])
    required_skills: list[str] = Field(
        min_length=1, examples=[["Python", "FastAPI", "PostgreSQL", "Docker"]]
    )

    client_name: str | None = Field(default=None, max_length=150)
    job_description: str | None = None

    @field_validator("job_title", "location")
    @classmethod
    def _require_text(cls, value: str) -> str:
        cleaned = normalize_display_name(value)
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("client_name", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("min_experience_years")
    @classmethod
    def _quantize(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.1"))


class JobOrderCreate(JobOrderBase):
    pass


class JobOrderUpdate(BaseModel):
    """Partial update. ``required_skills``, when given, replaces the whole set."""

    job_title: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, min_length=1, max_length=150)
    min_experience_years: Decimal | None = Field(default=None, ge=0, le=MAX_EXPERIENCE_YEARS)
    number_of_openings: int | None = Field(default=None, ge=1, le=9999)
    required_skills: list[str] | None = Field(default=None, min_length=1)
    client_name: str | None = Field(default=None, max_length=150)
    job_description: str | None = None
    status: JobOrderStatus | None = None

    @field_validator("job_title", "location")
    @classmethod
    def _require_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_display_name(value)
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("client_name", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class JobOrderListItem(BaseModel):
    """Row shape for the Job Order List table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_title: str
    client_name: str | None
    location: str
    min_experience_years: Decimal
    number_of_openings: int
    required_skills: list[SkillRead]
    status: JobOrderStatus
    created_at: datetime


class ShortlistedCandidate(BaseModel):
    """A candidate already submitted against this job order."""

    submission_id: int
    candidate_id: int
    full_name: str
    current_role: str | None
    location: str
    total_experience_years: Decimal
    status: str
    created_at: datetime


class JobOrderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_title: str
    client_name: str | None
    location: str
    min_experience_years: Decimal
    number_of_openings: int
    required_skills: list[SkillRead]
    status: JobOrderStatus
    job_description: str | None

    shortlisted: list[ShortlistedCandidate] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime


class JobOrderStats(BaseModel):
    total: int
    open: int
    total_openings: int


class MatchedCandidate(BaseModel):
    """One row of the ranked Matching Candidates list.

    ``match_count`` is the sole ranking key. ``meets_min_experience`` is shown
    beside it as a factual indicator and never filters or reorders anything -
    the assignment ranks on matched skill count, full stop.
    """

    candidate_id: int
    full_name: str
    current_role: str | None
    location: str
    total_experience_years: Decimal
    matched_skills: list[str]
    match_count: int
    meets_min_experience: bool
    is_shortlisted: bool


class MatchSummary(BaseModel):
    """Context the Matching Candidates panel shows above the list."""

    job_order_id: int
    required_skill_count: int
    required_skills: list[SkillRead]


class MatchPage(BaseModel):
    """Paginated matches plus the job's required-skill context.

    Shaped like the standard `Page` envelope with one extra field, so the
    frontend's pagination component works unchanged. Note there is no
    `sort_by`: the ranking is mandated by the assignment and is not a client
    choice.
    """

    items: list[MatchedCandidate]
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: MatchSummary


class SubmissionListItem(BaseModel):
    """Row shape for the Submission List: Job Order, Candidate, Status."""

    id: int
    job_order_id: int
    job_title: str
    client_name: str | None
    candidate_id: int
    candidate_name: str
    status: str
    created_at: datetime


class SubmissionStats(BaseModel):
    total: int
    added_this_week: int
    job_orders_with_submissions: int


class ShortlistRequest(BaseModel):
    candidate_id: int = Field(ge=1)


class ShortlistResult(BaseModel):
    submission_id: int
    job_order_id: int
    candidate_id: int
    status: str
    created_at: datetime
    already_shortlisted: bool = Field(
        description="True when this candidate was already on the shortlist; "
        "the request is idempotent and created nothing new.",
    )
