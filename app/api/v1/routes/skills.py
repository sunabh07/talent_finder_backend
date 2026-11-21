"""Skill vocabulary routes.

Not tenant-scoped: the vocabulary is shared and contains nothing but labels.
Candidate and job-order data - the parts that are actually tenant-owned - are
scoped everywhere they appear.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.controllers.skill_controller import SkillController
from app.core.deps import DbSession
from app.core.pagination import ListQuery, list_query_params
from app.schemas.candidate import SkillRead
from app.schemas.common import Page

router = APIRouter(prefix="/skills", tags=["Skills"])

ListQueryDep = Annotated[ListQuery, Depends(list_query_params)]


@router.get(
    "",
    response_model=Page[SkillRead],
    summary="Search the shared skill vocabulary",
    description="Type-ahead source for skill inputs. Sortable by: name, id.",
)
def list_skills(db: DbSession, query: ListQueryDep) -> Page[SkillRead]:
    return SkillController(db).list_skills(query)
