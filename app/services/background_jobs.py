"""Fon vazifalar infratuzilmasi (T3.15): ko'p worker'da bitta "rahbar" jarayon.

Gunicorn bir necha worker bilan ishlaganda scheduler va admin bot polling (getUpdates) faqat
BITTA jarayonda ishlashi kerak. Rahbarlik `background_leases` jadvalidagi ijara (lease) orqali
aniqlanadi: ijara muddati o'tgan yoki egasi o'zimiz bo'lsagina olinadi/yangilanadi.
Jadval orqali ishlaydi (advisory lock emas) — PgBouncer/pooler da ham to'g'ri.

Kunlik vazifalarning idempotentligi (bir kunda bir marta) alohida: `scheduler_runs`
(app/services/scheduler.py: claim_run) — T2.10.
"""
import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

import app.database as _database
from app.models.background_job import BackgroundLease

logger = logging.getLogger(__name__)

_PROCESS_HOLDER = None


def process_holder() -> str:
    """Shu jarayonning noyob nomi: host:pid:tasodifiy. Jarayon umri davomida o'zgarmaydi."""
    global _PROCESS_HOLDER
    if _PROCESS_HOLDER is None:
        _PROCESS_HOLDER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    return _PROCESS_HOLDER


def background_jobs_enabled() -> bool:
    """RUN_BACKGROUND_JOBS=0 bo'lsa web jarayon scheduler/botni ishga tushirmaydi (alohida worker rejimi)."""
    return os.environ.get("RUN_BACKGROUND_JOBS", "1").strip() != "0"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert_fn(db):
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def _acquire(name: str, holder: str, ttl: int, now: datetime = None) -> bool:
    """Ijarani olish/yangilash (xatoda istisno ko'taradi). True = ijara endi `holder` da."""
    from sqlalchemy import or_
    now = now or _utcnow()
    expires = now + timedelta(seconds=ttl)
    db = _database.SessionLocal()
    try:
        insert = _insert_fn(db)
        stmt = insert(BackgroundLease).values(name=name, holder=holder, expires_at=expires)
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={"holder": holder, "expires_at": expires},
            where=or_(BackgroundLease.expires_at < now, BackgroundLease.holder == holder),
        ).returning(BackgroundLease.holder)
        row = db.execute(stmt).first()
        db.commit()
        return row is not None and row[0] == holder
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()


def try_acquire_lease(name: str, holder: str, ttl: int = 60, now: datetime = None) -> bool:
    """Ijarani olishga/yangilashga urinadi. True = `holder` hozir rahbar.

    Boshqa egasining muddati o'tmagan ijarasi bo'lsa False. Baza xatosi (masalan jadval hali yo'q)
    loglanadi va False qaytadi — chaqiruvchi (scheduler) to'xtab qolmaydi."""
    try:
        return _acquire(name, holder, ttl, now)
    except Exception as e:
        logger.error("[Lease] %s ijarasini olishda xato: %s", name, e)
        return False


def release_lease(name: str, holder: str) -> None:
    """Ijarani bo'shatadi (faqat o'ziniki) — HUP/yopilishda yangi worker darrov rahbar bo'ladi."""
    db = _database.SessionLocal()
    try:
        db.query(BackgroundLease).filter(
            BackgroundLease.name == name, BackgroundLease.holder == holder,
        ).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        logger.error("[Lease] %s ijarasini bo'shatishda xato: %s", name, e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def _stop_task(task) -> None:
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("[Lease] vazifa to'xtatilganda xato: %s", e)


async def run_as_leader(name: str, coro_factory, ttl: int = 60, beat: int = 15) -> None:
    """`coro_factory()` ni faqat rahbar jarayonda ishlatadi.

    Har `beat` soniyada ijara olinadi/yangilanadi. Olinsa vazifa task sifatida boshlanadi;
    ijara boshqaga o'tsa, ijara yangilanmay `ttl` o'tsa yoki vazifa tugasa/yiqilsa vazifa
    to'xtatiladi (yiqilgan vazifa ijarani bo'shatib, keyingi beat'da qayta olinadi).
    `finally` da ijara bo'shatiladi."""
    holder = process_holder()
    loop = asyncio.get_running_loop()
    task = None
    last_ok = None  # ijara oxirgi marta muvaffaqiyatli tasdiqlangan vaqt (loop.time())
    try:
        while True:
            held = False
            try:
                held = await asyncio.to_thread(_acquire, name, holder, ttl)
                if held:
                    last_ok = loop.time()
            except Exception as e:
                # Vaqtinchalik baza xatosi: ijara muddati tugamaguncha rahbarlikni saqlaymiz
                logger.error("[Lease] %s ijarasi yangilanmadi: %s", name, e)
                held = last_ok is not None and (loop.time() - last_ok) < ttl

            if held:
                if task is not None and task.done():
                    exc = None if task.cancelled() else task.exception()
                    logger.error("[Lease] %s vazifasi tugadi%s — ijara bo'shatilib qayta olinadi",
                                 name, f": {exc!r}" if exc else "")
                    task = None
                    last_ok = None
                    await asyncio.to_thread(release_lease, name, holder)
                elif task is None:
                    logger.info("[Lease] %s: shu jarayon rahbar (%s)", name, holder)
                    task = asyncio.create_task(coro_factory())
            else:
                if task is not None:
                    logger.warning("[Lease] %s: rahbarlik yo'qoldi — vazifa to'xtatilmoqda", name)
                    await _stop_task(task)
                    task = None
                last_ok = None
            await asyncio.sleep(beat)
    finally:
        await _stop_task(task)
        try:
            await asyncio.to_thread(release_lease, name, holder)
        except BaseException:
            pass
