"""Filial tanlash yordamchilari (T1.15).

Mijoz/buyurtma uchun yagona "faol filialni tanlash" qoidasi: do'kon (shop), marketplace va
POST /orders bir xil zanjirdan foydalanadi.
"""
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.warehouse import Warehouse

NO_ACTIVE_BRANCH = "Faol filial topilmadi"
BRANCH_NOT_FOUND = "Filial topilmadi"
BRANCH_INACTIVE = "Filial faol emas"


def default_branch_id(db: Session, company_id: Optional[int]) -> Optional[int]:
    """Korxonaning birinchi FAOL filiali (id bo'yicha); faol filial yo'q bo'lsa `None`."""
    if company_id is None:
        return None
    row = db.query(Branch.id).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id.asc()).first()
    return row[0] if row else None


def fallback_active_branch_id(db: Session, user, *, wallet=None, warehouse_id: Optional[int] = None) -> Optional[int]:
    """T1.12: filialsiz amal (kassa xarajati, qarz to'lovi, ta'minotchi to'lovi) uchun FAOL filial:
    kassa/ombor/asosiy filial (`fallback_branch_id`) faol bo'lsa shu, aks holda `default_branch_id`.
    Arxivlangan filial hech qachon tanlanmaydi; faol filial bo'lmasa `None`."""
    from app.services.branch_provisioning import fallback_branch_id

    company_id = getattr(user, "company_id", None)
    fb = fallback_branch_id(db, user, wallet=wallet, warehouse_id=warehouse_id)
    return active_branch_id(db, fb, company_id) or default_branch_id(db, company_id)


def fallback_active_branch_id_or_400(db: Session, user, *, wallet=None, warehouse_id: Optional[int] = None) -> int:
    """`fallback_active_branch_id`; faol filial topilmasa 400."""
    branch_id = fallback_active_branch_id(db, user, wallet=wallet, warehouse_id=warehouse_id)
    if branch_id is None:
        # Korxonada filial umuman yo'q (T0.7) va "faol filial yo'q" (hammasi arxivlangan) xabarlari alohida
        has_any = db.query(Branch.id).filter(Branch.company_id == getattr(user, "company_id", None)).first()
        if not has_any:
            from app.services.branch_provisioning import NO_BRANCH_COMPANY
            raise HTTPException(status_code=400, detail=NO_BRANCH_COMPANY)
        raise HTTPException(status_code=400, detail=NO_ACTIVE_BRANCH)
    return branch_id


def get_active_branch(db: Session, branch_id: int, company_id: Optional[int]) -> Branch:
    """Filial shu korxonaniki va faol ekanini tekshiradi.
    Begona korxona yoki mavjud bo'lmagan filial uchun 404, nofaol uchun 400."""
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.company_id == company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    if not branch.is_active:
        raise HTTPException(status_code=400, detail=BRANCH_INACTIVE)
    return branch


def active_branch_id(db: Session, branch_id: Optional[int], company_id: Optional[int]) -> Optional[int]:
    if not branch_id:
        return None
    row = db.query(Branch.id).filter(
        Branch.id == branch_id,
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).first()
    return row[0] if row else None


def resolve_customer_branch_id(
    db: Session,
    customer,
    company_id: Optional[int],
    warehouse_ids: Optional[Iterable[int]] = None,
) -> Optional[int]:
    """Buyurtma uchun filialni tanlaydi. Tartib:
      1. `customer.branch_id` (faqat shu korxonaniki va faol bo'lsa);
      2. `warehouse_ids` ichidagi birinchi faol filialli omborning filiali;
      3. `default_branch_id` (korxonaning birinchi faol filiali).
    Hech biri bo'lmasa `None` — chaqiruvchi HTTP 400 "Faol filial topilmadi" beradi."""
    found = active_branch_id(db, getattr(customer, "branch_id", None), company_id)
    if found:
        return found

    wh_ids = [w for w in (warehouse_ids or []) if w]
    if wh_ids:
        # Ro'yxat tartibini saqlaymiz: birinchi mos keladigan ombor yutadi
        rows = {
            w.id: w.branch_id
            for w in db.query(Warehouse.id, Warehouse.branch_id).filter(
                Warehouse.id.in_(wh_ids), Warehouse.company_id == company_id,
            ).all()
        }
        for wid in wh_ids:
            found = active_branch_id(db, rows.get(wid), company_id)
            if found:
                return found

    return default_branch_id(db, company_id)


# ─── T1.12: filial hayot sikli (yopish / arxivlash / qayta ochish) ───────────────────────────

# Blokerlar nomlari (xabar uchun): {kalit: "son + nom"}
_BLOCKER_LABELS = {
    "open_shifts": "ochiq smena",
    "open_kassa": "ochiq kassa",
    "wallets_with_balance": "balansi bor kassa",
    "stock": "qoldiqli ombor",
    "active_users": "faol xodim",
    "open_orders": "ochiq buyurtma",
    "pending_transfers": "kutilayotgan ko'chirish",
    "open_counts": "ochiq inventarizatsiya",
    "open_production": "ochiq ishlab chiqarish",
    "open_purchase_orders": "ochiq xarid buyurtmasi",
    "pending_sales": "kutilayotgan sotuv",
}

BRANCH_REASSIGN_SELF = "Xodimlarni yopilayotgan filialning o'ziga ko'chirib bo'lmaydi"
BRANCH_ALREADY_ACTIVE = "Filial allaqachon faol"


class BranchCloseBlocked(Exception):
    """Filialni yopib bo'lmaydi: `blockers` — close-check natijasi, `detail` — o'zbekcha sabablar."""

    def __init__(self, blockers: dict):
        self.blockers = blockers
        self.detail = blockers_message(blockers)
        super().__init__(self.detail)


def blockers_message(blockers: dict) -> str:
    """'Filialni yopib bo'lmaydi: 2 ta ochiq smena, 1 ta faol xodim' ko'rinishidagi matn."""
    parts = []
    for key, label in _BLOCKER_LABELS.items():
        val = blockers.get(key)
        n = len(val) if isinstance(val, list) else int(val or 0)
        if n:
            parts.append(f"{n} ta {label}")
    return "Filialni yopib bo'lmaydi: " + ", ".join(parts)


def _branch_user_ids(db: Session, branch: Branch, exclude_user_id: Optional[int] = None) -> set:
    """Shu filialga biriktirilgan FAOL xodimlar: `users.branch_id`, `user_companies.branch_id`
    (T1.2) va `user_branches` (qo'shimcha filiallar) bo'yicha."""
    from app.models.user import User, UserStatus
    from app.models.user_branch import UserBranch
    from app.models.user_company import UserCompany

    ids = {r[0] for r in db.query(User.id).filter(
        User.branch_id == branch.id, User.status == UserStatus.active,
    ).all()}
    ids |= {r[0] for r in db.query(UserCompany.user_id).join(User, User.id == UserCompany.user_id).filter(
        UserCompany.branch_id == branch.id, UserCompany.company_id == branch.company_id,
        UserCompany.is_active == True,  # noqa: E712
        User.status == UserStatus.active,
    ).all()}
    ids |= {r[0] for r in db.query(UserBranch.user_id).join(User, User.id == UserBranch.user_id).filter(
        UserBranch.branch_id == branch.id, UserBranch.company_id == branch.company_id,
        User.status == UserStatus.active,
    ).all()}
    ids.discard(exclude_user_id)
    return ids


def branch_close_blockers(db: Session, branch: Branch, reassign_users: bool = False,
                          exclude_user_id: Optional[int] = None) -> dict:
    """Filialni yopishga to'sqinlik qiluvchi narsalar. Hammasi bo'sh/0 bo'lsa filialni yopish mumkin.

    `reassign_users=True` — xodimlar boshqa filialga ko'chiriladi, shuning uchun `active_users` 0 hisoblanadi.
    `exclude_user_id` — filialni yopayotgan xodimning o'zi (admin) `active_users` ga kirmaydi.
    Qoldiq va balans faqat FAOL ombor/kassalar bo'yicha (nofaol omborni boshqa omborga o'tkazib bo'lmaydi,
    shuning uchun u yopishni abadiy to'sib qo'ymasligi kerak)."""
    from sqlalchemy import func, or_

    from app.models.inventory import StockLevel
    from app.models.inventory_count import CountStatus, InventoryCount
    from app.models.moliya import Wallet
    from app.models.order import Order, OrderStatus
    from app.models.production_order import ProductionOrder, ProductionOrderStatus
    from app.models.purchase_order import POStatus, PurchaseOrder
    from app.models.sale import Sale, SaleStatus
    from app.models.shift import Shift
    from app.models.transfer import StockTransfer, TransferStatus

    all_wh = db.query(Warehouse.id, Warehouse.name, Warehouse.is_active).filter(
        Warehouse.branch_id == branch.id).all()
    wh_ids = [w[0] for w in all_wh]
    active_wh = {w[0]: w[1] for w in all_wh if w[2] is not False}

    def _count(q) -> int:
        return int(q.scalar() or 0)

    open_shifts = _count(db.query(func.count(Shift.id)).filter(
        Shift.branch_id == branch.id, Shift.status == "open"))

    wallets = db.query(Wallet).filter(
        Wallet.branch_id == branch.id, Wallet.company_id == branch.company_id,
        Wallet.is_active == True,  # noqa: E712
    ).all()
    open_kassa = sum(1 for w in wallets if w.is_open)
    wallets_with_balance = [
        {"id": w.id, "name": w.name, "balance": float(w.balance or 0)}
        for w in wallets if (w.balance or 0) != 0
    ]

    stock = []
    if active_wh:
        rows = db.query(StockLevel.warehouse_id, func.count(StockLevel.id), func.sum(StockLevel.quantity)).filter(
            StockLevel.warehouse_id.in_(list(active_wh)), StockLevel.quantity != 0,
        ).group_by(StockLevel.warehouse_id).all()
        stock = [
            {"warehouse_id": wid, "name": active_wh[wid], "qty": float(qty or 0), "products": int(n)}
            for wid, n, qty in sorted(rows)
        ]

    active_users = 0 if reassign_users else len(_branch_user_ids(db, branch, exclude_user_id))

    open_orders = _count(db.query(func.count(Order.id)).filter(
        Order.branch_id == branch.id, Order.company_id == branch.company_id,
        Order.status.notin_([OrderStatus.delivered, OrderStatus.cancelled]),
    ))
    pending_sales = _count(db.query(func.count(Sale.id)).filter(
        Sale.status == SaleStatus.pending,
        or_(Sale.branch_id == branch.id,
            Sale.branch_id.is_(None) & Sale.warehouse_id.in_(wh_ids or [0])),
    ))

    pending_transfers = open_counts = open_production = open_pos = 0
    if wh_ids:
        pending_transfers = _count(db.query(func.count(StockTransfer.id)).filter(
            StockTransfer.status.in_([TransferStatus.pending, TransferStatus.in_transit]),
            or_(StockTransfer.from_warehouse_id.in_(wh_ids), StockTransfer.to_warehouse_id.in_(wh_ids)),
        ))
        open_counts = _count(db.query(func.count(InventoryCount.id)).filter(
            InventoryCount.status.in_([CountStatus.draft, CountStatus.in_progress]),
            InventoryCount.warehouse_id.in_(wh_ids),
        ))
        open_production = _count(db.query(func.count(ProductionOrder.id)).filter(
            ProductionOrder.status.in_([ProductionOrderStatus.draft, ProductionOrderStatus.in_progress]),
            or_(ProductionOrder.warehouse_id.in_(wh_ids), ProductionOrder.target_warehouse_id.in_(wh_ids)),
        ))
        open_pos = _count(db.query(func.count(PurchaseOrder.id)).filter(
            PurchaseOrder.status.in_([POStatus.draft, POStatus.sent, POStatus.partial]),
            PurchaseOrder.warehouse_id.in_(wh_ids),
        ))

    return {
        "open_shifts": open_shifts,
        "open_kassa": open_kassa,
        "wallets_with_balance": wallets_with_balance,
        "stock": stock,
        "active_users": active_users,
        "open_orders": open_orders,
        "pending_transfers": pending_transfers,
        "open_counts": open_counts,
        "open_production": open_production,
        "open_purchase_orders": open_pos,
        "pending_sales": pending_sales,
    }


def has_blockers(blockers: dict) -> bool:
    return any((len(v) if isinstance(v, list) else v) for v in blockers.values())


def clear_closed_fields(branch: Branch) -> None:
    branch.closed_at = None
    branch.closed_by = None
    branch.close_reason = None


def _reassign_users(db: Session, branch: Branch, target_id: int) -> int:
    """Filial xodimlarini `target_id` filialiga ko'chiradi (users, user_companies, user_branches)."""
    from app.models.user import User
    from app.models.user_branch import UserBranch
    from app.models.user_company import UserCompany

    ids = _branch_user_ids(db, branch)
    if not ids:
        return 0
    db.query(User).filter(User.id.in_(ids), User.branch_id == branch.id).update(
        {User.branch_id: target_id}, synchronize_session=False)
    db.query(UserCompany).filter(
        UserCompany.user_id.in_(ids), UserCompany.company_id == branch.company_id,
        UserCompany.branch_id == branch.id,
    ).update({UserCompany.branch_id: target_id}, synchronize_session=False)
    # Qo'shimcha filiallar: yangi filialda allaqachon bor bo'lsa eskisi o'chiriladi, bo'lmasa ko'chiriladi
    already = {r[0] for r in db.query(UserBranch.user_id).filter(
        UserBranch.branch_id == target_id, UserBranch.user_id.in_(ids)).all()}
    for ub in db.query(UserBranch).filter(UserBranch.branch_id == branch.id, UserBranch.user_id.in_(ids)).all():
        if ub.user_id in already:
            db.delete(ub)
        else:
            ub.branch_id = target_id
    db.flush()
    return len(ids)


def archive_branch(db: Session, branch: Branch, user, reason: Optional[str] = None,
                   reassign_to: Optional[int] = None, action: str = "ARCHIVE") -> dict:
    """Filialni arxivlaydi (`is_active=False`). Blokerlar bo'lsa `BranchCloseBlocked` — hech narsa o'zgarmaydi.

    - `closed_at/closed_by/close_reason` yoziladi;
    - nol qoldiqli omborlar va nol balansli yopiq kassalar nofaol bo'ladi;
    - `reassign_to` berilsa faol xodimlar shu (faol, shu korxona) filialga ko'chiriladi.
    `action` — audit yozuvi nomi (DELETE /branches/{id} eski "DELETE" nomini saqlaydi).
    Commit chaqiruvchida. Qaytaradi: {deactivated_warehouses, deactivated_wallets, moved_users}."""
    from datetime import datetime, timezone

    from app.core.audit import log_action
    from app.models.moliya import Wallet

    if reassign_to is not None:
        if reassign_to == branch.id:
            raise HTTPException(status_code=400, detail=BRANCH_REASSIGN_SELF)
        get_active_branch(db, reassign_to, branch.company_id)   # 404 / 400

    blockers = branch_close_blockers(
        db, branch, reassign_users=reassign_to is not None, exclude_user_id=getattr(user, "id", None))
    if has_blockers(blockers):
        raise BranchCloseBlocked(blockers)

    moved = _reassign_users(db, branch, reassign_to) if reassign_to is not None else 0

    deact_wh = []
    for wh in db.query(Warehouse).filter(Warehouse.branch_id == branch.id, Warehouse.is_active == True):  # noqa: E712
        wh.is_active = False
        wh.is_default = False
        deact_wh.append(wh.id)
    deact_wallets = []
    for w in db.query(Wallet).filter(
        Wallet.branch_id == branch.id, Wallet.company_id == branch.company_id,
        Wallet.is_active == True,  # noqa: E712
    ):
        if not w.is_open and (w.balance or 0) == 0:
            w.is_active = False
            deact_wallets.append(w.id)

    old_active = branch.is_active
    branch.is_active = False
    branch.closed_at = datetime.now(timezone.utc)
    branch.closed_by = getattr(user, "id", None)
    branch.close_reason = (reason or "").strip() or None
    db.flush()
    log_action(
        db, action, "branch", branch.id, user_id=getattr(user, "id", None),
        old_values={"is_active": old_active},
        new_values={
            "is_active": False, "reason": branch.close_reason, "reassigned_to": reassign_to,
            "moved_users": moved, "deactivated_warehouses": deact_wh, "deactivated_wallets": deact_wallets,
        },
        company_id=branch.company_id, branch_id=branch.id,
    )
    return {"deactivated_warehouses": deact_wh, "deactivated_wallets": deact_wallets, "moved_users": moved}


def reopen_branch(db: Session, branch: Branch, user) -> dict:
    """Nofaol filialni qayta faollashtiradi: tarif limiti (403), `is_active=True`, `closed_*` tozalanadi.
    Omborlar/kassalar AVTOMATIK yoqilmaydi — ularning ro'yxati qaytariladi. Commit chaqiruvchida."""
    from app.core.audit import log_action
    from app.models.moliya import Wallet
    from app.utils.tariff_check import check_branch_limit

    if branch.is_active:
        raise HTTPException(status_code=400, detail=BRANCH_ALREADY_ACTIVE)
    check_branch_limit(db, branch.company_id, user, exclude_branch_id=branch.id)
    branch.is_active = True
    clear_closed_fields(branch)
    db.flush()
    inactive_wh = [
        {"id": w.id, "name": w.name}
        for w in db.query(Warehouse).filter(Warehouse.branch_id == branch.id, Warehouse.is_active == False)  # noqa: E712
    ]
    inactive_wallets = [
        {"id": w.id, "name": w.name}
        for w in db.query(Wallet).filter(
            Wallet.branch_id == branch.id, Wallet.company_id == branch.company_id,
            Wallet.is_active == False,  # noqa: E712
        )
    ]
    log_action(
        db, "REOPEN", "branch", branch.id, user_id=getattr(user, "id", None),
        old_values={"is_active": False}, new_values={"is_active": True},
        company_id=branch.company_id, branch_id=branch.id,
    )
    return {"inactive_warehouses": inactive_wh, "inactive_wallets": inactive_wallets}
