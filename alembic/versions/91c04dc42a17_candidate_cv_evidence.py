"""Store CV work evidence alongside the associated file."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "91c04dc42a17"
down_revision = "6e39bcea1d28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("cv_evidence", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "cv_evidence")
