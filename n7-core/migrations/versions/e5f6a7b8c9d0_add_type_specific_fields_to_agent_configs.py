"""add type-specific fields to agent_configs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-22

Adds sentinel-specific and striker-specific config columns to agent_configs table.

Sentinel:
  - enabled_probes: JSON list of active probe types ["system", "network", "process", "file"]

Striker:
  - allowed_actions: JSON list of permitted action types (null = all capabilities allowed)
  - action_defaults: JSON dict of per-action default params e.g. {"network_block": {"duration": 3600}}
  - max_concurrent_actions: integer cap on parallel action execution (null = unlimited)

Note: detection_thresholds and probe_interval_seconds (sentinel) and capabilities (striker)
already exist from migration b2c3d4e5f6a7. This migration adds the missing new columns only.

Ref: TDD Section 5.x Agent Configuration Management, SRS FR-K*, FR-S*
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sentinel-specific
    op.add_column('agent_configs', sa.Column('enabled_probes', sa.JSON(), nullable=True))

    # Striker-specific
    op.add_column('agent_configs', sa.Column('allowed_actions', sa.JSON(), nullable=True))
    op.add_column('agent_configs', sa.Column('action_defaults', sa.JSON(), nullable=True))
    op.add_column('agent_configs', sa.Column('max_concurrent_actions', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_configs', 'max_concurrent_actions')
    op.drop_column('agent_configs', 'action_defaults')
    op.drop_column('agent_configs', 'allowed_actions')
    op.drop_column('agent_configs', 'enabled_probes')
