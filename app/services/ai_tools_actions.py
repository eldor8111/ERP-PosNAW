from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.sale import Sale, SaleItem
from app.models.warehouse import Warehouse
from app.utils.report_utils import sale_or_return_filter, doc_sign
from app.models.supplier_product import SupplierProduct
from app.services.ai_tools_registry import AITool, AIToolRegistry, BRANCH_PARAM

@AIToolRegistry.register
class DraftPurchaseOrderTool(AITool):
    name = "draft_purchase_order"
    description = "Tugayotgan yoki qoldig'i kam mahsulotlar uchun yetkazib beruvchiga zayavka (Purchase Order) qoralamasini tayyorlash."
    required_permission = "purchase.create"
    risk_level = "MEDIUM" # Qoralama tayyorlaydi, bevosita rasmiylashtirmaydi
    parameters = {
        "type": "object",
        "properties": {
            "days_ahead": {"type": "integer", "description": "Zayavka necha kunlik ehtiyojni qoplashi kerak? Standart: 14 kun."},
            "urgent_only": {"type": "boolean", "description": "Faqat hozir yoki yaqin 3 kunda tugaydiganlari olinsinmi? Standart: false."},
            "branch": BRANCH_PARAM,
            "warehouse_id": {
                "type": "integer",
                "description": "Ombor ID (ixtiyoriy). Berilsa faqat shu ombor qoldig'i va min/max chegarasi bo'yicha hisoblanadi.",
            },
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.services.ai_scope import resolve_tool_scope, scope_header, scope_label, item_scope_filter
        from app.utils.stock_utils import warehouse_limits
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        head = scope_header(scope, note)
        # T4.4: ixtiyoriy ombor — qoldiq va chegara faqat shu ombor bo'yicha (berilmasa eski xatti-harakat)
        warehouse_id = kwargs.get("warehouse_id")
        try:
            warehouse_id = int(warehouse_id) if warehouse_id not in (None, "") else None
        except (TypeError, ValueError):
            warehouse_id = None
        if warehouse_id is not None:
            wh_ok = db.query(Warehouse.id).filter(Warehouse.id == warehouse_id, Warehouse.company_id == company_id).first()
            if not wh_ok or (scope is not None and warehouse_id not in {int(w) for w in scope.warehouse_ids}):
                return {"reply": f"{head}Ombor topilmadi yoki unga ruxsat yo'q."}
        days_ahead = kwargs.get("days_ahead", 14)
        urgent_only = kwargs.get("urgent_only", False)

        history_days = 14
        start_date = datetime.now(timezone.utc) - timedelta(days=history_days)

        # Ombor kesimida: tezlik (SaleItem.warehouse_id, bo'lmasa Sale.warehouse_id) va qoldiq (StockLevel.warehouse_id)
        item_wh = func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id)
        sales_q = db.query(
            SaleItem.product_id.label("product_id"),
            item_wh.label("warehouse_id"),
            func.sum(doc_sign() * SaleItem.quantity).label("total_sold_14d"),
        ).join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(Sale.company_id == company_id, sale_or_return_filter(), Sale.created_at >= start_date)
        flt = item_scope_filter(scope)
        if flt is not None:
            sales_q = sales_q.filter(flt)
        if warehouse_id is not None:
            sales_q = sales_q.filter(item_wh == warehouse_id)
        sales_rows = sales_q.group_by(SaleItem.product_id, item_wh).all()

        stock_q = db.query(
            StockLevel.product_id, StockLevel.warehouse_id, func.sum(StockLevel.quantity)
        ).join(Product, Product.id == StockLevel.product_id).filter(Product.company_id == company_id)
        # Faqat faol omborlar qoldig'i hisobga olinadi (nofaol ombor qoldig'i buyurtmaga ta'sir qilmasin)
        stock_q = stock_q.filter(
            __import__("sqlalchemy").or_(StockLevel.warehouse_id.is_(None), StockLevel.warehouse.has(is_active=True))
        )
        if scope is not None:
            stock_q = stock_q.filter(StockLevel.warehouse_id.in_(list(scope.warehouse_ids)))
        if warehouse_id is not None:
            stock_q = stock_q.filter(StockLevel.warehouse_id == warehouse_id)
        stock_map = {(pid, wid): float(q or 0) for pid, wid, q in stock_q.group_by(
            StockLevel.product_id, StockLevel.warehouse_id).all()}

        sold_ids = {r.product_id for r in sales_rows}
        limits = {}
        if warehouse_id is not None:
            # samarali min/max (ombor sozlamasi yoki mahsulot): chegaradan pastdagilar sotuvi bo'lmasa ham kiradi
            limits = warehouse_limits(db, company_id, warehouse_id)
            sold_ids |= set(limits)
            limits.update(warehouse_limits(db, company_id, warehouse_id, {r.product_id for r in sales_rows}))
        products = {}
        if sold_ids:
            products = {p.id: p for p in db.query(Product).filter(
                Product.company_id == company_id, Product.id.in_(sold_ids), Product.is_deleted.isnot(True)).all()}
        wh_names = {}
        wh_ids = {r.warehouse_id for r in sales_rows if r.warehouse_id}
        if warehouse_id is not None:
            wh_ids.add(warehouse_id)
        if wh_ids:
            wh_names = {w.id: w.name for w in db.query(Warehouse.id, Warehouse.name).filter(
                Warehouse.id.in_(wh_ids), Warehouse.company_id == company_id).all()}

        po_items = []
        product_ids_needed = []
        # T4.4: ombor rejimida sotuvi yo'q, lekin chegaradan pastdagi mahsulotlar ham ko'rib chiqiladi
        entries = [(r.product_id, r.warehouse_id, float(r.total_sold_14d or 0)) for r in sales_rows]
        if warehouse_id is not None:
            seen = {r.product_id for r in sales_rows}
            entries += [(pid, warehouse_id, 0.0) for pid in limits if pid not in seen]

        for pid, row_wh, sold_14d in entries:
            prod = products.get(pid)
            if prod is None:
                continue
            daily_speed = sold_14d / history_days
            current_qty = stock_map.get((pid, row_wh), 0.0)
            lim = limits.get(pid) if warehouse_id is not None else None
            # Chegara bo'yicha yetishmovchilik (qoldiq min dan oshmagan bo'lsa): max bo'lsa max - qoldiq, bo'lmasa min - qoldiq
            level_need = 0.0
            if lim is not None and lim["min"] > 0 and current_qty <= float(lim["min"]):
                target = float(lim["max"]) if lim["max"] is not None else float(lim["min"])
                level_need = max(target - current_qty, 0.0)

            if daily_speed > 0 or level_need > 0:
                days_left = current_qty / daily_speed if daily_speed > 0 else 999

                # Agar urgent_only bo'lsa, faqat 3 kundan kam qolganlarini olamiz
                if urgent_only and days_left > 3 and level_need <= 0:
                    continue

                # Ehtiyoj: kelasi days_ahead kunga qancha kerak
                needed_for_period = daily_speed * days_ahead
                suggested_order_qty = max(needed_for_period - current_qty, level_need)

                if suggested_order_qty > 0:
                    if level_need > 0 and suggested_order_qty == level_need:
                        suggested_order_qty = max(1, int(suggested_order_qty + 0.5))
                    else:
                        # Kamida 10 ta yoki butun songa yaxlitlash
                        suggested_order_qty = max(10, int(suggested_order_qty + 0.5))

                    po_items.append({
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "warehouse_id": row_wh,
                        "warehouse_name": wh_names.get(row_wh),
                        "current_stock": current_qty,
                        "suggested_qty": suggested_order_qty,
                        "unit_cost": float(prod.cost_price or 0),
                        "estimated_cost": float(prod.cost_price or 0) * suggested_order_qty,
                        "supplier_id": None,
                        "supplier_name": None,
                    })
                    product_ids_needed.append(prod.id)

        if not po_items:
            return {"reply": f"{head}Hozircha omborda zaxiralar yetarli. Zayavka qilishga ehtiyoj yo'q."}

        # Mahsulot uchun avval bog'langan yetkazib beruvchi bo'lsa — avtomatik biriktiramiz
        if product_ids_needed:
            sp_rows = db.query(SupplierProduct).filter(
                SupplierProduct.product_id.in_(product_ids_needed)
            ).all()
            supplier_by_product = {}
            for sp in sp_rows:
                supplier_by_product.setdefault(sp.product_id, sp)
            for item in po_items:
                sp = supplier_by_product.get(item["product_id"])
                if sp:
                    item["supplier_id"] = sp.supplier_id
                    item["supplier_name"] = sp.supplier.name if sp.supplier else None
                    if sp.purchase_price:
                        item["unit_cost"] = float(sp.purchase_price)
                        item["estimated_cost"] = float(sp.purchase_price) * item["suggested_qty"]

        total_cost = sum(item["estimated_cost"] for item in po_items)
        missing_supplier = sum(1 for item in po_items if not item["supplier_id"])
        note = ""
        if missing_supplier:
            note = f" {missing_supplier} ta mahsulot uchun yetkazib beruvchi topilmadi — tasdiqlashda qo'lda tanlashingiz kerak bo'ladi."

        return {
            "reply": f"{head}Ombor tahlil qilindi. {len(po_items)} ta pozitsiya (mahsulot-ombor) bo'yicha zayavka qoralamasi tayyorlandi. Taxminiy xarajat: {total_cost:,.0f} so'm.{note} Tasdiqlash uchun ekranga chiqardim.",
            "action": {
                "type": "draft_purchase_order",
                "items": po_items,
                "total_estimated_cost": total_cost,
                "scope": scope_label(scope),
                "warehouse_id": warehouse_id,
            }
        }

@AIToolRegistry.register
class DraftSmsCampaignTool(AITool):
    name = "draft_sms_campaign"
    description = "Ma'lum mijozlar segmentiga (masalan: passiv mijozlar, qarzkorlar) SMS yuborish uchun kampaniya qoralamasini tayyorlash va tasdiqlash bilan yuborish."
    required_permission = "customers.marketing"
    risk_level = "HIGH"
    read_only = False
    parameters = {
        "type": "object",
        "properties": {
            "target_group": {
                "type": "string", 
                "enum": ["inactive", "churn_risk", "debtors"],
                "description": "Kimlarga jo'natiladi? inactive (passiv), churn_risk (yo'qolayotgan), debtors (qarzkorlar)."
            },
            "message_text": {
                "type": "string",
                "description": "SMS matni. AI bu matnni o'zi chiroyli qilib yozib berishi kerak."
            }
        },
        "required": ["target_group", "message_text"]
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        target_group = kwargs.get("target_group", "inactive")
        message_text = kwargs.get("message_text", "Assalomu alaykum! Siz uchun maxsus taklif!")
        
        query = db.query(Customer).filter(
            Customer.company_id == company_id, 
            Customer.phone != None,
            Customer.phone != ""
        )
        
        customers = []
        if target_group == "debtors":
            query = query.filter(Customer.debt_balance > 0)
            customers = query.all()
        elif target_group == "inactive":
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            subq = db.query(Sale.customer_id).filter(
                Sale.company_id == company_id, Sale.created_at >= cutoff, Sale.customer_id.isnot(None)
            ).subquery()
            query = query.filter(~Customer.id.in_(subq))
            customers = query.all()
        elif target_group == "churn_risk":
            cutoff = datetime.now(timezone.utc) - timedelta(days=45)
            # Find users who bought >= 3 times but not in last 45 days
            subq_recent = db.query(Sale.customer_id).filter(
                Sale.company_id == company_id, Sale.created_at >= cutoff, Sale.customer_id.isnot(None)
            ).subquery()
            subq_loyal = db.query(Sale.customer_id).filter(Sale.company_id == company_id).group_by(Sale.customer_id).having(func.count(Sale.id) >= 3).subquery()
            query = query.filter(~Customer.id.in_(subq_recent)).filter(Customer.id.in_(subq_loyal))
            customers = query.all()

        if not customers:
            return {"reply": f"'{target_group}' guruhiga mos keluvchi telefon raqamiga ega mijozlar topilmadi."}

        recipients = [{"id": c.id, "name": c.name, "phone": c.phone} for c in customers[:50]]

        # Tasdiqlangandan keyin haqiqiy jo'natish (Eskiz orqali) va SMSLog'ga yozish
        from app.models.sms_log import SMSLog
        from app.services import eskiz_service
        import asyncio

        sent, failed = 0, 0
        for r in recipients:
            phone = (r.get("phone") or "").strip()
            if not phone:
                failed += 1
                continue
            try:
                try:
                    res = asyncio.run(eskiz_service.send_sms(phone, message_text))
                except RuntimeError:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        res = pool.submit(asyncio.run, eskiz_service.send_sms(phone, message_text)).result()

                db.add(SMSLog(
                    company_id=company_id,
                    phone=phone,
                    message=message_text,
                    status="sent" if res.get("success") else "failed",
                    eskiz_id=res.get("eskiz_id"),
                    sms_type="ai_campaign",
                    error=res.get("error"),
                ))
                if res.get("success"):
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        db.commit()
        return {
            "reply": f"✅ {sent} ta mijozga SMS yuborildi." + (f" {failed} tasi yuborilmadi (xato)." if failed else ""),
            "sent": sent,
            "failed": failed,
        }


@AIToolRegistry.register
class SendCustomerSmsTool(AITool):
    name = "send_customer_sms"
    description = "Mijozlarga SMS xabarnoma yuborish (HIGH xavf darajasi, tasdiqlash talab qilinadi)."
    required_permission = "customers.marketing"
    risk_level = "HIGH"
    read_only = False
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "Mijoz ID si"},
            "target_group": {"type": "string", "enum": ["inactive", "churn_risk", "debtors"], "description": "Mijozlar guruhi"},
            "message_text": {"type": "string", "description": "SMS matni"}
        },
        "required": ["message_text"]
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        draft = DraftSmsCampaignTool()
        return draft.execute(db, company_id, user, **kwargs)

