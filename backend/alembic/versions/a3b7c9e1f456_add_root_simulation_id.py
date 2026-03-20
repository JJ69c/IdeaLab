"""add root_simulation_id column

Revision ID: a3b7c9e1f456
Revises: 59c5207a4198
Create Date: 2026-03-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b7c9e1f456'
down_revision: Union[str, Sequence[str], None] = '59c5207a4198'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('simulations', sa.Column('root_simulation_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_simulations_root_simulation_id'), 'simulations', ['root_simulation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_simulations_root_simulation_id'), table_name='simulations')
    op.drop_column('simulations', 'root_simulation_id')
