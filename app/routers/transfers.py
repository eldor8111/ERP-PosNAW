from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.transfer import TransferCreate, TransferListOut, TransferOut, TransferItemOut
from app.services.transfer_service import confirm_transfer, create_transfer, delete_transfer

router = APIRouter(prefix="/transfers", tags=["Stock Transfers"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _build_transfer_out(t: StockTransfer) -> TransferOut:
    return TransferOut(
        id=t.id,
        number=t.number,
        from_warehouse_id=t.from_warehouse_id,
        from_warehouse_name=t.from_warehouse.name,
        to_warehouse_id=t.to_warehouse_id,
        to_warehouse_name=t.to_warehouse.name,
        status=t.status,
        note=t.note,
        created_by=t.created_by,
        creator_name=t.creator.name,
        confirmed_by=t.confirmed_by,
        confirmed_at=t.confirmed_at,
        created_at=t.created_at,
        items=[
            TransferItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                quantity=item.quantity,
            )
            for item in t.items
        ],
    )


def _load_transfer(db: Session, transfer_id: int, company_id: Optional[int] = None) -> StockTransfer:
    q = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.from_warehouse),
            joinedload(StockTransfer.to_warehouse),
            joinedload(StockTransfer.creator),
            joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
        )
        .filter(StockTransfer.id == transfer_id)
    )
    if company_id is not None:
        company_wh_ids = [
            wh[0] for wh in db.query(Warehouse.id).filter(Warehouse.company_id == company_id).all()
        ]
        q = q.filter(StockTransfer.from_warehouse_id.in_(company_wh_ids))
    return q.first()


from datetime import date, datetime, timedelta

@router.get("", response_model=List[TransferListOut])
def list_transfers(
    status: Optional[TransferStatus] = Query(None),
    from_warehouse_id: Optional[int] = Query(None),
    to_warehouse_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.from_warehouse),
            joinedload(StockTransfer.to_warehouse),
        )
        .order_by(StockTransfer.created_at.desc())
    )
    if current_user.role != UserRole.super_admin:
        company_wh_ids = [
            wh[0] for wh in db.query(Warehouse.id).filter(Warehouse.company_id == current_user.company_id).all()
        ]
        q = q.filter(StockTransfer.from_warehouse_id.in_(company_wh_ids))
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
    return [
        TransferListOut(
            id=t.id,
            number=t.number,
            from_warehouse_name=t.from_warehouse.name,
            to_warehouse_name=t.to_warehouse.name,
            status=t.status,
            created_at=t.created_at,
        )
        for t in transfers
    ]


@router.post("", response_model=TransferOut)
def create_new_transfer(
    data: TransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    transfer = create_transfer(db, data, current_user.id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    t = _load_transfer(db, transfer.id, cid)
    return _build_transfer_out(t)


@router.get("/{transfer_id}", response_model=TransferOut)
def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    t = _load_transfer(db, transfer_id, cid)
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return _build_transfer_out(t)


@router.post("/{transfer_id}/confirm", response_model=TransferOut)
def confirm_transfer_endpoint(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    confirm_transfer(db, transfer_id, current_user.id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    t = _load_transfer(db, transfer_id, cid)
    return _build_transfer_out(t)


@router.post("/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    tq = db.query(StockTransfer).filter(StockTransfer.id == transfer_id)
    if current_user.role != UserRole.super_admin:
        company_wh_ids = [
            wh[0] for wh in db.query(Warehouse.id).filter(Warehouse.company_id == current_user.company_id).all()
        ]
        tq = tq.filter(StockTransfer.from_warehouse_id.in_(company_wh_ids))
    t = tq.first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    if t.status != TransferStatus.pending:
        raise HTTPException(status_code=400, detail="Faqat kutayotgan transferni bekor qilish mumkin")
    t.status = TransferStatus.cancelled
    db.commit()
    return {"message": "Transfer bekor qilindi", "number": t.number}


@router.delete("/{transfer_id}")
def remove_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Transfer'ni o'chirish va mahsulot qoldiqlarini qaytarish"""
    delete_transfer(db=db, transfer_id=transfer_id, current_user=current_user)
    return {"message": "Transfer o'chirildi va qoldiqlar qaytarildi"}
