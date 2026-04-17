from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy import func  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import threading
import requests
import os

from app.models.user import UserRole  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.models.product import Product, ProductStatus  # type: ignore
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType, SaleItemBatch  # type: ignore
from app.models.batch import Batch
from app.schemas.sale import SaleCreate  # type: ignore
from app.services.inventory_service import deduct_stock, receive_stock  # type: ignore

def send_tg_sync(token, chat_id, text, filepath=None):
    try:
        if filepath and os.path.exists(filepath):
            with open(filepath, "rb") as doc:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                    files={"document": doc},
                    timeout=10
                )
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
    except:
        pass
def generate_sale_number(db: Session) -> str:
    """MAX ishlatadi — COUNT dan 2-3x tezroq."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"S{today}"
    max_num_str = (
        db.query(func.max(Sale.number))
        .filter(Sale.number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num_str:
        try:
            last_num = int(max_num_str[len(prefix):])
        except (ValueError, IndexError):
            last_num = 0
    else:
        last_num = 0
    return f"{prefix}{last_num + 1:04d}"


def generate_return_number(db: Session) -> str:
    """MAX ishlatadi — COUNT dan 2-3x tezroq."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"R{today}"
    max_num_str = (
        db.query(func.max(Sale.number))
        .filter(Sale.number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num_str:
        try:
            last_num = int(max_num_str[len(prefix):])
        except (ValueError, IndexError):
            last_num = 0
    else:
        last_num = 0
    return f"{prefix}{last_num + 1:04d}"

from app.models.customer import Customer  # type: ignore
from app.models.currency import Currency  # type: ignore
from app.models.company import Company as from_models_company  # type: ignore
from app.models.moliya import Transaction  # type: ignore
from app.models.branch import Branch  # type: ignore

from app.models.user import User  # type: ignore

def create_sale(db: Session, data: SaleCreate, current_user: User, ip: Optional[str] = None, background_tasks=None) -> Sale:
    if data.warehouse_id is None:
        from app.models.warehouse import Warehouse
        from app.models.inventory import StockLevel as _StockLevel
        wh_q = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id, Warehouse.is_active == True)
        if current_user.branch_id:
            wh = wh_q.filter(Warehouse.branch_id == current_user.branch_id).first()
            if not wh:
                wh = wh_q.first()
            if wh:
                data.warehouse_id = wh.id
        else:
            # Filialsiz foydalanuvchi: birinchi mahsulot uchun qoldig'i bor omborni topamiz
            if data.items:
                first_pid = data.items[0].product_id
                stock_row = (
                    db.query(_StockLevel)
                    .join(Warehouse, Warehouse.id == _StockLevel.warehouse_id)
                    .filter(
                        _StockLevel.product_id == first_pid,
                        _StockLevel.quantity > 0,
                        _StockLevel.warehouse_id.isnot(None),
                        Warehouse.is_active == True,
                    )
                    .order_by(_StockLevel.quantity.desc())
                    .first()
                )
                if stock_row:
                    data.warehouse_id = stock_row.warehouse_id
                # Aks holda warehouse_id=None qoladi — deduct_stock barcha omborlardan yechadi

    # 1. Mahsulotlarni tekshirish va narxlarni hisoblash
    sale_items_data = []
    total_amount = Decimal("0")

    for item_data in data.items:
        # Xavfsizlik: faqat shu korxona mahsulotlari olinadi
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
            Product.status == ProductStatus.active,
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Mahsulot ID={item_data.product_id} topilmadi yoki nofaol",
            )

        unit_price = item_data.unit_price if item_data.unit_price is not None else product.sale_price
        max_discount = unit_price * item_data.quantity
        discount = item_data.discount
        if discount > max_discount:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' uchun chegirma ({discount}) narxdan ({max_discount}) oshib ketdi",
            )
        subtotal = (unit_price * item_data.quantity) - discount

        sale_items_data.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": product.cost_price,
            "discount": discount,
            "subtotal": subtotal,
        })
        total_amount += subtotal

    total_amount -= data.discount_amount
    # Chegirma summasi jami narxdan oshib ketmasligi kerak
    if total_amount < Decimal("0"):
        total_amount = Decimal("0")

    # Agar qarzga sotilayotgan bo'lsa, albatta mijozni tanlash majburiy
    if data.payment_type.value == "debt" and not data.customer_id:
        raise HTTPException(
            status_code=400,
            detail="Qarzga sotish uchun mijozni tanlash majburiy"
        )


    # Valyuta hisobi
    exchange_rate = Decimal(1.0)
    if data.currency_id:
        currency = db.query(Currency).filter(Currency.id == data.currency_id).first()
        if currency:
            exchange_rate = currency.rate

    # CRM Va Loyallik ballari hisob-kitobi
    loyalty_earned = 0
    if data.customer_id:
        # Xavfsizlik: faqat shu korxona mijozi olinadi
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
            
        if data.loyalty_points_used > 0:
            if data.loyalty_points_used > customer.loyalty_points:
                raise HTTPException(status_code=400, detail="Mijozda yetarli loyallik ballari yo'q")
            # 1 ball = 1 so'm deb qabul qilamiz (buni kustomizatsiya qilish mumkin)
            discount_from_loyalty = Decimal(data.loyalty_points_used)
            total_amount -= discount_from_loyalty
            customer.loyalty_points -= data.loyalty_points_used
            
        # Keshbek va total_spent qo'shish
        if getattr(customer, "cashback_percent", 0) > 0:
            cashback_amount = (total_amount * exchange_rate * customer.cashback_percent) / Decimal("100")
            customer.bonus_balance = (customer.bonus_balance or Decimal("0")) + cashback_amount
        customer.total_spent = (customer.total_spent or Decimal("0")) + (total_amount * exchange_rate)

        # Xarid summasidan (valyutadan keyin base qiymat) %1 ni keshbek qilamiz
        loyalty_earned = int((total_amount * exchange_rate) * Decimal("0.01"))
        customer.loyalty_points += loyalty_earned
        
        # Agar qisman yoki to'liq qarz bo'lsa (istalgan to'lov turi bilan)
        if data.paid_amount < total_amount:
            debt_amount = total_amount - data.paid_amount
            if customer.debt_limit > 0 and (customer.debt_balance + debt_amount) > customer.debt_limit:
                raise HTTPException(status_code=400, detail="Kechirasiz, mijozning qarz limiti oshib ketdi")
            customer.debt_balance += debt_amount

    # 2. To'lov tekshiruvi — mijoz bo'lmasa qarz yopib bo'lmaydi
    if data.paid_amount < total_amount and not data.customer_id:
        raise HTTPException(
            status_code=400,
            detail="Qarzga yoki qisman to'lovga sotish uchun mijozni tanlash majburiy",
        )

    # 3. Savdo hujjatini yaratish
    sale = Sale(
        number=generate_sale_number(db),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=data.paid_amount,
        paid_cash=data.paid_cash,
        paid_card=data.paid_card,
        payment_type=data.payment_type,
        status=SaleStatus.completed,
        note=data.note,
        currency_id=data.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=loyalty_earned,
        loyalty_points_used=data.loyalty_points_used,
        debt_due_date=data.debt_due_date,
    )
    db.add(sale)
    db.flush()
    
    # 3.1. Agar qisman yoki full to'lov qilingan bo'lsa, avto-Moliya Tranzaksiya qoshish
    if data.paid_amount > 0:
        tx_branch_id = current_user.branch_id
        if not tx_branch_id and data.warehouse_id:
            from app.models.warehouse import Warehouse as _Warehouse
            wh_obj = db.query(_Warehouse).filter(_Warehouse.id == data.warehouse_id).first()
            if wh_obj and wh_obj.branch_id:
                tx_branch_id = wh_obj.branch_id
        if not tx_branch_id:
            from app.models.branch import Branch as _Branch
            br = db.query(_Branch).filter(_Branch.company_id == current_user.company_id).first()
            if br:
                tx_branch_id = br.id
        
        if tx_branch_id:
            if data.payment_type == PaymentType.mixed:
                if data.paid_cash > 0:
                    tx_cash = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=data.paid_cash, reference_type="sale",
                        reference_id=sale.id, description=f"Sotuv to'lovi #{sale.number} (Aralash/Naqd)"
                    )
                    db.add(tx_cash)
                if data.paid_card > 0:
                    tx_card = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=data.paid_card, reference_type="sale",
                        reference_id=sale.id, description=f"Sotuv to'lovi #{sale.number} (Aralash/Karta)"
                    )
                    db.add(tx_card)
            else:
                tx = Transaction(
                    branch_id=tx_branch_id,
                    company_id=current_user.company_id,
                    type="income",
                    amount=data.paid_amount,
                    reference_type="sale",
                    reference_id=sale.id,
                    description=f"Sotuv to'lovi #{sale.number}"
                )
                db.add(tx)

    # 4. Optimized: barcha mahsulotlar uchun Batch larni BITTA query bilan olamiz (N+1 muammosi hal qilindi)
    product_ids = [item_d["product"].id for item_d in sale_items_data]
    batches_q = db.query(Batch).filter(
        Batch.product_id.in_(product_ids),
        Batch.quantity > 0,
        Batch.company_id == current_user.company_id
    )
    if data.warehouse_id is not None:
        batches_q = batches_q.filter(Batch.warehouse_id == data.warehouse_id)
    all_batches = batches_q.order_by(Batch.created_at.asc(), Batch.id.asc()).all()

    # product_id → sorted list of batches (FIFO)
    from collections import defaultdict
    batches_by_product = defaultdict(list)
    for b in all_batches:
        batches_by_product[b.product_id].append(b)

    # StockLevel larni ham bitta query bilan olamiz
    from app.models.inventory import StockLevel as _SL
    if data.warehouse_id is not None:
        stock_rows = db.query(_SL).filter(
            _SL.product_id.in_(product_ids),
            _SL.warehouse_id == data.warehouse_id
        ).with_for_update().all()
    else:
        stock_rows = db.query(_SL).filter(
            _SL.product_id.in_(product_ids),
            _SL.quantity > 0
        ).order_by(_SL.quantity.desc()).with_for_update().all()
    
    stocks_by_product = defaultdict(list)
    for s in stock_rows:
        stocks_by_product[s.product_id].append(s)

    new_sale_items = []
    new_sibs = []
    new_movements = []

    for item_d in sale_items_data:
        product = item_d["product"]
        qty_needed = Decimal(item_d["quantity"])

        # --- Stock kamaytirish (DB lock allaqachon olindi yuqorida) ---
        if data.warehouse_id is not None:
            stocks = stocks_by_product.get(product.id, [])
            if not stocks:
                # Yangi yaratamiz
                from app.models.inventory import StockLevel as _SL2
                new_sl = _SL2(product_id=product.id, warehouse_id=data.warehouse_id, quantity=Decimal("0"))
                db.add(new_sl)
                stocks = [new_sl]
                stocks_by_product[product.id] = stocks
            stock = stocks[0]
            qty_before = stock.quantity
            stock.quantity -= qty_needed
            from app.models.inventory import StockMovement, MovementType
            new_movements.append(StockMovement(
                product_id=product.id,
                type=MovementType.OUT,
                qty_before=qty_before,
                qty_after=stock.quantity,
                quantity=qty_needed,
                reference_type="sale",
                reference_id=sale.id,
                user_id=current_user.id,
                reason=f"Sotuv #{sale.number}",
            ))
        else:
            # Barcha omborlardan yechamiz
            stocks = stocks_by_product.get(product.id, [])
            total_avail = sum((s.quantity for s in stocks), Decimal("0"))
            remaining_deduct = qty_needed
            if total_avail < qty_needed:
                if not stocks:
                    from app.models.inventory import StockLevel as _SL3
                    new_sl = _SL3(product_id=product.id, warehouse_id=None, quantity=Decimal("0"))
                    db.add(new_sl)
                    stocks = [new_sl]
                stocks[0].quantity -= (qty_needed - total_avail)
                remaining_deduct = total_avail
            from app.models.inventory import StockMovement, MovementType
            for stock in stocks:
                if remaining_deduct <= 0:
                    break
                take = min(remaining_deduct, stock.quantity)
                qty_before = stock.quantity
                stock.quantity -= take
                remaining_deduct -= take
                new_movements.append(StockMovement(
                    product_id=product.id,
                    type=MovementType.OUT,
                    qty_before=qty_before,
                    qty_after=stock.quantity,
                    quantity=take,
                    reference_type="sale",
                    reference_id=sale.id,
                    user_id=current_user.id,
                    reason=f"Sotuv #{sale.number}",
                ))

        # --- FIFO Batch Allocation (keshdan) ---
        batches = batches_by_product.get(product.id, [])
        remaining_to_allocate = qty_needed
        total_allocated_cost = Decimal("0")
        allocated_batches = []

        for batch in batches:
            if remaining_to_allocate <= 0:
                break
            qty_from_batch = min(remaining_to_allocate, batch.quantity)
            batch.quantity -= qty_from_batch
            remaining_to_allocate -= qty_from_batch
            cost = qty_from_batch * (batch.purchase_price or Decimal("0"))
            total_allocated_cost += cost
            allocated_batches.append({
                "batch_id": batch.id,
                "quantity": qty_from_batch,
                "unit_cost": batch.purchase_price or Decimal("0")
            })

        if remaining_to_allocate > 0:
            cost = remaining_to_allocate * (product.cost_price or Decimal("0"))
            total_allocated_cost += cost

        exact_unit_cost = (total_allocated_cost / qty_needed) if qty_needed > 0 else Decimal("0")

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=qty_needed,
            unit_price=item_d["unit_price"],
            cost_price=exact_unit_cost,
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
        )
        new_sale_items.append((sale_item, allocated_batches))

    # Barcha SaleItem larni birdan qo'shish
    for sale_item, allocated_batches in new_sale_items:
        db.add(sale_item)
    db.flush()  # sale_item.id lar tayyor bo'lsin

    # SaleItemBatch va StockMovement larni birdan qo'shish
    for sale_item, allocated_batches in new_sale_items:
        for ab in allocated_batches:
            db.add(SaleItemBatch(
                sale_item_id=sale_item.id,
                batch_id=ab["batch_id"],
                quantity=ab["quantity"],
                unit_cost=ab["unit_cost"]
            ))
    for mov in new_movements:
        db.add(mov)

    log_action(
        db=db,
        action="SALE",
        entity_type="sale",
        entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "payment": data.payment_type.value},
        ip_address=ip,
    )

    db.commit()
    # refresh is NOT needed here — router will call _load_sale with a fresh joinedload query
    
    # 5. Telegram notification — fully async, does NOT block the HTTP response
    if getattr(data, 'customer_id', None):
        # Xavfsizlik: faqat shu korxona mijozi (Telegram xabarnoma uchun)
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if customer and getattr(customer, 'tg_chat_id', None):
            company = db.query(from_models_company).filter(from_models_company.id == current_user.company_id).first()
            if company and getattr(company, 'tg_bot_token', None):
                due_str = data.debt_due_date.strftime("%d.%m.%Y") if getattr(data, 'debt_due_date', None) else "belgilanmagan"
                debt_val = total_amount - data.paid_amount

                if debt_val > 0:
                    msg = f"🔔 <b>Qarz qo'shildi</b>\n\nHurmatli <b>{customer.name}</b>!\nSiz bugun <b>{company.name}</b> do'konidan qarzingiz tushdi.\n\n📅 Qarzni to'lash muddati: <b>{due_str}</b>\n\n<i>Iltimos qarzni o'z vaqtida to'lashni unutmang! Chek ilova qilindi.</i>"
                else:
                    msg = f"✅ Xaridingiz uchun rahmat, <b>{customer.name}</b>!\nHaridingiz cheki fayl sifatida ilova qilindi."

                # Snapshot all needed values before launching thread
                _token = company.tg_bot_token
                _chat_id = customer.tg_chat_id
                _sale_id = sale.id
                _sale_num = sale.number
                _msg = msg
                _comp = company
                _cust = customer

                def _bg_send(token, chat_id, text, sale_id, comp, cust):
                    """Runs safely after response is sent"""
                    try:
                        from app.utils.pdf_generator import build_sale_pdf
                        from app.database import SessionLocal
                        _db = SessionLocal()
                        try:
                            from app.models.sale import Sale as _Sale
                            _sale = _db.query(_Sale).filter(_Sale.id == sale_id).first()
                            if _sale:
                                filepath = build_sale_pdf(_sale, comp, cust)
                                send_tg_sync(token, chat_id, text, filepath)
                            else:
                                send_tg_sync(token, chat_id, text)
                        finally:
                            _db.close()
                    except Exception as e:
                        print("Telegram BG error:", e)

                if background_tasks:
                    background_tasks.add_task(_bg_send, _token, _chat_id, _msg, _sale_id, _comp, _cust)
                else:
                    threading.Thread(
                        target=_bg_send,
                        args=(_token, _chat_id, _msg, _sale_id, _comp, _cust),
                        daemon=True
                    ).start()

    return sale


def delete_sale(db: Session, sale_id: int, current_user: User) -> None:
    """Sotuvni o'chirish: har bir mahsulot qoldig'ini qaytarish + StockMovement log."""
    from app.models.inventory import StockMovement  # type: ignore

    q = db.query(Sale).filter(Sale.id == sale_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if sale.status == SaleStatus.cancelled:
        raise HTTPException(status_code=400, detail="Sotuv allaqachon bekor qilingan")

    # 1. Tarixdagi StockMovement yozuvlarini o'chirish (oldingi holatga qaytarish)
    # Bu sotuvga tegishli barcha stock harakatlarini topib, ularni bekor qilamiz
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id
    ).all()

    # Har bir harakatni teskari yo'nalishda bekor qilamiz
    from app.models.inventory import StockLevel  # type: ignore
    from app.models.sale import SaleItemBatch
    from app.models.batch import Batch
    
    for movement in old_movements:
        # Qoldiqni oldingi holatga qaytaramiz
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == movement.product_id,
            StockLevel.warehouse_id == sale.warehouse_id,
        ).first()

        if stock:
            # Sotuvda OUT harakati bo'lgan, shuning uchun qoldiqni qaytaramiz
            stock.quantity = movement.qty_before

        # Eski harakatni o'chiramiz
        db.delete(movement)

    # FIFO Batch larni tiklash
    for item in sale.items:
        sale_item_batches = db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).all()
        for sib in sale_item_batches:
            batch = db.query(Batch).filter(Batch.id == sib.batch_id).first()
            if batch:
                batch.quantity += sib.quantity
            db.delete(sib)

    # 2. Mijoz qarzini va loyallik ballarini to'g'irlash
    if sale.customer_id:
        # Xavfsizlik: faqat shu korxona mijozi (sale.company_id orqali)
        customer = db.query(Customer).filter(
            Customer.id == sale.customer_id,
            Customer.company_id == sale.company_id,
        ).first()
        if customer:
            # 2.1. Qarzni qaytarish (agar qarzdorlik bo'lgan bo'lsa — istalgan to'lov turida)
            debt_in_sale = sale.total_amount - sale.paid_amount
            if debt_in_sale > 0:
                customer.debt_balance = max(Decimal("0"), customer.debt_balance - debt_in_sale)

            # 2.2. Loyallik ballarini qaytarish
            # Avval ishlatilgan ballarni qaytaramiz
            if sale.loyalty_points_used and sale.loyalty_points_used > 0:
                customer.loyalty_points += sale.loyalty_points_used

            # Keyin berilgan ballarni olib qo'yamiz
            if sale.loyalty_points_earned and sale.loyalty_points_earned > 0:
                customer.loyalty_points = max(0, customer.loyalty_points - sale.loyalty_points_earned)

            # Qo'shilgan cashback va total_spent ni ayirish
            if getattr(customer, "cashback_percent", 0) > 0:
                cashback_amount = (sale.total_amount * getattr(sale, 'exchange_rate', Decimal('1')) * customer.cashback_percent) / Decimal("100")
                customer.bonus_balance = max(Decimal("0"), (customer.bonus_balance or Decimal("0")) - cashback_amount)

            customer.total_spent = max(Decimal("0"), (customer.total_spent or Decimal("0")) - (sale.total_amount * getattr(sale, 'exchange_rate', Decimal('1'))))

    # 3. Moliya tranzaksiyasini qaytarish (agar to'lov qilingan bo'lsa)
    if sale.paid_amount > 0:
        # Avvalgi kirim tranzaksiyalarini (masalan, aralash to'lovlar uchun 2 ta) topamiz
        old_transactions = db.query(Transaction).filter(
            Transaction.reference_type == "sale",
            Transaction.reference_id == sale.id,
            Transaction.type == "income"
        ).all()

        if old_transactions:
            for otx in old_transactions:
                db.delete(otx)
        else:
            # Agar tranzaksiya topilmasa, yangi chiqim tranzaksiya qo'shamiz (qaytarish)
            refund_branch_id = current_user.branch_id
            if not refund_branch_id and sale.warehouse_id:
                from app.models.warehouse import Warehouse as _WH
                wh_obj = db.query(_WH).filter(_WH.id == sale.warehouse_id).first()
                if wh_obj and wh_obj.branch_id:
                    refund_branch_id = wh_obj.branch_id
            if not refund_branch_id:
                from app.models.branch import Branch as _BR
                br = db.query(_BR).filter(_BR.company_id == current_user.company_id).first()
                if br:
                    refund_branch_id = br.id
            if refund_branch_id:
                refund_tx = Transaction(
                    branch_id=refund_branch_id,
                    company_id=current_user.company_id,
                    type="expense",
                    amount=sale.paid_amount,
                    reference_type="sale_refund",
                    reference_id=sale.id,
                    description=f"Sotuv bekor qilish #{sale.number}"
                )
                db.add(refund_tx)

    log_action(
        db=db,
        action="SALE_DELETE",
        entity_type="sale",
        entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(sale.total_amount)},
    )

    # 4. Sotuvni o'chirish
    db.delete(sale)
    db.commit()


def update_sale(db: Session, sale_id: int, data, current_user: User) -> Sale:
    """Sotuvni qisman yangilash: holat, izoh, to'lov miqdori."""
    q = db.query(Sale).filter(Sale.id == sale_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    if data.status is not None:
        sale.status = data.status
    if data.note is not None:
        sale.note = data.note
    if data.paid_amount is not None:
        # Mijoz qarzini to'g'irlash
        if sale.customer_id:
            from app.models.customer import Customer  # type: ignore
            customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
            if customer:
                old_debt = sale.total_amount - sale.paid_amount
                new_debt = sale.total_amount - data.paid_amount
                diff = new_debt - old_debt  # musbat = qarz oshdi, manfiy = qarz kamaydi
                customer.debt_balance = max(Decimal("0"), customer.debt_balance + diff)
        sale.paid_amount = data.paid_amount

    log_action(
        db=db,
        action="SALE_UPDATE",
        entity_type="sale",
        entity_id=sale.id,
        user_id=current_user.id,
        new_values={"status": str(sale.status), "paid": str(sale.paid_amount)},
    )

    db.commit()
    return sale


def create_return_sale(db: Session, data: SaleCreate, current_user, ip: str = None) -> Sale:
    """
    Sotuv interfeysidagi Vazvrat (Return) uchun maxsus funksiya.
    Qilingan ishlar:
    1. Qarzga olingan tovar qaytarilsa, mijoz qarzi kamayadi.
    2. Tovarlar qoldigi (Stock) receive_stock orqali uzluksiz oshiriladi.
    3. Pul mijozga qaytarilsa (paid_amount > 0), kassadan 'expense' tranzaksiyasi yaratiladi.
    4. Sale statusi 'refunded' qilib belgilanadi.
    """
    from app.models.moliya import Transaction

    total_amount = Decimal("0")
    sale_items_data = []

    # 1. Mahsulotlarni tekshirish va narxni hisoblash
    for item_d in data.items:
        # Xavfsizlik: faqat shu korxona mahsulotlari olinadi
        product = db.query(Product).filter(
            Product.id == item_d.product_id,
            Product.company_id == current_user.company_id,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item_d.product_id}")

        qty = Decimal(str(item_d.quantity))
        price = Decimal(str(item_d.unit_price)) if item_d.unit_price is not None else product.sale_price
        discount = Decimal(str(item_d.discount))
        subtotal = (price - discount) * qty

        total_amount += subtotal

        sale_items_data.append({
            "product": product,
            "quantity": qty,
            "unit_price": price,
            "discount": discount,
            "subtotal": subtotal,
            "cost_price": product.cost_price,
        })

    total_amount -= data.discount_amount
    if total_amount < 0:
        total_amount = Decimal("0")

    # Mijoz qarzini hisoblash (orqaga qaytarish)
    if data.customer_id:
        from app.models.customer import Customer # type: ignore
        # Xavfsizlik: faqat shu korxona mijozi olinadi
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).with_for_update().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        
        # Vazvrat bo'lganda mijozga to'liq pul qaytarilmasa, demak uning qarzidan chegiriladi
        if data.paid_amount < total_amount:
            debt_amount = total_amount - data.paid_amount
            customer.debt_balance = max(Decimal("0"), customer.debt_balance - debt_amount)

    # 3. Savdo hujjatini yaratish (Vazvrat)
    sale = Sale(
        number=generate_return_number(db),  # R prefix bilan - Return ekanini bildirish uchun
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=data.paid_amount,
        paid_cash=data.paid_cash,
        paid_card=data.paid_card,
        payment_type=data.payment_type,
        status=SaleStatus.refunded, # Muhim: Vazvrat
        note="Vazvrat: " + (data.note or ""),
        currency_id=data.currency_id,
        exchange_rate=1, # Default
        loyalty_points_earned=0,
        loyalty_points_used=0,
    )
    db.add(sale)
    db.flush()
    
    # 3.1. Agar pul qaytarilayotgan bo'lsa (Expense)
    if data.paid_amount > 0:
        tx_branch_id = current_user.branch_id
        if not tx_branch_id and data.warehouse_id:
            from app.models.warehouse import Warehouse as _Warehouse
            wh_obj = db.query(_Warehouse).filter(_Warehouse.id == data.warehouse_id).first()
            if wh_obj and wh_obj.branch_id:
                tx_branch_id = wh_obj.branch_id
        if not tx_branch_id:
            from app.models.branch import Branch as _Branch
            br = db.query(_Branch).filter(_Branch.company_id == current_user.company_id).first()
            if br:
                tx_branch_id = br.id
        
        if tx_branch_id:
            if data.payment_type == PaymentType.mixed:
                if data.paid_cash > 0:
                    tx_cash = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="expense", amount=data.paid_cash, reference_type="sale_refund",
                        reference_id=sale.id, description=f"Vazvrat to'lovi #{sale.number} (Aralash/Naqd)"
                    )
                    db.add(tx_cash)
                if data.paid_card > 0:
                    tx_card = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="expense", amount=data.paid_card, reference_type="sale_refund",
                        reference_id=sale.id, description=f"Vazvrat to'lovi #{sale.number} (Aralash/Karta)"
                    )
                    db.add(tx_card)
            else:
                tx = Transaction(
                    branch_id=tx_branch_id,
                    company_id=current_user.company_id,
                    type="expense",
                    amount=data.paid_amount,
                    reference_type="sale_refund",
                    reference_id=sale.id,
                    description=f"Vazvrat to'lovi #{sale.number}"
                )
                db.add(tx)

    # 4. Har mahsulot uchun: SaleItem + qoldiq KOPAYTIRISH
    for item_d in sale_items_data:
        product = item_d["product"]
        qty_needed = Decimal(str(item_d["quantity"]))

        # Qoldiqni oshirish
        receive_stock(
            db=db,
            product_id=product.id,
            quantity=qty_needed,
            user_id=current_user.id,
            reason=f"Vazvrat #{sale.number}",
            reference_type="sale_refund",
            reference_id=sale.id,
            warehouse_id=data.warehouse_id,
        )

        # FIFO: qaytarilgan tovarni yangi Batch sifatida kiritish
        return_batch = Batch(
            product_id=product.id,
            warehouse_id=data.warehouse_id,
            lot_number=f"RETURN-{sale.number}",
            initial_quantity=qty_needed,
            quantity=qty_needed,
            purchase_price=product.cost_price,
            company_id=current_user.company_id,
        )
        db.add(return_batch)

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=qty_needed,
            unit_price=item_d["unit_price"],
            cost_price=item_d["cost_price"],
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
        )
        db.add(sale_item)

    log_action(
        db=db,
        action="SALE_RETURN",
        entity_type="sale",
        entity_id=sale.id,
        user_id=current_user.id,
    )

    db.commit()
    db.refresh(sale)
    return sale
