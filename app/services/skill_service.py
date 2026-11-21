"""Skill vocabulary rules.

The single place where a free-text skill string becomes a `Skill` row. Both
candidates (Story 2) and job orders (Story 3) go through this, which is what
guarantees that the two sides of a match are drawn from the same vocabulary —
without that, matching would be comparing strings that were normalized by two
different code paths.

Resolution order for each input string:

1. Normalize it (casefold, trim, collapse whitespace, keep ``+`` and ``#``).
2. Does a canonical skill already exist with that normalized name? Use it.
3. Does an alias map it to one? Use the alias target. (``reactjs`` -> React)
4. Otherwise create a new canonical skill.

Steps 2 and 3 are **bulk** queries, so resolving ten skills costs two round
trips rather than twenty.
"""

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.normalization import normalize_display_name, normalize_skill
from app.models.skill import Skill
from app.repositories.skill_repository import SkillRepository

MAX_SKILLS_PER_RECORD = 50


class SkillService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SkillRepository(session)

    def resolve(self, raw_names: list[str], *, field: str = "skills") -> list[Skill]:
        """Turn user-entered skill strings into canonical `Skill` rows.

        Creating unknown skills on demand is deliberate. The alternative - a
        fixed vocabulary that rejects anything unseeded - would mean a recruiter
        could not enter a skill the seed data never anticipated, which is
        unusable in a live demo.
        """
        cleaned: dict[str, str] = {}  # normalized -> display form, deduplicated
        for raw in raw_names:
            display = normalize_display_name(raw)
            normalized = normalize_skill(display)
            if not normalized:
                continue
            cleaned.setdefault(normalized, display)

        if not cleaned:
            raise ValidationError("At least one skill is required.", {"field": field})
        if len(cleaned) > MAX_SKILLS_PER_RECORD:
            raise ValidationError(
                f"A record may not have more than {MAX_SKILLS_PER_RECORD} skills.",
                {"field": field, "received": len(cleaned)},
            )

        keys = list(cleaned)
        existing = self.repo.find_by_normalized(keys)
        aliases = self.repo.find_by_alias([key for key in keys if key not in existing])

        resolved: list[Skill] = []
        seen_ids: set[int] = set()
        for normalized, display in cleaned.items():
            skill = existing.get(normalized) or aliases.get(normalized)
            if skill is None:
                skill = self.repo.add(Skill(name=display, normalized_name=normalized))
            # Two inputs can resolve to one skill ("React" and "reactjs"), so
            # deduplicate again after resolution or the link insert will fail.
            if skill.id not in seen_ids:
                seen_ids.add(skill.id)
                resolved.append(skill)
        return resolved
