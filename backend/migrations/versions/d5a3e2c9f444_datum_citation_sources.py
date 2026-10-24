"""result datums: the API search that lists every trial of a sampled data point (design Q14)

Revision ID: d5a3e2c9f444
Revises: c4f2d1b8e333
Create Date: 2026-10-25 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5a3e2c9f444"
down_revision: str | Sequence[str] | None = "c4f2d1b8e333"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "result_datums", sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("result_datums", sa.Column("next_page_token", sa.Text(), nullable=True))
    op.add_column(
        "result_datums",
        sa.Column("complete", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("result_datums", "complete")
    op.drop_column("result_datums", "next_page_token")
    op.drop_column("result_datums", "source")
