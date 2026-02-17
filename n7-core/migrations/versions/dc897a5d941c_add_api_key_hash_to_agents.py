
"""add_api_key_hash_to_agents

Revision ID: dc897a5d941c
Revises: d6bac841ac13
Create Date: 2026-02-17 20:23:56.145484

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc897a5d941c'
down_revision: Union[str, None] = 'd6bac841ac13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    # Add api_key_prefix column for O(1) lookup (first 16 chars of API key)
    op.add_column('agents', sa.Column('api_key_prefix', sa.String(length=16), nullable=True))
    
    # Add api_key_hash column to agents table
    op.add_column('agents', sa.Column('api_key_hash', sa.String(), nullable=True))
    
    # For existing agents (if any), set placeholder values
    op.execute("UPDATE agents SET api_key_prefix = 'migration-' WHERE api_key_prefix IS NULL")
    op.execute("UPDATE agents SET api_key_hash = 'migration-placeholder-' || id::text WHERE api_key_hash IS NULL")
    
    # Now make columns not nullable
    op.alter_column('agents', 'api_key_prefix', nullable=False)
    op.alter_column('agents', 'api_key_hash', nullable=False)
    
    # Add indexes for performance
    op.create_index(op.f('ix_agents_api_key_prefix'), 'agents', ['api_key_prefix'], unique=False)
    op.create_index(op.f('ix_agents_api_key_hash'), 'agents', ['api_key_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_agents_api_key_hash'), table_name='agents')
    op.drop_index(op.f('ix_agents_api_key_prefix'), table_name='agents')
    op.drop_column('agents', 'api_key_hash')
    op.drop_column('agents', 'api_key_prefix')
