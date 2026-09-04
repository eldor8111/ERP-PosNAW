from datetime import datetime as dt
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import func
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

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
    ExpiringBatchOut,
    ChiqimDocumentOut,
    ChiqimDetailOut,
    SupplierReturnRequest, StockMovementUpdate, WriteOffExpiredRequest,
    CustomerReturnRequest
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
                variant_id=s.variant_id,
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
        search: Optional[str] = Query(None, description="Mahsulot nomi yoki SKU"),
        date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
        date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product), joinedload(StockMovement.user))
        .order_by(StockMovement.created_at.desc())
    )
    q = q.filter(Product.company_id == current_user.company_id)

    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if type:
        q = q.filter(StockMovement.type == type)
    if reference_type:
        if reference_type == "return_from_customer":
            q = q.filter(StockMovement.reference_type.in_(["return_from_customer", "sale_refund"]))
        else:
            q = q.filter(StockMovement.reference_type == reference_type)
    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%")) |
            (Product.sku.ilike(f"%{search}%"))
        )
    if date_from:
        try:
            df = dt.strptime(date_from, "%Y-%m-%d")
            q = q.filter(StockMovement.created_at >= df)
        except Exception:
            pass
    if date_to:
        try:
            dt2 = dt.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(StockMovement.created_at < dt2)
        except Exception:
            pass

    movements = q.offset(skip).limit(limit).all()

    # ── Kontragent nomlarini yig'ish ──────────────────────────────────────

    def _get_contragent(m: StockMovement) -> Optional[str]:
        if not m.reference_id:
            return None
        rt = m.reference_type or ""
        try:
            if rt == "purchase_order":
                row = db.execute(
                    sa_text(
                        "SELECT s.name FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id WHERE po.id=:id"),
                    {"id": m.reference_id}
                ).fetchone()
                return row[0] if row else None
            elif rt == "sale":
                row = db.execute(
                    sa_text("SELECT c.name FROM sales sa LEFT JOIN customers c ON sa.customer_id=c.id WHERE sa.id=:id"),
                    {"id": m.reference_id}
                ).fetchone()
                return row[0] if row else "Noma'lum mijoz"
            elif rt == "return_to_supplier":
                row = db.execute(
                    sa_text("SELECT name FROM suppliers WHERE id=:id"),
                    {"id": m.reference_id}
                ).fetchone()
                return row[0] if row else None
            elif rt in ("return_from_customer", "customer_return", "sale_refund"):
                row = db.execute(
                    sa_text("SELECT c.name FROM sales sa LEFT JOIN customers c ON sa.customer_id=c.id WHERE sa.id=:id"),
                    {"id": m.reference_id}
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None
        return None

    return [
        StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            variant_id=m.variant_id,
            product_name=m.product.name,
            product_sku=m.product.sku,
            product_unit=getattr(m.product, "unit", None),
            type=m.type,
            qty_before=m.qty_before,
            qty_after=m.qty_after,
            quantity=m.quantity,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            contragent_name=_get_contragent(m),
            user_name=m.user.name if m.user else None,
            created_at=m.created_at,
        )
        for m in movements
    ]


@router.get("/movements/{movement_id}", response_model=StockMovementOut)
def get_movement(
        movement_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """Bitta StockMovement ma'lumotini olish"""
    m = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product), joinedload(StockMovement.user))
        .filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Harakat topilmadi")
    return StockMovementOut(
        id=m.id,
        product_id=m.product_id,
        variant_id=m.variant_id,
        product_name=m.product.name,
        product_sku=m.product.sku,
        product_unit=getattr(m.product, "unit", None),
        type=m.type,
        qty_before=m.qty_before,
        qty_after=m.qty_after,
        quantity=m.quantity,
        reference_type=m.reference_type,
        reference_id=m.reference_id,
        reason=m.reason,
        contragent_name=None,
        user_name=m.user.name if m.user else None,
        created_at=m.created_at,
    )


@router.delete("/movements/{movement_id}")
def delete_return_movement(
        movement_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """
    Qaytaruvni bekor qilish:
    - return_from_customer → stok kamayadi, mijoz qarzi + kassa orqaga qaytadi
    - sale_refund          → stok kamayadi (avvalgi sotuv logikasi)
    - return_to_supplier   → stok qaytadi, tranzaksiyalar bekor qilinadi
    """
    from app.models.moliya import Transaction, Wallet
    from app.models.supplier import Supplier
    from app.models.customer import Customer

    m = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product))
        .filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Harakat topilmadi")

    rt = m.reference_type or ""
    qty = Decimal(str(m.quantity))

    # ── 1. MIJOZDAN QAYTARISH BEKOR (return_from_customer) ─────────────────
    if rt == "return_from_customer":
        # 1a. Stokni orqaga kamaytir (omborga kelgan tovar yana chiqariladi)
        wh_id = m.warehouse_id if hasattr(m, 'warehouse_id') else None
        stock_q = db.query(StockLevel).filter(StockLevel.product_id == m.product_id)
        if wh_id:
            stock_q = stock_q.filter(StockLevel.warehouse_id == wh_id)
        stock = stock_q.first()
        if stock and stock.quantity >= qty:
            qty_before = stock.quantity
            stock.quantity -= qty
            revert_mov = StockMovement(
                product_id=m.product_id,
                warehouse_id=wh_id,
                type=MovementType.OUT,
                qty_before=qty_before,
                qty_after=stock.quantity,
                quantity=qty,
                reference_type="return_revert",
                reference_id=m.id,
                user_id=current_user.id,
                reason=f"Mijozdan qaytarish bekor qilindi (asl ID: {m.id})",
            )
            db.add(revert_mov)

        # 1b. Tegishli tranzaksiyalarni orqaga qaytarish (qarz + kassa)
        txs = db.query(Transaction).filter(
            Transaction.reference_type == "return_from_customer",
            Transaction.reference_id == m.id,
        ).all()
        for tx in txs:
            wallet = db.get(Wallet, tx.wallet_id)
            if wallet:
                # Chiqim tranzaksiya edi (kassadan pul chiqdi), endi orqaga qaytaramiz
                if tx.type == "expense":
                    wallet.balance = Decimal(str(wallet.balance)) + Decimal(str(tx.amount))
                else:
                    wallet.balance = Decimal(str(wallet.balance)) - Decimal(str(tx.amount))
            db.delete(tx)

        # 1c. Mijoz qarz balansini tiklash
        #     Qaytarish vaqtida: debt → qarz kamaydi, cash/card → kassa kamaydi
        #     Bekor qilganda: debt → qarz oshadi, cash/card → (tranzaksiya yuqorida bekor qilindi)
        if m.reference_id:  # reference_id = customer_id (return_from_customer da)
            customer = db.get(Customer, m.reference_id)
            if customer:
                # m.reason dan payment_type ni o'qiymiz
                reason_txt = m.reason or ""
                if "qarzga" in reason_txt.lower() or "debt" in reason_txt.lower():
                    # Qarzga yopilgan edi, endi qarzni qaytaramiz
                    total_val = Decimal(str(m.quantity)) * Decimal(str(getattr(m, 'unit_price', 0) or 0))
                    # total_val ni reason dan o'qishga harakat qilamiz
                    import re
                    match = re.search(r'summa:(\d+\.?\d*)', reason_txt)
                    if match:
                        total_val = Decimal(match.group(1))
                    # Eski mijozlar uchun: debt_balances null bo'lsa, debt_balance dan ko'chiramiz
                    if not customer.debt_balances:
                        if float(customer.debt_balance or 0) > 0:
                            customer.debt_balances = {"UZS": float(customer.debt_balance)}
                        else:
                            customer.debt_balances = {}

                    curr_uzs = float(customer.debt_balances.get("UZS", 0))
                    customer.debt_balances["UZS"] = curr_uzs + float(total_val)
                    customer.debt_balance = float(customer.debt_balance or 0) + float(total_val)
                    flag_modified(customer, "debt_balances")

    # ── 2. SOTUV REFUNDI BEKOR (sale_refund – eski logika) ─────────────────
    elif rt == "sale_refund":
        stock = db.query(StockLevel).filter(StockLevel.product_id == m.product_id).first()
        if stock and stock.quantity >= qty:
            qty_before = stock.quantity
            stock.quantity -= qty
            revert_mov = StockMovement(
                product_id=m.product_id,
                type=MovementType.OUT,
                qty_before=qty_before,
                qty_after=stock.quantity,
                quantity=qty,
                reference_type="return_revert",
                reference_id=m.id,
                user_id=current_user.id,
                reason=f"Qaytaruv bekor qilindi (asl harakat ID: {m.id})",
            )
            db.add(revert_mov)

    # ── 3. TA'MINOTCHIGA QAYTARISH BEKOR ───────────────────────────────────
    elif rt == "return_to_supplier":
        stock = db.query(StockLevel).filter(StockLevel.product_id == m.product_id).first()
        qty_before = stock.quantity if stock else Decimal("0")
        if not stock:
            stock = StockLevel(product_id=m.product_id, warehouse_id=None, quantity=Decimal("0"))
            db.add(stock)
            db.flush()
        stock.quantity += qty
        revert_mov = StockMovement(
            product_id=m.product_id,
            type=MovementType.IN,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=qty,
            reference_type="return_revert",
            reference_id=m.id,
            user_id=current_user.id,
            reason=f"Ta'minotchi qaytaruvi bekor qilindi (asl harakat ID: {m.id})",
        )
        db.add(revert_mov)
        if m.reference_id:
            supplier = db.get(Supplier, m.reference_id)
            if supplier:
                supplier.debt_balance = float(supplier.debt_balance or 0) + float(qty)
        txs = db.query(Transaction).filter(
            Transaction.reference_type == "return_to_supplier",
            Transaction.reference_id == m.reference_id,
        ).all()
        for tx in txs:
            wallet = db.get(Wallet, tx.wallet_id)
            if wallet:
                if tx.type == "income":
                    wallet.balance = float(wallet.balance) - float(tx.amount)
                else:
                    wallet.balance = float(wallet.balance) + float(tx.amount)
            db.delete(tx)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Bu turdagi harakatni ({rt}) bekor qilish qo'llab-quvvatlanmaydi"
        )

    db.delete(m)
    db.commit()
    return {"message": "Qaytaruv muvaffaqiyatli bekor qilindi"}


@router.put("/{movement_id}/movements", response_model=StockMovementOut)
def update_movement(
        movement_id: int,
        movement_data: StockMovementUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES))
):
    movement = (
        db.query(StockMovement).join(Product, Product.id == StockMovement.product_id).filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id).first()
    )
    if not movement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ombor harakati topilmadi"
        )
    update_dict = movement_data.model_dump(exclude_unset=True)
    for  key, value in update_dict.items():
        setattr(movement, key, value)

    db.commit()
    db.refresh(movement)

    return movement

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
            variant_id=item.variant_id,
            expiry_date=item.expiry_date,
        )
        movements.append({"product_id": item.product_id, "variant_id": item.variant_id, "qty_added": str(item.quantity), "new_qty": str(m.qty_after)})

    db.commit()
    return {"message": f"{len(movements)} ta mahsulot qabul qilindi", "details": movements}


@router.post("/return-from-customer")
def return_from_customer(
        data: CustomerReturnRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """
    Mijozdan mustaqil qaytarish operatsiyasi.
    - Sotuvlar tarixiga ta'sir qilmaydi
    - Operatsiyalar → Qaytarishlar da ko'rinadi
    - O'chirilganda stok + qarz/kassa orqaga qaytadi
    """
    from app.models.customer import Customer
    from app.models.moliya import Transaction, Wallet
    from app.services.inventory_service import receive_stock as _receive_stock

    customer = None
    if data.customer_id:
        customer = db.get(Customer, data.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    total_amount = sum(Decimal(str(i.quantity)) * Decimal(str(i.unit_price)) for i in data.items)
    movements_created = []

    for item in data.items:
        if item.quantity <= 0:
            continue
        qty = Decimal(str(item.quantity))

        # Stokni oshiramiz (omborga kirim)
        stock_q = db.query(StockLevel).filter(
            StockLevel.product_id == item.product_id,
            StockLevel.warehouse_id == data.warehouse_id,
        )
        stock = stock_q.first()
        if not stock:
            stock = StockLevel(
                product_id=item.product_id,
                warehouse_id=data.warehouse_id,
                quantity=Decimal("0")
            )
            db.add(stock)
            db.flush()

        qty_before = stock.quantity
        stock.quantity += qty

        # payment_type ni reason ga saqlaymiz (delete da orqaga qaytarish uchun)
        pay_info = f"debt" if data.payment_type == "debt" else data.payment_type
        item_total = qty * Decimal(str(item.unit_price))
        cust_name = customer.name if customer else "Noma'lum xaridor"
        reason_text = (
            f"Qisman qaytarish: {cust_name}. "
            f"payment:{pay_info}. summa:{item_total}. "
            f"{data.note or ''}".strip()
        )

        mov = StockMovement(
            product_id=item.product_id,
            variant_id=item.variant_id,
            warehouse_id=data.warehouse_id,
            type=MovementType.IN,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=qty,
            reference_type="return_from_customer",
            reference_id=customer.id if customer else None,   # mijoz ID saqlanadi yoki None
            user_id=current_user.id,
            reason=reason_text,
        )
        db.add(mov)
        db.flush()  # ID olish uchun
        movements_created.append(mov)

    # ── To'lov turini qayta ishlash ─────────────────────────────────────────
    if data.payment_type == "debt":
        # Mijoz qarzi kamayadi (biz unga pul qaytaramiz – qarz pasayadi)
        if customer:
            # Eski mijozlar uchun: debt_balances null bo'lsa, debt_balance dan ko'chiramiz
            if not customer.debt_balances:
                if float(customer.debt_balance or 0) > 0:
                    legacy_curr = (getattr(customer, 'debt_currency', 'UZS') or 'UZS').strip().upper() or 'UZS'
                    customer.debt_balances = {legacy_curr: float(customer.debt_balance)}
                else:
                    customer.debt_balances = {}

            # UZS qarzidan kamaytiramiz
            curr_uzs_debt = float(customer.debt_balances.get("UZS", 0))
            customer.debt_balances["UZS"] = max(0.0, curr_uzs_debt - float(total_amount))
            # Umumiy debt_balance ham kamaytiramiz
            customer.debt_balance = max(0.0, float(customer.debt_balance or 0) - float(total_amount))
            flag_modified(customer, "debt_balances")

        # Har bir movement uchun Transaction yozish (bekor qilish vaqtida topish uchun)
        for mov in movements_created:
            item_total = mov.quantity * Decimal(str(
                next((i.unit_price for i in data.items if i.product_id == mov.product_id), 0)
            ))
            cust_name = customer.name if customer else "Noma'lum"
            tx = Transaction(
                branch_id=current_user.branch_id,
                company_id=current_user.company_id,
                type="expense",          # Bizdan pul chiqdi (qarz hisobida)
                amount=float(item_total),
                wallet_id=None,
                reference_type="return_from_customer",
                reference_id=mov.id,
                description=f"Mijozdan qaytarish (qarzga): {cust_name}"
            )
            db.add(tx)

    elif data.payment_type in ("cash", "card", "mixed"):
        # Kassadan pul chiqadi (mijozga qaytaramiz)
        if data.wallet_id:
            wallet = db.get(Wallet, data.wallet_id)
            if not wallet:
                raise HTTPException(status_code=404, detail="Kassa topilmadi")

            paid_total = Decimal(str(data.paid_cash)) + Decimal(str(data.paid_card))
            if paid_total <= 0:
                paid_total = total_amount

            wallet.balance = Decimal(str(wallet.balance)) - paid_total
            if wallet.balance < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Kassada yetarli mablag' yo'q. Balans: {wallet.balance + paid_total}"
                )

            # Tranzaksiya (kassadan chiqim)
            for mov in movements_created:
                item_total = mov.quantity * Decimal(str(
                    next((i.unit_price for i in data.items if i.product_id == mov.product_id), 0)
                ))
                cust_name = customer.name if customer else "Noma'lum"
                tx = Transaction(
                    branch_id=current_user.branch_id,
                    company_id=current_user.company_id,
                    type="expense",
                    amount=float(item_total),
                    wallet_id=wallet.id,
                    reference_type="return_from_customer",
                    reference_id=mov.id,
                    description=f"Mijozdan qaytarish ({data.payment_type}): {cust_name}"
                )
                db.add(tx)

    db.commit()
    return {
        "message": "Mijozdan qaytarish muvaffaqiyatli saqlandi",
        "total_amount": str(total_amount),
        "items_count": len(movements_created)
    }


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
            warehouse_id=data.warehouse_id,
            variant_id=item.variant_id
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
    ref_id = create_chiqim_batch(db, data.items, current_user.id, company_id=current_user.company_id,
                                 warehouse_id=data.warehouse_id)
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
                "user_name": m.user.name if m.user else None
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

    return grouped[skip: skip + limit]


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
            variant_id=m.variant_id,
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
        variant_id=data.variant_id,
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
    if current_user.branch_id:
        wq = wq.filter(Warehouse.branch_id == current_user.branch_id)
    warehouses = wq.order_by(Warehouse.name).all()
    return [{"id": w.id, "name": w.name, "type": w.type} for w in warehouses]


@router.get("/expiring-batches", response_model=List[ExpiringBatchOut])
def get_expiring_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from datetime import date
    from app.models.category import Category
    from app.models.product_variant import ProductVariant
    from app.models.batch import Batch
    
    today_date = date.today()
    
    batches = db.query(Batch, Product.name, ProductVariant.name)\
        .join(Product, Product.id == Batch.product_id)\
        .join(Category, Category.id == Product.category_id)\
        .outerjoin(ProductVariant, ProductVariant.id == Batch.variant_id)\
        .filter(Batch.company_id == current_user.company_id)\
        .filter(Batch.quantity > 0)\
        .filter(Category.is_perishable == True)\
        .filter(Batch.expiry_date != None)\
        .all()
        
    result = []
    for b, p_name, v_name in batches:
        expiry = b.expiry_date.date() if hasattr(b.expiry_date, 'date') else b.expiry_date
        delta = (expiry - today_date).days
        if delta <= 30:
            result.append(ExpiringBatchOut(
                batch_id=b.id,
                product_name=p_name,
                variant_name=v_name,
                expiry_date=expiry,
                days_left=delta,
                quantity=b.quantity,
                is_expired=delta < 0
            ))
            
    result.sort(key=lambda x: x.days_left)
    return result


@router.post("/write-off-expired")
def write_off_expired(
    data: WriteOffExpiredRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager]))
):
    from app.models.batch import Batch
    
    batch = db.query(Batch).filter(Batch.id == data.batch_id, Batch.company_id == current_user.company_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch topilmadi")
        
    if batch.quantity <= 0:
        raise HTTPException(status_code=400, detail="Qoldiq yo'q")
        
    qty_to_write_off = batch.quantity
    
    stock_level = db.query(StockLevel).filter(
        StockLevel.product_id == batch.product_id,
        StockLevel.warehouse_id == batch.warehouse_id,
        StockLevel.variant_id == batch.variant_id
    ).with_for_update().first()
    
    if stock_level:
        qty_before = stock_level.quantity
        stock_level.quantity -= qty_to_write_off
        qty_after = stock_level.quantity
    else:
        raise HTTPException(status_code=400, detail="StockLevel topilmadi")
        
    batch.quantity = 0
    
    movement = StockMovement(
        product_id=batch.product_id,
        variant_id=batch.variant_id,
        type=MovementType.EXPIRED,
        qty_before=qty_before,
        qty_after=qty_after,
        quantity=qty_to_write_off,
        reference_type="batch_write_off",
        reference_id=batch.id,
        user_id=current_user.id,
        reason=f"Muddati o'tgan (xodim: {current_user.name})"
    )
    db.add(movement)
    db.commit()
    
    return {"message": "Muddati o'tgan mahsulot hisobdan chiqarildi"}
