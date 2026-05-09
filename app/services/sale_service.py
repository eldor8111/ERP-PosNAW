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
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType, SaleItemBatch, SalePayment  # type: ignore
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
    prev_debt_balance = 0.0
    if data.customer_id:
        # Xavfsizlik: faqat shu korxona mijozi olinadi
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        prev_debt_balance = float(customer.debt_balance or 0)

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
    
    # 3.1. To'lovlarni saqlash (SalePayment) va Moliya Tranzaksiya qo'shish
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
            
    if data.payments and len(data.payments) > 0:
        for p in data.payments:
            if p.amount > 0:
                sp = SalePayment(sale_id=sale.id, payment_type=p.type.value, amount=p.amount)
                db.add(sp)
                if tx_branch_id:
                    tx = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=p.amount, payment_type=p.type.value,
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv to'lovi #{sale.number} ({p.type.value})"
                    )
                    db.add(tx)
    elif data.paid_amount > 0:
        if data.payment_type == PaymentType.mixed:
            if data.paid_cash > 0:
                sp_cash = SalePayment(sale_id=sale.id, payment_type="cash", amount=data.paid_cash)
                db.add(sp_cash)
                if tx_branch_id:
                    tx_cash = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=data.paid_cash, payment_type="cash",
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv to'lovi #{sale.number} (Aralash/Naqd)"
                    )
                    db.add(tx_cash)
            if data.paid_card > 0:
                sp_card = SalePayment(sale_id=sale.id, payment_type="card", amount=data.paid_card)
                db.add(sp_card)
                if tx_branch_id:
                    tx_card = Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=data.paid_card, payment_type="card",
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv to'lovi #{sale.number} (Aralash/Karta)"
                    )
                    db.add(tx_card)
        else:
            sp = SalePayment(sale_id=sale.id, payment_type=data.payment_type.value, amount=data.paid_amount)
            db.add(sp)
            if tx_branch_id:
                tx = Transaction(
                    branch_id=tx_branch_id,
                    company_id=current_user.company_id,
                    type="income", amount=data.paid_amount, payment_type=data.payment_type.value,
                    reference_type="sale", reference_id=sale.id,
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
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if customer and getattr(customer, 'tg_chat_id', None):
            company = db.query(from_models_company).filter(from_models_company.id == current_user.company_id).first()
            if company and getattr(company, 'tg_bot_token', None):
                _token = str(company.tg_bot_token)
                _chat_id = str(customer.tg_chat_id)
                _sale_id = sale.id
                _prev_debt = prev_debt_balance
                _new_debt = float(customer.debt_balance or 0)
                _seller = current_user.name
                _comp_name = str(company.name)
                _cust_name = str(customer.name)

                def _bg_send(token, chat_id, sale_id, prev_debt, new_debt, seller, comp_name, cust_name):
                    try:
                        from app.database import SessionLocal
                        from sqlalchemy.orm import joinedload as _jl
                        _db = SessionLocal()
                        try:
                            from app.models.sale import Sale as _Sale, SaleItem as _SI
                            _sale = (
                                _db.query(_Sale)
                                .options(_jl(_Sale.items).joinedload(_SI.product), _jl(_Sale.payments))
                                .filter(_Sale.id == sale_id)
                                .first()
                            )
                            if not _sale:
                                return

                            def FMT(v):
                                val = float(v or 0)
                                if val == int(val):
                                    return f"{int(val):,}".replace(",", " ")
                                return f"{val:,.1f}".replace(",", " ")

                            pay_labels = {
                                "cash": "💵Naqd", "card": "💳Karta",
                                "uzcard": "💳UzCard", "humo": "💳Humo",
                                "bank": "🏦Bank", "click": "📱Click",
                                "payme": "📱Payme", "visa": "💳Visa",
                                "uzum": "📱Uzum", "debt": "🔖Qarz", "mixed": "💰Aralash",
                            }
                            if _sale.payments:
                                pay_lines = "\n".join(
                                    f"{pay_labels.get(str(p.payment_type), str(p.payment_type))}: som {FMT(p.amount)}"
                                    for p in _sale.payments if float(p.amount or 0) > 0
                                )
                            else:
                                pt = str(_sale.payment_type.value if hasattr(_sale.payment_type, 'value') else _sale.payment_type)
                                pay_lines = f"{pay_labels.get(pt, pt)}: som {FMT(_sale.total_amount)}"

                            item_lines = []
                            total_qty = 0
                            for it in _sale.items:
                                pname = it.product.name if it.product else f"ID={it.product_id}"
                                qty = float(it.quantity)
                                total_qty += qty
                                qty_str = str(int(qty)) if qty == int(qty) else f"{qty:g}"
                                item_lines.append(
                                    f"{pname}\n{qty_str} dona x som {FMT(it.unit_price)} = som {FMT(it.subtotal)}"
                                )

                            status_map = {
                                "completed": "Bajarildi", "pending": "Kutilmoqda",
                                "refunded": "Qaytarildi", "cancelled": "Bekor qilindi",
                                "partial_refund": "Qisman qaytarildi",
                            }
                            st = str(_sale.status.value if hasattr(_sale.status, 'value') else _sale.status)
                            sale_date = _sale.created_at.strftime("%d.%m.%Y %H:%M") if _sale.created_at else "-"
                            tqty_str = str(int(total_qty)) if total_qty == int(total_qty) else f"{total_qty:g}"

                            receipt = (
                                f"🧾 <b>Sotuv cheki</b>\n\n"
                                f"Mijoz: {cust_name}\n"
                                f"💴 Savdodan oldingi balans: som {FMT(prev_debt)}\n"
                                f"💰 Hozirgi balans: som {FMT(new_debt)}\n"
                                f"Savdo: #{_sale.number}\n"
                                f"Mahsulotlar:\n"
                                + "\n".join(item_lines)
                                + f"\nTashkilot: {comp_name}\n"
                                f"To'lov usuli:\n{pay_lines}\n\n"
                                f"Sotuvchi: {seller}\n"
                                f"📅 Sana: {sale_date}\n"
                                f"Holati: {status_map.get(st, st)}\n"
                                f"Jami: som {FMT(_sale.total_amount)}\n"
                                f"Chegirma bilan: som {FMT(_sale.total_amount)}\n"
                                f"Jami miqdor: {tqty_str}\n"
                                f"🏷 Jami chegirma: som {FMT(_sale.discount_amount)}"
                            )
                            send_tg_sync(token, chat_id, receipt)
                        finally:
                            _db.close()
                    except Exception as e:
                        print("Telegram BG error:", e)

                if background_tasks:
                    background_tasks.add_task(
                        _bg_send, _token, _chat_id, _sale_id,
                        _prev_debt, _new_debt, _seller, _comp_name, _cust_name
                    )
                else:
                    threading.Thread(
                        target=_bg_send,
                        args=(_token, _chat_id, _sale_id, _prev_debt, _new_debt, _seller, _comp_name, _cust_name),
                        daemon=True
                    ).start()

    return sale


def create_pending_sale(db: Session, data: SaleCreate, current_user: User, ip: str = None) -> Sale:
    """
    Ulgurji sotuv — to'lovsiz (pending) saqlash.
    Stock kamaytirmaydi, moliya tranzaksiya qo'shmaydi.
    Faqat Sale + SaleItem yozuvlarini saqlaydi.
    """
    # Warehouse aniqlash
    if data.warehouse_id is None:
        from app.models.warehouse import Warehouse
        wh_q = db.query(Warehouse).filter(
            Warehouse.company_id == current_user.company_id,
            Warehouse.is_active == True
        )
        if current_user.branch_id:
            wh = wh_q.filter(Warehouse.branch_id == current_user.branch_id).first()
            if wh:
                data.warehouse_id = wh.id
        if not data.warehouse_id:
            wh = wh_q.first()
            if wh:
                data.warehouse_id = wh.id

    # Mahsulotlar va summa hisoblash
    sale_items_data = []
    total_amount = Decimal("0")
    for item_data in data.items:
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
        ).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Mahsulot ID={item_data.product_id} topilmadi"
            )
        unit_price = item_data.unit_price if item_data.unit_price is not None else product.sale_price
        discount = item_data.discount
        subtotal = max(Decimal("0"), (unit_price * item_data.quantity) - discount)
        sale_items_data.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": product.cost_price,
            "discount": discount,
            "subtotal": subtotal,
        })
        total_amount += subtotal

    total_amount = max(Decimal("0"), total_amount - data.discount_amount)

    # Sale yozuvi (pending, paid=0)
    sale = Sale(
        number=generate_sale_number(db),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=Decimal("0"),
        paid_cash=Decimal("0"),
        paid_card=Decimal("0"),
        payment_type=PaymentType.cash,
        status=SaleStatus.pending,
        note=data.note,
        currency_id=data.currency_id,
        exchange_rate=Decimal("1"),
        loyalty_points_earned=0,
        loyalty_points_used=0,
        debt_due_date=None,
    )
    db.add(sale)
    db.flush()

    # SaleItem larni saqlash (stock tegilmaydi)
    for item_d in sale_items_data:
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item_d["product"].id,
            quantity=item_d["quantity"],
            unit_price=item_d["unit_price"],
            cost_price=item_d["cost_price"],
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
        ))

    log_action(
        db=db,
        action="SALE_PENDING",
        entity_type="sale",
        entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "status": "pending"},
        ip_address=ip,
    )

    db.commit()
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
    if sale.customer_id and sale.status != SaleStatus.pending:
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


def _reverse_sale_effects(db: Session, sale: Sale) -> None:
    """
    Sotuvning barcha moliyaviy ta'sirlarini bekor qilish.
    Stock, mijoz qarzi, loyallik ballari, cashback, finance tranzaksiyalar — hammasi qaytariladi.
    """
    from app.models.inventory import StockMovement, StockLevel  # type: ignore
    from app.models.sale import SaleItemBatch, SalePayment  # type: ignore
    from app.models.batch import Batch  # type: ignore
    from app.models.customer import Customer  # type: ignore

    # 1. Stock harakatlarini teskari bekor qilish (qty_before ga qaytarish)
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id
    ).all()
    for movement in old_movements:
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == movement.product_id,
            StockLevel.warehouse_id == sale.warehouse_id,
        ).first()
        if stock:
            stock.quantity = movement.qty_before
        db.delete(movement)

    # FIFO Batch larni tiklash
    for item in sale.items:
        for sib in db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).all():
            batch = db.query(Batch).filter(Batch.id == sib.batch_id).first()
            if batch:
                batch.quantity += sib.quantity
            db.delete(sib)

    # 2. Mijoz: qarz, loyalty, cashback, total_spent qaytarish
    if sale.customer_id and sale.status != SaleStatus.pending:
        customer = db.query(Customer).filter(
            Customer.id == sale.customer_id,
            Customer.company_id == sale.company_id,
        ).first()
        if customer:
            debt_in_sale = sale.total_amount - sale.paid_amount
            if debt_in_sale > 0:
                customer.debt_balance = max(Decimal("0"), customer.debt_balance - debt_in_sale)
            if sale.loyalty_points_used and sale.loyalty_points_used > 0:
                customer.loyalty_points += sale.loyalty_points_used
            if sale.loyalty_points_earned and sale.loyalty_points_earned > 0:
                customer.loyalty_points = max(0, customer.loyalty_points - sale.loyalty_points_earned)
            exr = getattr(sale, 'exchange_rate', Decimal('1')) or Decimal('1')
            if getattr(customer, "cashback_percent", 0) > 0:
                cashback_amount = (sale.total_amount * exr * customer.cashback_percent) / Decimal("100")
                customer.bonus_balance = max(Decimal("0"), (customer.bonus_balance or Decimal("0")) - cashback_amount)
            customer.total_spent = max(Decimal("0"), (customer.total_spent or Decimal("0")) - (sale.total_amount * exr))

    # 3. Moliya income tranzaksiyalarini o'chirish
    for otx in db.query(Transaction).filter(
        Transaction.reference_type == "sale",
        Transaction.reference_id == sale.id,
        Transaction.type == "income"
    ).all():
        db.delete(otx)

    # 4. SalePayment larni o'chirish
    db.query(SalePayment).filter(SalePayment.sale_id == sale.id).delete()

    # 5. SaleItem larni o'chirish
    for item in list(sale.items):
        db.delete(item)

    db.flush()


def update_sale(db: Session, sale_id: int, data, current_user: User) -> Sale:
    """Sotuvni yangilash: oddiy holat/izoh yoki to'liq tahrirlash (items bilan)."""
    from app.models.customer import Customer  # type: ignore
    from sqlalchemy.orm import joinedload  # type: ignore

    q = (
        db.query(Sale)
        .options(joinedload(Sale.items), joinedload(Sale.payments))
        .filter(Sale.id == sale_id)
    )
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    # ── To'liq tahrirlash (items berilgan bo'lsa) ──────────────────────────────
    if data.items is not None:
        # A. Eski qiymatlarni saqlab olish (reverse dan oldin)
        old_paid_amount = Decimal(str(sale.paid_amount or 0))
        old_payment_type = sale.payment_type
        old_paid_cash = Decimal(str(sale.paid_cash or 0))
        old_paid_card = Decimal(str(sale.paid_card or 0))

        # A2. Eski barcha moliyaviy ta'sirlarni bekor qilish
        _reverse_sale_effects(db, sale)

        wh_id = data.warehouse_id if data.warehouse_id is not None else sale.warehouse_id
        disc_amount = data.discount_amount if data.discount_amount is not None else Decimal("0")
        payment_type = data.payment_type if data.payment_type is not None else old_payment_type
        new_customer_id = data.customer_id if data.customer_id is not None else sale.customer_id

        # B. Yangi items hisoblash
        sale_items_data = []
        total_amount = Decimal("0")
        for item_d in data.items:
            product = db.query(Product).filter(
                Product.id == item_d.product_id,
                Product.company_id == current_user.company_id,
                Product.is_deleted == False,
            ).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_d.product_id} topilmadi")
            unit_price = item_d.unit_price if item_d.unit_price is not None else product.sale_price
            discount = item_d.discount
            subtotal = (unit_price * item_d.quantity) - discount
            sale_items_data.append({
                "product": product,
                "quantity": item_d.quantity,
                "unit_price": unit_price,
                "cost_price": product.cost_price,
                "discount": discount,
                "subtotal": subtotal,
            })
            total_amount += subtotal

        total_amount = max(Decimal("0"), total_amount - disc_amount)
        # To'lov o'zgarmaydi — eski to'lov saqlanadi
        paid_amount = data.paid_amount if data.paid_amount is not None else old_paid_amount
        paid_cash = data.paid_cash if data.paid_cash is not None else old_paid_cash
        paid_card = data.paid_card if data.paid_card is not None else old_paid_card

        # C. Yangi SaleItem yaratish + stock yechish
        final_status = data.status if data.status is not None else sale.status
        for sid in sale_items_data:
            db.add(SaleItem(
                sale_id=sale.id,
                product_id=sid["product"].id,
                quantity=sid["quantity"],
                unit_price=sid["unit_price"],
                cost_price=sid["cost_price"],
                discount=sid["discount"],
                subtotal=sid["subtotal"],
            ))
            if final_status != SaleStatus.pending:
                deduct_stock(
                    db=db,
                    product_id=sid["product"].id,
                    quantity=sid["quantity"],
                    user_id=current_user.id,
                    reason=f"Sotuv tahrirlash (sale #{sale_id})",
                    reference_type="sale",
                    reference_id=sale_id,
                    warehouse_id=wh_id,
                    allow_negative=True,
                )

        # D. Yangi mijoz: qarz, cashback, total_spent, loyalty yozish
        if new_customer_id and final_status != SaleStatus.pending:
            new_customer = db.query(Customer).filter(
                Customer.id == new_customer_id,
                Customer.company_id == current_user.company_id,
            ).first()
            if new_customer:
                new_debt = max(Decimal("0"), total_amount - paid_amount)
                if new_debt > 0:
                    new_customer.debt_balance = (new_customer.debt_balance or Decimal("0")) + new_debt
                exr = Decimal('1')
                if getattr(new_customer, "cashback_percent", 0) > 0:
                    cashback = (total_amount * exr * new_customer.cashback_percent) / Decimal("100")
                    new_customer.bonus_balance = (new_customer.bonus_balance or Decimal("0")) + cashback
                new_customer.total_spent = (new_customer.total_spent or Decimal("0")) + (total_amount * exr)
                loyalty_earned = int((total_amount * exr) * Decimal("0.01"))
                new_customer.loyalty_points = (new_customer.loyalty_points or 0) + loyalty_earned
                sale.loyalty_points_earned = loyalty_earned
            sale.loyalty_points_used = 0

        # E. Yangi moliya tranzaksiyalari yozish
        if final_status != SaleStatus.pending:
            tx_branch_id = current_user.branch_id
            if not tx_branch_id and wh_id:
                from app.models.warehouse import Warehouse as _WH  # type: ignore
                wh_obj = db.query(_WH).filter(_WH.id == wh_id).first()
                if wh_obj and wh_obj.branch_id:
                    tx_branch_id = wh_obj.branch_id
            if not tx_branch_id:
                from app.models.branch import Branch as _BR  # type: ignore
                br = db.query(_BR).filter(_BR.company_id == current_user.company_id).first()
                if br:
                    tx_branch_id = br.id

            from app.models.sale import SalePayment as _SP  # type: ignore
            if data.payments and len(data.payments) > 0:
                for p in data.payments:
                    if p.amount > 0:
                        db.add(_SP(sale_id=sale.id, payment_type=p.type.value, amount=p.amount))
                        if tx_branch_id:
                            db.add(Transaction(
                                branch_id=tx_branch_id, company_id=current_user.company_id,
                                type="income", amount=p.amount, payment_type=p.type.value,
                                reference_type="sale", reference_id=sale.id,
                                description=f"Sotuv tahrirlash #{sale.number} ({p.type.value})"
                            ))
            elif paid_amount > 0:
                db.add(_SP(sale_id=sale.id, payment_type=payment_type.value, amount=paid_amount))
                if tx_branch_id:
                    db.add(Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=paid_amount, payment_type=payment_type.value,
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv tahrirlash #{sale.number}"
                    ))

        # F. Sale maydonlarini yangilash
        sale.status = final_status
        sale.total_amount = total_amount
        sale.discount_amount = disc_amount
        sale.paid_amount = paid_amount
        sale.paid_cash = paid_cash
        sale.paid_card = paid_card
        sale.payment_type = payment_type
        sale.customer_id = new_customer_id
        sale.warehouse_id = wh_id
        if data.note is not None:
            sale.note = data.note
        if data.debt_due_date is not None:
            sale.debt_due_date = data.debt_due_date

    else:
        # ── Oddiy yangilash: faqat holat/izoh/to'lov ─────────────────────────
        old_status = sale.status
        if data.status is not None:
            sale.status = data.status
        if data.note is not None:
            sale.note = data.note
        if data.paid_amount is not None:
            if sale.customer_id:
                customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
                if customer:
                    old_debt = sale.total_amount - sale.paid_amount
                    new_debt = sale.total_amount - data.paid_amount
                    if old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
                        if new_debt > 0:
                            customer.debt_balance = (customer.debt_balance or Decimal("0")) + new_debt
                    elif old_status != SaleStatus.pending and sale.status == SaleStatus.pending:
                        if old_debt > 0:
                            customer.debt_balance = max(Decimal("0"), customer.debt_balance - old_debt)
                    elif old_status != SaleStatus.pending and sale.status != SaleStatus.pending:
                        diff = new_debt - old_debt
                        customer.debt_balance = max(Decimal("0"), customer.debt_balance + diff)
            sale.paid_amount = data.paid_amount

        # Pending → Completed holatida paid_amount berilmasa ham mijoz qarzini yozish
        if data.paid_amount is None and old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
            if sale.customer_id:
                customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
                if customer:
                    remaining_debt = sale.total_amount - sale.paid_amount
                    if remaining_debt > 0:
                        customer.debt_balance = (customer.debt_balance or Decimal("0")) + remaining_debt

        # 2. Stock updates for simple status transition
        if old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
            for item in sale.items:
                deduct_stock(
                    db=db,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    user_id=current_user.id,
                    reason=f"Sotuv tasdiqlandi (sale #{sale.id})",
                    reference_type="sale",
                    reference_id=sale.id,
                    warehouse_id=sale.warehouse_id,
                    allow_negative=True,
                )
        elif old_status != SaleStatus.pending and sale.status == SaleStatus.pending:
            from app.models.inventory import StockMovement, StockLevel  # type: ignore
            old_movements = db.query(StockMovement).filter(
                StockMovement.reference_type == "sale",
                StockMovement.reference_id == sale.id
            ).all()
            for movement in old_movements:
                stock = db.query(StockLevel).filter(
                    StockLevel.product_id == movement.product_id,
                    StockLevel.warehouse_id == sale.warehouse_id,
                ).first()
                if stock:
                    stock.quantity = movement.qty_before
                db.delete(movement)

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
