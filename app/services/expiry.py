"""T1.8: yaroqlilik muddati qoidasi — ro'yxat, qo'lda hisobdan chiqarish, cron va Telegram
ogohlantirishi uchun YAGONA so'rov (avval uch joyda har xil filtr edi)."""
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Query, Session

from app.models.batch import Batch
from app.models.category import Category
from app.models.product import Product


def _day_start(d) -> datetime:
    """Sana -> kun boshi (Batch.expiry_date DateTime ustuni; SQLite sana qabul qilmaydi)."""
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, time.min)


def expired_batches_query(
    db: Session,
    company_id: int,
    today: date,
    *,
    warehouse_ids: Optional[Iterable[int]] = None,
    only_expired: bool = False,
    expiry_until: Optional[date] = None,
    expiry_from: Optional[date] = None,
) -> Query:
    """Muddati nazorat qilinadigan partiyalar (Batch) so'rovi.

    Qoida: Batch.quantity > 0, expiry_date bor, kategoriyasi "tez buziladigan" (is_perishable).
    - only_expired=True: faqat muddati o'tganlar (expiry_date < today)
    - expiry_from/expiry_until: muddat oralig'i (ikkala chegara kiritiladi)
    - warehouse_ids: ombor filtri (bo'sh ro'yxat = hech narsa)
    """
    q = (
        db.query(Batch)
        .join(Product, Product.id == Batch.product_id)
        .join(Category, Category.id == Product.category_id)
        .filter(
            Batch.company_id == company_id,
            Batch.quantity > 0,
            Batch.expiry_date.isnot(None),
            Category.is_perishable == True,  # noqa: E712
        )
    )
    if warehouse_ids is not None:
        q = q.filter(Batch.warehouse_id.in_(list(warehouse_ids)))
    if only_expired:
        q = q.filter(Batch.expiry_date < _day_start(today))
    if expiry_from is not None:
        q = q.filter(Batch.expiry_date >= _day_start(expiry_from))
    if expiry_until is not None:
        q = q.filter(Batch.expiry_date < _day_start(expiry_until + timedelta(days=1)))
    return q
