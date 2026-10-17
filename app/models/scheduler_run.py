from sqlalchemy import Column, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class SchedulerRun(Base):
    """Scheduler vazifalarining kunlik bajarilish registri (T2.10).

    (job, scope, run_date) unikal: bir vazifa bir kunda bir marta "egallanadi" (claim) —
    restart va ko'p worker/server holatida ham dublikat yuborilmaydi.
    scope: 'global' yoki 'company:{id}'. status: running | done | failed.
    """
    __tablename__ = "scheduler_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job = Column(String(40), nullable=False)
    scope = Column(String(64), nullable=False, default="global", server_default="global")
    run_date = Column(Date, nullable=False)
    status = Column(String(12), nullable=False, default="running", server_default="running")
    attempts = Column(Integer, nullable=False, default=1, server_default="1")
    claimed_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    detail = Column(Text, nullable=True)

    __table_args__ = (
        Index("uq_scheduler_runs_job_scope_date", "job", "scope", "run_date", unique=True),
    )
