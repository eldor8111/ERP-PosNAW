"""Add marketplace agent notifications

Revision ID: fc4ac3ab5d14
Revises: fc4ac3ab5d13
Create Date: 2026-10-10 15:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'fc4ac3ab5d14'
down_revision: Union[str, None] = 'fc4ac3ab5d13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_agent_notifications (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            body VARCHAR(1000) NOT NULL,
            notif_type VARCHAR(50) DEFAULT 'general',
            data JSON,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_marketplace_agent_notifications_agent_id ON marketplace_agent_notifications(agent_id);
        CREATE INDEX IF NOT EXISTS ix_marketplace_agent_notifications_id ON marketplace_agent_notifications(id);
        CREATE INDEX IF NOT EXISTS ix_marketplace_agent_notifications_is_read ON marketplace_agent_notifications(is_read);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS marketplace_agent_notifications CASCADE;")
