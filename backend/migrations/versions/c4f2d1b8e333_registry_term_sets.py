"""registry term sets: the trials each search term matches (design Q22)

Revision ID: c4f2d1b8e333
Revises: b3e1c0a7d222
Create Date: 2026-10-25 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f2d1b8e333"
down_revision: str | Sequence[str] | None = "b3e1c0a7d222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "term_sets",
        sa.Column("term_key", sa.Text(), nullable=False),
        sa.Column("param", sa.Text(), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("term_key"),
        schema="registry",
    )
    op.create_table(
        "term_members",
        sa.Column("term_key", sa.Text(), nullable=False),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["term_key"], ["registry.term_sets.term_key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("term_key", "nct_id"),
        schema="registry",
    )
    op.create_index("term_members_nct_id", "term_members", ["nct_id"], schema="registry")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("term_members", schema="registry")
    op.drop_table("term_sets", schema="registry")
