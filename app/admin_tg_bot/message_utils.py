"""Admin bot xabarlari uchun yordamchilar (T3.16): filial/ombor/kassa qatori."""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.moliya import Wallet
from app.models.warehouse import Warehouse
from app.utils.telegram_text import esc


def describe_location(
    db: Session,
    warehouse_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    wallet_id: Optional[int] = None,
) -> str:
    """Xabar uchun joy qatori, masalan `🏬 Filial: Chilonzor · Ombor: Asosiy` (HTML-escape qilingan).

    Faqat korxonada 2 va undan ko'p FAOL filial bo'lsa chiqadi; aks holda yoki aniqlab bo'lmasa — "".
    `branch_id` berilmasa filial ombor (keyin kassa) orqali topiladi: ombori yo'q eski sotuvlarda
    "Filial: —" yozilmaydi, qator butunlay yashiriladi. Dinamik nomlar HTML-escape qilinadi.
    """
    wh = db.get(Warehouse, warehouse_id) if warehouse_id else None
    wallet = db.get(Wallet, wallet_id) if wallet_id else None

    company_id = None
    for obj in (wh, wallet):
        if obj is not None and obj.company_id:
            company_id = obj.company_id
            break
    if branch_id is None:
        branch_id = (wh.branch_id if wh is not None else None) or (wallet.branch_id if wallet is not None else None)
    branch = db.get(Branch, branch_id) if branch_id else None
    if company_id is None and branch is not None:
        company_id = branch.company_id
    if company_id is None:
        return ""
    # Begona korxona obyekti (nomi sizib chiqmasin)
    if branch is not None and branch.company_id != company_id:
        branch = None

    active = db.query(func.count(Branch.id)).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).scalar() or 0
    if active < 2:
        return ""

    parts = []
    if branch is not None:
        parts.append(f"Filial: {esc(branch.name)}")
    if wh is not None and wh.company_id == company_id:
        parts.append(f"Ombor: {esc(wh.name)}")
    if wallet is not None and wallet.company_id == company_id:
        parts.append(f"Kassa: {esc(wallet.name)}")
    if branch is None or not parts:
        return ""   # filial noma'lum — "Filial: —" ko'rsatilmaydi
    return "🏬 " + " · ".join(parts)
