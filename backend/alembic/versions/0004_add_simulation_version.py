"""Add simulation_version and error_message columns to simulations table.

Supports V2 engine alongside V1. Existing rows default to 'v1'.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Idempotent: skip if columns already exist (e.g. from a prior partial run)
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'simulations' AND column_name = 'simulation_version'"
        )
    )
    if result.fetchone() is None:
        op.add_column(
            "simulations",
            sa.Column(
                "simulation_version",
                sa.String(10),
                nullable=False,
                server_default="v1",
            ),
        )
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'simulations' AND column_name = 'error_message'"
        )
    )
    if result.fetchone() is None:
        op.add_column(
            "simulations",
            sa.Column("error_message", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("simulations", "error_message")
    op.drop_column("simulations", "simulation_version")
