"""Kredit limit qoidasi (T2.12): barcha sotuv yo'llari (create_sale, update_sale ikkala yo'li) uchun yagona yordamchi."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.company import Company


def credit_limit_applies(db: Session, customer) -> bool:
    """Limit mijozga qo'llanadimi: `debt_limit > 0` va (korxona `credit_limit_scope == "all"` yoki mijoz distribyutor)."""
    if Decimal(str(customer.debt_limit or 0)) <= 0:
        return False
    if getattr(customer, "customer_type", "retail") == "distributor":
        return True
    scope = None
    if getattr(customer, "company_id", None):
        scope = db.query(Company.credit_limit_scope).filter(Company.id == customer.company_id).scalar()
    return scope == "all"


def check_credit_limit(db: Session, customer, delta_uzs) -> None:
    """`customer.debt_balance + delta_uzs > debt_limit` bo'lsa 400.

    DIQQAT: chaqiruvchi mijoz qatorini `with_for_update()` (masalan `lock_customer`) bilan olgan bo'lishi
    shart — aks holda parallel ikki sotuv limitdan oshib ketishi mumkin. `debt_limit = 0` — cheklanmagan.
    """
    delta = Decimal(str(delta_uzs or 0))
    if delta <= 0 or not credit_limit_applies(db, customer):
        return
    limit = Decimal(str(customer.debt_limit or 0))
    current = Decimal(str(customer.debt_balance or 0))
    new_debt = current + delta
    if new_debt > limit:
        fmt = lambda v: f"{v:,.0f}".replace(",", " ")
        raise HTTPException(
            status_code=400,
            detail=(
                f"Kredit limitidan oshadi: limit {fmt(limit)}, "
                f"joriy qarz {fmt(current)}, "
                f"bu sotuvdan keyin {fmt(new_debt)} so'm. "
                f"Qarzni yoping yoki limitni oshiring."
            ),
        )
