"""T2.10: scheduler_runs — scheduler vazifalarining kunlik bajarilish registri

Revision ID: t2_10
Revises:
Create Date: 2026-10-16
"""
from alembic import op

revision = 't2_10'
down_revision = 't2_8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_runs (
            id SERIAL PRIMARY KEY,
            job VARCHAR(40) NOT NULL,
            scope VARCHAR(64) NOT NULL DEFAULT 'global',
            run_date DATE NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'running',
            attempts INTEGER NOT NULL DEFAULT 1,
            claimed_at TIMESTAMP NOT NULL DEFAULT now(),
            finished_at TIMESTAMP,
            detail TEXT
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduler_runs_job_scope_date "
        "ON scheduler_runs (job, scope, run_date)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_runs")
