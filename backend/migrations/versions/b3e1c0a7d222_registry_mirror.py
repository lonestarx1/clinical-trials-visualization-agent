"""registry schema: the mirror's trials and sync runs (design Q22)

Revision ID: b3e1c0a7d222
Revises: 6ebfd3b4b50c
Create Date: 2026-10-25 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3e1c0a7d222"
down_revision: str | Sequence[str] | None = "6ebfd3b4b50c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SCHEMA IF NOT EXISTS registry")
    op.create_table(
        "trials",
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("record", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("last_update_post_date", sa.Date(), nullable=True),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("nct_id"),
        schema="registry",
    )
    op.create_index("trials_start_year", "trials", ["start_year"], schema="registry")
    op.create_table(
        "sync_runs",
        sa.Column("run_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("since", sa.Date(), nullable=True),
        sa.Column("upserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("removed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('load','update')", name="sync_runs_kind"),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="sync_runs_status"),
        sa.PrimaryKeyConstraint("run_id"),
        schema="registry",
    )
    op.create_index(
        "sync_runs_status_finished", "sync_runs", ["status", "finished_at"], schema="registry"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sync_runs", schema="registry")
    op.drop_table("trials", schema="registry")
    op.execute("DROP SCHEMA IF EXISTS registry")
