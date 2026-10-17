"""Alohida fon jarayon (T3.15): `python -m app.worker`.

Scheduler va admin bot pollingni web serverdan alohida jarayonda ishga tushiradi.
Web unit'ga `RUN_BACKGROUND_JOBS=0` qo'yilsa, ular faqat shu jarayonda ishlaydi. Bir nechta
nusxa ishga tushirilsa ham `background_leases` ijarasi tufayli faqat bittasi rahbar bo'ladi.
"""
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from app.database import engine  # noqa: E402
from app.services.background_jobs import run_as_leader  # noqa: E402


def _ensure_tables() -> None:
    """Web jarayon hali ishga tushmagan bo'lsa ham ijara jadvallari bo'lsin."""
    import app.models  # noqa: F401 — barcha modellar mapper registrida
    from app.models.background_job import BackgroundLease
    from app.models.scheduler_run import SchedulerRun
    for model in (BackgroundLease, SchedulerRun):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # parallel jarayon allaqachon yaratgan bo'lishi mumkin
            logging.getLogger(__name__).warning("[Worker] jadval yaratilmadi (%s): %s", model.__tablename__, e)


async def amain() -> None:
    from app.admin_tg_bot.bot_manager import main as run_admin_bot_polling
    from app.services.scheduler import start_scheduler

    import signal

    main_task = asyncio.gather(
        run_as_leader("scheduler", start_scheduler),
        run_as_leader("admin_bot", run_admin_bot_polling),
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            # To'xtatishda `finally` ishlab ijara bo'shatilsin (yangi jarayon darrov rahbar bo'ladi)
            loop.add_signal_handler(sig, main_task.cancel)
        except (NotImplementedError, RuntimeError):
            pass  # Windows
    try:
        await main_task
    except asyncio.CancelledError:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _ensure_tables()
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
