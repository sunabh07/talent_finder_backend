"""Data access for the shared skill vocabulary and its aliases."""

# Repository classes define a ``list`` method, which shadows the builtin inside
# the class body. Deferring annotation evaluation keeps ``list[...]`` hints working.
from __future__ import annotations

from sqlalchemy import or_, select

from app.core.pagination import ListQuery
from app.models.skill import Skill, SkillAlias
from app.repositories.base import BaseRepository, apply_window, count_rows

SORTABLE: dict[str, object] = {"name": Skill.name, "id": Skill.id}
DEFAULT_SORT = "name"


class SkillRepository(BaseRepository):
    def find_by_normalized(self, normalized: list[str]) -> dict[str, Skill]:
        """Bulk lookup keyed by canonical name.

        One query for the whole batch rather than one per skill: a candidate
        with ten skills would otherwise cost ten round trips on every save.
        """
        if not normalized:
            return {}
        stmt = select(Skill).where(Skill.normalized_name.in_(normalized))
        return {skill.normalized_name: skill for skill in self.session.scalars(stmt)}

    def find_by_alias(self, normalized: list[str]) -> dict[str, Skill]:
        """Bulk alias resolution, keyed by the alias that matched."""
        if not normalized:
            return {}
        stmt = (
            select(SkillAlias.alias_normalized, Skill)
            .join(Skill, Skill.id == SkillAlias.skill_id)
            .where(SkillAlias.alias_normalized.in_(normalized))
        )
        return {alias: skill for alias, skill in self.session.execute(stmt)}

    def add(self, skill: Skill) -> Skill:
        self.session.add(skill)
        self.session.flush()
        return skill

    def list(self, query: ListQuery) -> tuple[list[Skill], int]:
        """Backs the skill picker in the candidate and job-order forms."""
        stmt = select(Skill)
        if query.q:
            term = f"%{query.q}%"
            stmt = stmt.where(or_(Skill.name.ilike(term), Skill.normalized_name.ilike(term)))
        column, descending = query.validated_sort(SORTABLE, DEFAULT_SORT)
        order = column.desc() if descending else column.asc()  # type: ignore[union-attr]
        stmt = stmt.order_by(order, Skill.id.asc())

        total = count_rows(self.session, stmt)
        return list(self.session.scalars(apply_window(stmt, query)).all()), total
