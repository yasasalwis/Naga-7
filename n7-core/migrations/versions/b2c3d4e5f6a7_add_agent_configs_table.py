"""add agent_configs table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20

Adds the agent_configs table for centralized, DB-backed per-agent configuration.
Replaces the static .env file approach written during deployment with a versioned,
encrypted config store that agents poll on startup.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_configs',
        sa.Column('id', PGUUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', PGUUID(as_uuid=True), nullable=False),

        # Connectivity — Fernet-encrypted at rest
        sa.Column('nats_url_enc', sa.String(), nullable=True),
        sa.Column('core_api_url_enc', sa.String(), nullable=True),

        # Behaviour tunables
        sa.Column('log_level', sa.String(), nullable=True),
        sa.Column('environment', sa.String(), nullable=True),
        sa.Column('zone', sa.String(), nullable=True),

        # Thresholds
        sa.Column('detection_thresholds', sa.JSON(), nullable=True),
        sa.Column('probe_interval_seconds', sa.Integer(), nullable=True),

        # Capabilities
        sa.Column('capabilities', sa.JSON(), nullable=True),

        # Versioning
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_agent_configs_agent_id'),
        'agent_configs',
        ['agent_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_configs_agent_id'), table_name='agent_configs')
    op.drop_table('agent_configs')
