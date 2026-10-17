"""Hujjat raqamlarini atomar hisoblagich bilan yaratish (T1.14).

Format: `{doc_type}{YYYYMMDD}-{company_id}-{branch_id or 0}-{seq:04d}`,
masalan `S20261014-12-3-0007`. Hisoblagich korxona/filial/hujjat turi/kun kesimida
bitta SQL (`INSERT .. ON CONFLICT DO UPDATE .. RETURNING`) bilan oshiriladi va
chaqiruvchi tranzaksiyasi ichida bajariladi: tranzaksiya bekor bo'lsa hisoblagich ham
bekor bo'ladi (raqamlarda bo'shliq qolmaydi), parallel so'rovlar esa qator qulfi tufayli
ketma-ketlashadi. Satr-`max()` / `count()+1` xatolari (9999 dan keyin, o'chirishdan keyin
takrorlanish) yo'q.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.document_counter import DocumentCounter

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Tashkent")
except Exception:  # tzdata yo'q muhitda (UTC+5, DST yo'q)
    _TZ = timezone(timedelta(hours=5))


def tashkent_today() -> date:
    """Toshkent vaqti bo'yicha bugungi sana (UTC bo'yicha emas)."""
    return datetime.now(_TZ).date()


def _upsert_returning(db: Session, values: dict) -> int:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:  # sqlite (testlar) — bir xil ON CONFLICT sintaksisi
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(DocumentCounter).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_id", "branch_id", "doc_type", "period"],
        set_={"last_value": DocumentCounter.last_value + 1},
    ).returning(DocumentCounter.last_value)
    return int(db.execute(stmt).scalar_one())


def next_document_number(
    db: Session,
    *,
    company_id: int,
    branch_id: Optional[int],
    doc_type: str,
    on_date: Optional[date] = None,
) -> str:
    """Keyingi hujjat raqamini qaytaradi. `on_date` berilmasa — Toshkent bo'yicha bugun."""
    if company_id is None:
        raise ValueError("Hujjat raqami uchun company_id majburiy")
    day = on_date or tashkent_today()
    if isinstance(day, datetime):
        day = day.date()
    period = day.strftime("%Y%m%d")
    branch = int(branch_id or 0)
    seq = _upsert_returning(db, {
        "company_id": int(company_id),
        "branch_id": branch,
        "doc_type": doc_type,
        "period": period,
        "last_value": 1,
    })
    return f"{doc_type}{period}-{int(company_id)}-{branch}-{seq:04d}"
