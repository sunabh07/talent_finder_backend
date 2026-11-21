"""Skill vocabulary, shared across tenants, plus its alias table.

The vocabulary is deliberately **global** rather than per-tenant. A skill row
holds nothing but a label, so sharing it leaks no tenant data, and it keeps
matching a single integer join instead of a cross-tenant string comparison.
Isolation is enforced on candidates and job orders, which is where the tenant
data actually lives.
"""

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Human-facing label, e.g. "React.js"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Canonical lookup form produced by core.normalization.normalize_skill
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    aliases: Mapped[list["SkillAlias"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("normalized_name = lower(normalized_name)", name="normalized_is_lower"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Skill id={self.id} name={self.name!r}>"


class SkillAlias(Base, TimestampMixin):
    """Explicit synonym -> canonical skill mapping.

    This is the deliberate alternative to fuzzy string matching. "js" resolving
    to "JavaScript" is a reviewable row in a table; a similarity threshold is an
    invisible heuristic that makes the ranking non-deterministic and the tests
    unstable. Aliases are resolved **on write**, so matching itself stays an
    exact join.
    """

    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_normalized: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    skill: Mapped[Skill] = relationship(back_populates="aliases")

    __table_args__ = (
        CheckConstraint("alias_normalized = lower(alias_normalized)", name="alias_is_lower"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SkillAlias {self.alias_normalized!r} -> skill_id={self.skill_id}>"
