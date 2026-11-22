"""Editable suggestions returned by the resume parser."""

from typing import Annotated

from pydantic import BaseModel, Field

CvExcerpt = Annotated[str, Field(min_length=1, max_length=400)]
CvEvidence = Annotated[list[CvExcerpt], Field(max_length=8)]


class CvParseResult(BaseModel):
    full_name: str | None = Field(max_length=150)
    location: str | None = Field(max_length=150)
    total_experience_years: float | None = Field(ge=0, le=60)
    skills: list[str] = Field(max_length=50)
    email: str | None = Field(max_length=255)
    phone: str | None = Field(max_length=40)
    current_role: str | None = Field(max_length=150)
    professional_summary: str | None = Field(max_length=1500)
    evidence: CvEvidence
