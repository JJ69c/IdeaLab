"""Make all datetime columns timezone-aware.

asyncpg requires TIMESTAMP WITH TIME ZONE when Python produces
timezone-aware datetimes (datetime.now(timezone.utc)).

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# All (table, column) pairs that use DateTime
_COLUMNS = [
    ("users", "created_at"),
    ("simulations", "created_at"),
    ("simulations", "completed_at"),
    ("assets", "created_at"),
    ("simulation_events", "created_at"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=column == "completed_at",
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=column == "completed_at",
        )
