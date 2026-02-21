"""add_node_metadata_to_agents

Adds node_metadata column to the agents table for rich hardware/OS identity data.
  - node_metadata: JSON dict populated by Sentinel on every restart via NATS n7.node.metadata.>
    Contains: cpu_model, cpu_cores, ram_total_mb, os_name, os_version, kernel_version,
              hostname, mac_address, python_version, agent_version

Nullable so existing agents and Strikers (which don't publish metadata) are unaffected.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-21 00:00:00.000000

Ref: TDD Section 4.3 Agent Registry, SRS FR-S001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('node_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('agents', 'node_metadata')
