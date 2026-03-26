"""initial schema — full table creation for PostgreSQL and SQLite

Revision ID: 0001
Revises:
Create Date: 2026-03-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- simulations ---
    op.create_table(
        "simulations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_title", sa.String(200), nullable=False),
        sa.Column("idea_description", sa.Text, nullable=False),
        sa.Column("idea_category", sa.String(100), nullable=False, server_default="general"),
        sa.Column("idea_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("report", sa.JSON, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        # Variant lineage
        sa.Column("parent_simulation_id", sa.String(36), nullable=True, index=True),
        sa.Column("root_simulation_id", sa.String(36), nullable=True, index=True),
        sa.Column("variant_name", sa.String(200), nullable=True),
        sa.Column("changed_fields", sa.JSON, nullable=True),
    )

    # --- assets ---
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- simulation_events ---
    op.create_table(
        "simulation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("simulation_id", sa.String(36), nullable=False, index=True),
        sa.Column("tick", sa.Integer, nullable=False),
        sa.Column("npc_id", sa.String(50), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("data", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("simulation_events")
    op.drop_table("assets")
    op.drop_table("simulations")
