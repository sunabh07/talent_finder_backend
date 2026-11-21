"""Skill controller - backs the skill picker in candidate and job-order forms."""

from sqlalchemy.orm import Session

from app.core.pagination import ListQuery
from app.repositories.skill_repository import SkillRepository
from app.schemas.candidate import SkillRead
from app.schemas.common import Page


class SkillController:
    def __init__(self, session: Session) -> None:
        self.repo = SkillRepository(session)

    def list_skills(self, query: ListQuery) -> Page[SkillRead]:
        skills, total = self.repo.list(query)
        return Page.build(
            items=[SkillRead.model_validate(skill) for skill in skills],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
