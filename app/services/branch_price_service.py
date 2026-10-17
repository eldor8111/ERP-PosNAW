"""Filial narxlari (T4.3): korxona narxini filial bo'yicha ustidan yozish.

Filial narxi yo'q (yoki kerakli ustun NULL) bo'lsa — mahsulotning korxona narxi qoladi.
"""
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.branch_price import BranchProductPrice


def get_branch_prices(db: Session, company_id: int, branch_id: Optional[int],
                      product_ids: Iterable[int]) -> dict:
    """`{(product_id, variant_id): BranchProductPrice}` — shu filial va mahsulotlar uchun.
    `variant_id` NULL bo'lsa kalit `(product_id, None)`. Filial yoki mahsulot yo'q bo'lsa `{}`."""
    ids = {int(i) for i in (product_ids or []) if i}
    if not branch_id or company_id is None or not ids:
        return {}
    rows = db.query(BranchProductPrice).filter(
        BranchProductPrice.company_id == company_id,
        BranchProductPrice.branch_id == branch_id,
        BranchProductPrice.product_id.in_(ids),
    ).all()
    return {(r.product_id, r.variant_id): r for r in rows}


def pick_branch_price(prices_map: Optional[dict], product_id: int, variant_id: Optional[int] = None):
    """Qator uchun filial narxi: avval variantning o'ziniki, bo'lmasa mahsulotniki (variant_id NULL)."""
    if not prices_map:
        return None
    if variant_id is not None:
        found = prices_map.get((product_id, variant_id))
        if found is not None:
            return found
    return prices_map.get((product_id, None))


def resolve_price_branch_id(db: Session, user, warehouse_id=None) -> Optional[int]:
    """Narx uchun filial: ombor filiali (o'z korxonasidan) -> xodimning joriy filiali.

    DIQQAT: "korxonaning birinchi filiali" fallbacki ISHLATILMAYDI — u noto'g'ri filial narxini tanlab
    qo'yadi. Filial aniqlanmasa `None` (korxona narxi ishlatiladi)."""
    from app.core.branch_context import effective_branch_id
    from app.services.sale_helpers import _warehouse_branch_id

    company_id = getattr(user, "company_id", None)
    found = _warehouse_branch_id(db, company_id, warehouse_id)
    if found:
        return found
    try:
        return effective_branch_id(db, user)
    except Exception:  # noqa: BLE001 — filial kontekstida xato narxni to'xtatmasin
        return None
