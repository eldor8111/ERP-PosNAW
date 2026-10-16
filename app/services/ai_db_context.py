"""
app/services/ai_db_context.py
─────────────────────────────
AI Copilot va tahlil so'rovlari uchun PostgreSQL sessiyasida korxona izolyatsiyasi (RLS)
va xavfsiz o'qish (ai_readonly) rolini boshqarish.
"""
from contextlib import contextmanager
from typing import Generator
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

_log = logging.getLogger("ai_db_context")


def set_ai_tenant_context(db: Session, company_id: int, read_only: bool = True) -> None:
    """
    Joriy tranzaksiya doirasida PostgreSQL sessiya kontekstini o'rnatadi.
    is_local=True parametri sababli sozlamalar tranzaksiya yakunlanganda (commit/rollback)
    avtomatik bekor bo'ladi.
    """
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    if not bind or bind.dialect.name != "postgresql":
        return

    try:
        # 1. Korxona ID sini sessiya o'zgaruvchisiga o'rnatamiz (fail-closed RLS uchun)
        db.execute(
            text("SELECT set_config('app.company_id', :cid, true)"),
            {"cid": str(company_id)}
        )

        # 2. Agar faqat o'qish rejimi bo'lsa, ai_readonly roliga o'tamiz
        if read_only:
            db.execute(text("SET LOCAL ROLE ai_readonly"))
    except Exception as e:
        _log.warning("set_ai_tenant_context muvaffaqiyatsiz: %s", e)


def clear_ai_tenant_context(db: Session) -> None:
    """PostgreSQL sessiya kontekstini tozalaydi."""
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    if not bind or bind.dialect.name != "postgresql":
        return

    try:
        db.execute(text("RESET ROLE"))
    except Exception:
        pass
    try:
        db.execute(text("SELECT set_config('app.company_id', '', true)"))
    except Exception:
        pass


@contextmanager
def ai_tenant_context(db: Session, company_id: int, read_only: bool = True) -> Generator[Session, None, None]:
    """
    Kontekst menejeri: AI operatsiyalari vaqtida RLS va ai_readonly rolini faollashtiradi,
    tugagach sessiyani asl holatiga qaytaradi.
    """
    set_ai_tenant_context(db, company_id, read_only=read_only)
    try:
        yield db
    finally:
        clear_ai_tenant_context(db)
