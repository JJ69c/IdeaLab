"""Add business_plan JSON column to simulations table.

Stores the on-demand generated business plan so it persists across sessions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'simulations' AND column_name = 'business_plan'"
        )
    )
    if result.fetchone() is None:
        op.add_column(
            "simulations",
            sa.Column("business_plan", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("simulations", "business_plan")
