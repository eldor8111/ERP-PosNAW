from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.models.product import Product
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    StockAdjustRequest,
    StockLevelOut,
    StockMovementOut,
    StockReceiveRequest,
    ChiqimBatchRequest,
    ChiqimDocumentOut,
    ChiqimDetailOut,
    SupplierReturnRequest
)
from app.services.inventory_service import (
    adjust_stock, 
    receive_stock, 
    create_chiqim_batch, 
    delete_chiqim_batch
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])

WAREHOUSE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


@router.get("/stock", response_model=List[StockLevelOut])
def get_stock_levels(
    low_stock_only: bool = Query(False, description="Faqat kam qoldiqlilarni ko'rsatish"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockLevel)
        .join(Product)
        .filter(Product.is_deleted == False)
        .options(joinedload(StockLevel.product))
    )
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )

    stocks = q.offset(skip).limit(limit).all()

    result = []
    for s in stocks:
        is_low = s.quantity <= s.product.min_stock
        if low_stock_only and not is_low:
            continue
        result.append(
            StockLevelOut(
                product_id=s.product_id,
                product_name=s.product.name,
                product_sku=s.product.sku,
                product_barcode=s.product.barcode,
                quantity=s.quantity,
                min_stock=s.product.min_stock,
                is_low_stock=is_low,
                updated_at=s.updated_at,
            )
        )
    return result


@router.get("/low-stock-count")
def get_low_stock_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    count = (
        db.query(func.count(StockLevel.id))
        .join(Product, StockLevel.product_id == Product.id)
        .filter(
            Product.is_deleted == False,
            Product.company_id == current_user.company_id,
            StockLevel.quantity <= Product.min_stock,
        )
        .scalar() or 0
    )
    return {"count": count}


@router.get("/movements", response_model=List[StockMovementOut])
def get_movements(
    product_id: Optional[int] = Query(None),
    type: Optional[MovementType] = Query(None),
    reference_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product))
        .order_by(StockMovement.created_at.desc())
    )
    q = q.filter(Product.company_id == current_user.company_id)

    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if type:
        q = q.filter(StockMovement.type == type)
    if reference_type:
        q = q.filter(StockMovement.reference_type == reference_type)

    movements = q.offset(skip).limit(limit).all()

    return [
        StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name,
            type=m.type,
            qty_before=m.qty_before,
            qty_after=m.qty_after,
            quantity=m.quantity,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            created_at=m.created_at,
        )
        for m in movements
    ]


@router.post("/receive")
def receive_goods(
    data: StockReceiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    movements = []
    for item in data.items:
        m = receive_stock(
            db=db,
            product_id=item.product_id,
            quantity=item.quantity,
            user_id=current_user.id,
            reason=item.reason or data.note,
            reference_type="manual_receive",
            purchase_price=item.purchase_price,
            company_id=current_user.company_id if item.purchase_price is not None else None,
        )
        movements.append({"product_id": item.product_id, "qty_added": str(item.quantity), "new_qty": str(m.qty_after)})

    db.commit()
    return {"message": f"{len(movements)} ta mahsulot qabul qilindi", "details": movements}


@router.post("/return-to-supplier")
def return_to_supplier(
    data: SupplierReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    from app.models.supplier import Supplier
    from app.services.inventory_service import deduct_stock

    supplier = db.get(Supplier, data.supplier_id)
    if not supplier:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")

    total_return_value = Decimal("0")
    
    for item in data.items:
        if item.quantity <= 0:
            continue
            
        deduct_stock(
            db=db,
            product_id=item.product_id,
            quantity=item.quantity,
            user_id=current_user.id,
            reason=f"Ta'minotchiga qaytarish: {supplier.name}. {data.note or ''}".strip(),
            reference_type="return_to_supplier",
            reference_id=supplier.id,
            warehouse_id=data.warehouse_id
        )
        total_return_value += (item.quantity * item.unit_cost)

    # 1. Vazvrat summasi qarzdan chegiriladi (bizning qarzimiz kamayadi)
    supplier.debt_balance = float(supplier.debt_balance or 0) - float(total_return_value)

    # 2. Agar ta'minotchi pul qaytargan bo'lsa (kassaga kirim)
    if data.received_amount > 0 and data.wallet_id:
        from app.models.moliya import Transaction, Wallet
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            tx = Transaction(
                branch_id=current_user.branch_id,
                company_id=current_user.company_id,
                type="income",
                amount=data.received_amount,
                wallet_id=wallet.id,
                reference_type="return_to_supplier",
                reference_id=supplier.id,
                description=f"Ta'minotchidan vazvrat uchun pul qaytdi: {supplier.name}"
            )
            db.add(tx)
            wallet.balance = float(wallet.balance) + float(data.received_amount)
            
            # Agar naqd pul qaytib olingan bo'lsa, qarzimiz yana ko'payadi, chunki pulni oldik
            # Umuman olganda, Vazvrat (-) = Qarz kamayadi. Pul olsak (+) = Qarz yana oshadi, chunki tovar o'rniga pul berdi.
            supplier.debt_balance = float(supplier.debt_balance) + float(data.received_amount)

    db.commit()
    return {
        "message": "Vazvrat muvaffaqiyatli saqlandi",
        "total_value": str(total_return_value)
    }


@router.post("/chiqims")
def create_chiqim(
    data: ChiqimBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    ref_id = create_chiqim_batch(db, data.items, current_user.id, company_id=current_user.company_id)
    db.commit()
    return {"message": "Chiqim muvaffaqiyatli saqlandi", "reference_id": ref_id}


from datetime import date, datetime, timedelta

@router.get("/chiqims", response_model=List[ChiqimDocumentOut])
def get_chiqims(
    user_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockMovement)
        .join(Product)
        .filter(Product.company_id == current_user.company_id)
        .filter(StockMovement.reference_type == "chiqim")
    )
    if user_id:
        q = q.filter(StockMovement.user_id == user_id)
    if date_from:
        q = q.filter(StockMovement.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(StockMovement.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
        
    movements = q.order_by(StockMovement.created_at.desc()).all()

    # Group by reference_id
    groups = {}
    for m in movements:
        rid = m.reference_id
        if rid not in groups:
            groups[rid] = {
                "reference_id": rid,
                "created_at": m.created_at,
                "type_hints": set(),
                "doc_nums": set(),
                "reasons": set(),
                "total_qty": Decimal("0"),
                "item_count": 0,
                "user_name": m.user.full_name if m.user else None
            }
        
        g = groups[rid]
        g["total_qty"] += max(Decimal("0"), m.quantity)  # quantity holds the diff
        g["item_count"] += 1
        
        # Parse reason to extract type logic
        # format was: "TYPE | Hujjat: DOC | reason" or similar
        rparts = [p.strip() for p in (m.reason or "").split("|")]
        if len(rparts) >= 1 and rparts[0]:
            g["type_hints"].add(rparts[0])
        if len(rparts) >= 2 and rparts[1].startswith("Hujjat: "):
            g["doc_nums"].add(rparts[1].replace("Hujjat: ", ""))
        elif len(rparts) >= 2:
            g["reasons"].add(rparts[1])
        if len(rparts) >= 3:
            g["reasons"].add(rparts[2])

    grouped = []
    for g in sorted(groups.values(), key=lambda x: x["created_at"], reverse=True):
        grouped.append(ChiqimDocumentOut(
            reference_id=g["reference_id"],
            created_at=g["created_at"],
            type_hints=list(g["type_hints"]),
            doc_nums=list(g["doc_nums"]),
            reasons=list(g["reasons"]),
            total_qty=g["total_qty"],
            item_count=g["item_count"],
            user_name=g["user_name"]
        ))
    
    return grouped[skip : skip + limit]


@router.get("/chiqims/{id}", response_model=List[ChiqimDetailOut])
def get_chiqim_details(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    movements = (
        db.query(StockMovement)
        .join(Product)
        .filter(Product.company_id == current_user.company_id)
        .filter(StockMovement.reference_type == "chiqim", StockMovement.reference_id == id)
        .options(joinedload(StockMovement.product))
        .all()
    )

    out = []
    for m in movements:
        parts = [p.strip() for p in (m.reason or "").split("|")]
        ctype = parts[0] if len(parts) > 0 else "unknown"
        doc_num = None
        reason = None
        if len(parts) > 1:
            if parts[1].startswith("Hujjat: "):
                doc_num = parts[1].replace("Hujjat: ", "")
                if len(parts) > 2:
                    reason = parts[2]
            else:
                reason = parts[1]

        out.append(ChiqimDetailOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name,
            product_sku=m.product.sku,
            product_unit=m.product.unit or "dona",
            type=ctype,
            quantity=m.quantity,
            doc_num=doc_num,
            reason=reason
        ))
    return out


@router.delete("/chiqims/{id}")
def delete_chiqim(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    # Verify owner company
    m = db.query(StockMovement).join(Product).filter(
        StockMovement.reference_type == "chiqim",
        StockMovement.reference_id == id,
        Product.company_id == current_user.company_id
    ).first()

    if not m:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chiqim topilmadi")

    delete_chiqim_batch(db, id, current_user.id, company_id=current_user.company_id)
    db.commit()
    return {"message": "Chiqim muvaffaqiyatli bekor qilindi"}


@router.post("/adjust")
def adjust_stock_level(
    data: StockAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    m = adjust_stock(
        db=db,
        product_id=data.product_id,
        new_quantity=data.new_quantity,
        user_id=current_user.id,
        reason=data.reason,
    )
    db.commit()
    return {
        "message": "Qoldiq yangilandi",
        "product_id": data.product_id,
        "qty_before": str(m.qty_before),
        "qty_after": str(m.qty_after),
    }


@router.get("/warehouses")
def list_warehouses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wq = db.query(Warehouse).filter(Warehouse.is_active == True)
    wq = wq.filter(Warehouse.company_id == current_user.company_id)
    warehouses = wq.order_by(Warehouse.name).all()
    return [{"id": w.id, "name": w.name, "type": w.type} for w in warehouses]
