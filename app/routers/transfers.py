from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.transfer import (
    InTransitRow,
    TransferCancel,
    TransferCreate,
    TransferItemOut,
    TransferListOut,
    TransferOut,
    TransferReceive,
    TransferUpdate,
)
from app.services.transfer_service import (
    _is_two_step_doc,
    cancel_transfer_flow,
    confirm_transfer,
    create_transfer,
    delete_transfer,
    in_transit_summary,
    receive_transfer,
    send_transfer,
    transfer_flags,
    update_transfer,
)

router = APIRouter(prefix="/transfers", tags=["Stock Transfers"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _build_transfer_out(t: StockTransfer, user: Optional[User] = None, ctx: Optional[BranchContext] = None) -> TransferOut:
    fw, tw = t.from_warehouse, t.to_warehouse
    flags = transfer_flags(user, ctx, t) if user is not None else {}
    return TransferOut(
        id=t.id,
        number=t.number,
        from_warehouse_id=t.from_warehouse_id,
        from_warehouse_name=fw.name,
        to_warehouse_id=t.to_warehouse_id,
        to_warehouse_name=tw.name,
        status=t.status,
        note=t.note,
        created_by=t.created_by,
        creator_name=t.creator.name,
        confirmed_by=t.confirmed_by,
        confirmed_at=t.confirmed_at,
        created_at=t.created_at,
        sent_by=t.sent_by,
        sender_name=t.sender.name if t.sender else None,
        sent_at=t.sent_at,
        confirmer_name=t.confirmer.name if t.confirmer else None,
        cancel_reason=t.cancel_reason,
        from_branch_id=fw.branch_id,
        from_branch_name=fw.branch.name if fw.branch else None,
        to_branch_id=tw.branch_id,
        to_branch_name=tw.branch.name if tw.branch else None,
        two_step=_is_two_step_doc(t) or (
            t.status == TransferStatus.pending and bool(fw.branch_id and tw.branch_id and fw.branch_id != tw.branch_id)
        ),
        can_send=flags.get("can_send", False),
        can_receive=flags.get("can_receive", False),
        can_cancel=flags.get("can_cancel", False),
        items=[
            TransferItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                variant_id=item.variant_id,
                variant_name=item.variant.name if item.variant else None,
                target_product_id=item.target_product_id,
                target_product_name=item.target_product.name if item.target_product else None,
                quantity=item.quantity,
                qty_sent=item.qty_sent,
                qty_received=item.qty_received,
                discrepancy_reason=item.discrepancy_reason,
            )
            for item in t.items
        ],
    )


def _load_transfer(db: Session, transfer_id: int, company_id: Optional[int] = None) -> StockTransfer:
    q = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.from_warehouse).joinedload(Warehouse.branch),
            joinedload(StockTransfer.to_warehouse).joinedload(Warehouse.branch),
            joinedload(StockTransfer.creator),
            joinedload(StockTransfer.sender),
            joinedload(StockTransfer.confirmer),
            joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
            joinedload(StockTransfer.items).joinedload(StockTransferItem.target_product),
            joinedload(StockTransfer.items).joinedload(StockTransferItem.variant),
        )
        .filter(StockTransfer.id == transfer_id)
        .populate_existing()
    )
    if company_id is not None:
        # Ikkala ombor ham korxonaga tegishli bo'lishi shart (subquery, ro'yxat materializatsiya qilinmaydi)
        company_wh_ids = db.query(Warehouse.id).filter(Warehouse.company_id == company_id)
        q = q.filter(
            StockTransfer.from_warehouse_id.in_(company_wh_ids),
            StockTransfer.to_warehouse_id.in_(company_wh_ids),
        )
    return q.first()


def _company_scope(current_user: User) -> Optional[int]:
    """super_admin uchun None (filtr yo'q), qolganlar uchun o'z korxonasi"""
    return None if current_user.role == UserRole.super_admin else current_user.company_id


def _my_branch_ids(current_user: User, ctx: BranchContext) -> Optional[set]:
    """Foydalanuvchi filiallari (yo'nalish hisobi uchun): kontekst doirasi, bo'lmasa biriktirilgan filial."""
    ids = ctx.scope_ids()
    if ids is not None:
        return set(ids)
    if current_user.branch_id:
        return {current_user.branch_id}
    return None


def _direction(t: StockTransfer, my_ids: Optional[set]) -> Optional[str]:
    if not my_ids:
        return None
    src = t.from_warehouse.branch_id in my_ids
    dst = t.to_warehouse.branch_id in my_ids
    if src and dst:
        return "internal"
    if dst:
        return "incoming"
    if src:
        return "outgoing"
    return None


@router.get("", response_model=List[TransferListOut])
def list_transfers(
    status: Optional[TransferStatus] = Query(None),
    from_warehouse_id: Optional[int] = Query(None),
    to_warehouse_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(incoming|outgoing)$"),
    branch_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    q = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.from_warehouse).joinedload(Warehouse.branch),
            joinedload(StockTransfer.to_warehouse).joinedload(Warehouse.branch),
            selectinload(StockTransfer.items),
        )
        .order_by(StockTransfer.created_at.desc(), StockTransfer.id.desc())
    )
    company_id = _company_scope(current_user)
    if company_id is not None:
        # Chiquvchi VA kiruvchi transferlar: ikkala ombor korxonaniki (begona korxona yozuvi hech qachon qaytmaydi)
        company_wh_ids = db.query(Warehouse.id).filter(Warehouse.company_id == company_id)
        q = q.filter(
            StockTransfer.from_warehouse_id.in_(company_wh_ids),
            StockTransfer.to_warehouse_id.in_(company_wh_ids),
        )
    my_ids = _my_branch_ids(current_user, ctx)
    if direction and my_ids:
        mine = db.query(Warehouse.id).filter(Warehouse.branch_id.in_(list(my_ids)))
        if company_id is not None:
            mine = mine.filter(Warehouse.company_id == company_id)
        if direction == "incoming":
            q = q.filter(StockTransfer.to_warehouse_id.in_(mine))
        else:
            q = q.filter(StockTransfer.from_warehouse_id.in_(mine))
    if branch_id:
        br_wh = db.query(Warehouse.id).filter(Warehouse.branch_id == branch_id)
        if company_id is not None:
            br_wh = br_wh.filter(Warehouse.company_id == company_id)
        q = q.filter(or_(
            StockTransfer.from_warehouse_id.in_(br_wh),
            StockTransfer.to_warehouse_id.in_(br_wh),
        ))
    if status:
        q = q.filter(StockTransfer.status == status)
    if from_warehouse_id:
        q = q.filter(StockTransfer.from_warehouse_id == from_warehouse_id)
    if to_warehouse_id:
        q = q.filter(StockTransfer.to_warehouse_id == to_warehouse_id)
    if user_id:
        q = q.filter(StockTransfer.created_by == user_id)
    if date_from:
        q = q.filter(StockTransfer.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(StockTransfer.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))

    transfers = q.offset(skip).limit(limit).all()
    out = []
    for t in transfers:
        flags = transfer_flags(current_user, ctx, t)
        out.append(TransferListOut(
            id=t.id,
            number=t.number,
            from_warehouse_id=t.from_warehouse_id,
            to_warehouse_id=t.to_warehouse_id,
            from_warehouse_name=t.from_warehouse.name,
            to_warehouse_name=t.to_warehouse.name,
            from_branch_name=t.from_warehouse.branch.name if t.from_warehouse.branch else None,
            to_branch_name=t.to_warehouse.branch.name if t.to_warehouse.branch else None,
            status=t.status,
            created_at=t.created_at,
            total_qty=sum((i.quantity or 0 for i in t.items), 0),
            direction=_direction(t, my_ids),
            **flags,
        ))
    return out


@router.get("/in-transit-summary", response_model=List[InTransitRow])
def get_in_transit_summary(
    warehouse_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Manzil ombor uchun yo'ldagi (in_transit) tovarlar: [{product_id, variant_id, qty}]. Faqat o'qish."""
    return in_transit_summary(db, warehouse_id, _company_scope(current_user))


@router.post("", response_model=TransferOut)
def create_new_transfer(
    data: TransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = _company_scope(current_user)
    # Korxona va filial (manba ombor) tekshiruvi servis ichida, commitdan OLDIN bajariladi
    transfer = create_transfer(db, data, current_user.id, cid, user=current_user, ctx=ctx)
    db.commit()
    t = _load_transfer(db, transfer.id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)


@router.get("/{transfer_id}", response_model=TransferOut)
def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = _company_scope(current_user)
    t = _load_transfer(db, transfer_id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)


@router.post("/{transfer_id}/send", response_model=TransferOut)
def send_transfer_endpoint(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """pending → in_transit: faqat manba ombor filialidan (403), holat mos emas — 409, qoldiq yetmasa — 400"""
    cid = _company_scope(current_user)
    send_transfer(db, transfer_id, current_user, ctx)
    db.commit()
    t = _load_transfer(db, transfer_id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)


@router.post("/{transfer_id}/receive", response_model=TransferOut)
def receive_transfer_endpoint(
    transfer_id: int,
    payload: Optional[TransferReceive] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """in_transit → received: faqat manzil ombor filialidan (403); haqiqiy miqdor va kamomad sababi bilan"""
    cid = _company_scope(current_user)
    receive_transfer(db, transfer_id, payload, current_user, ctx)
    db.commit()
    t = _load_transfer(db, transfer_id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)


@router.post("/{transfer_id}/confirm", response_model=TransferOut)
def confirm_transfer_endpoint(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Eski nom: /receive ga alias (hammasi to'liq qabul). pending bo'lsa — 400 "avval yuboring"."""
    cid = _company_scope(current_user)
    confirm_transfer(db, transfer_id, current_user, ctx)
    db.commit()
    t = _load_transfer(db, transfer_id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)


@router.post("/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: int,
    payload: Optional[TransferCancel] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Holatga qarab bekor qilish: pending — qoldiqsiz; in_transit — qty_sent manbaga qaytadi;
    received — faqat admin/direktor va manzilda yetarli qoldiq bo'lsa (aks holda 400).
    T1.19: asl StockMovement qatorlari saqlanadi, TRANSFER_CANCEL auditga yoziladi."""
    t = cancel_transfer_flow(db, transfer_id, current_user, payload.reason if payload else None, ctx)
    db.commit()
    return {"message": "Transfer bekor qilindi va qoldiqlar qaytarildi", "number": t.number, "status": "cancelled"}


@router.delete("/{transfer_id}")
def remove_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Transfer'ni bekor qilish (soft-delete): qoldiqlar qaytariladi, harakatlar tarixi saqlanadi (cancel bilan bir xil).
    Ikki bosqichli transfer yo'lda/qabul qilingan bo'lsa — 409 (POST /cancel ishlating)."""
    delete_transfer(db=db, transfer_id=transfer_id, current_user=current_user)
    return {"message": "Transfer bekor qilindi"}


@router.put("/{transfer_id}", response_model=TransferOut)
def transfer_update(
    transfer_id: int,
    data: TransferUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = _company_scope(current_user)
    transfer = update_transfer(db, transfer_id, data, current_user.id, cid)
    db.commit()
    t = _load_transfer(db, transfer.id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t, current_user, ctx)
