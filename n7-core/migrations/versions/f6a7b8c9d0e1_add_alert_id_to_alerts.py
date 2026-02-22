"""add alert_id to alerts

Adds the public-facing alert_id UUID column to the alerts table.

Previously the Alert model only had UUIDMixin.id (internal surrogate key).
ThreatCorrelatorService and LLMAnalyzerService both use alert_id as the
canonical identifier for cross-service correlation; without this column,
every AlertModel(..., alert_id=...) constructor call silently ignored the
field, causing:
  - All alerts to appear without a public ID in the API response
  - LLMAnalyzerService _persist_narrative() WHERE clause to match nothing
    (updating 0 rows), so llm_narrative was never written back
  - /api/v1/alerts/ returning alert_id=null for every row

The new column is UNIQUE and NOT NULL (backfilled from id for existing rows).

This migration merges the two previously divergent heads:
  - e5f6a7b8c9d0 (add_type_specific_fields_to_agent_configs)
  - (previously forked off c3d4e5f6a7b8 in error)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-22 00:00:00.000000

Ref: TDD Section 4.5 Data Architecture, SRS FR-C009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add alert_id as nullable first so existing rows don't violate NOT NULL
    op.add_column(
        'alerts',
        sa.Column('alert_id', UUID(as_uuid=True), nullable=True)
    )
    # Backfill: copy id into alert_id for all existing rows
    op.execute("UPDATE alerts SET alert_id = id WHERE alert_id IS NULL")
    # Now enforce NOT NULL and UNIQUE
    op.alter_column('alerts', 'alert_id', nullable=False)
    op.create_unique_constraint('uq_alerts_alert_id', 'alerts', ['alert_id'])


def downgrade() -> None:
    op.drop_constraint('uq_alerts_alert_id', 'alerts', type_='unique')
    op.drop_column('alerts', 'alert_id')
