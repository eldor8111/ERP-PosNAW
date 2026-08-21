from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.sale import Sale, SaleItem, SaleStatus
from app.services.ai_tools_registry import AITool, AIToolRegistry

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
            "urgent_only": {"type": "boolean", "description": "Faqat hozir yoki yaqin 3 kunda tugaydiganlari olinsinmi? Standart: false."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        days_ahead = kwargs.get("days_ahead", 14)
        urgent_only = kwargs.get("urgent_only", False)
        
        history_days = 14
        start_date = datetime.now(timezone.utc) - timedelta(days=history_days)

        sales_subquery = db.query(
            SaleItem.product_id,
            func.sum(SaleItem.quantity).label("total_sold_14d")
        ).join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(Sale.company_id == company_id, Sale.status != SaleStatus.cancelled, Sale.created_at >= start_date)\
         .group_by(SaleItem.product_id).subquery()

        stock_subquery = db.query(
            StockLevel.product_id,
            func.sum(StockLevel.quantity).label("current_stock")
        ).join(Product, Product.id == StockLevel.product_id)\
         .filter(Product.company_id == company_id)\
         .group_by(StockLevel.product_id).subquery()

        results = db.query(
            Product.id,
            Product.name,
            Product.buy_price,
            sales_subquery.c.total_sold_14d,
            stock_subquery.c.current_stock
        ).join(sales_subquery, sales_subquery.c.product_id == Product.id)\
         .outerjoin(stock_subquery, stock_subquery.c.product_id == Product.id)\
         .filter(Product.company_id == company_id).all()

        po_items = []
        for row in results:
            daily_speed = float(row.total_sold_14d or 0) / history_days
            current_qty = float(row.current_stock or 0)
            
            if daily_speed > 0:
                days_left = current_qty / daily_speed if daily_speed > 0 else 999
                
                # Agar urgent_only bo'lsa, faqat 3 kundan kam qolganlarini olamiz
                if urgent_only and days_left > 3:
                    continue
                    
                # Ehtiyoj: kelasi days_ahead kunga qancha kerak
                needed_for_period = daily_speed * days_ahead
                suggested_order_qty = needed_for_period - current_qty
                
                if suggested_order_qty > 0:
                    # Kamida 10 ta yoki butun songa yaxlitlash
                    suggested_order_qty = max(10, int(suggested_order_qty + 0.5))
                    
                    po_items.append({
                        "product_id": row.id,
                        "product_name": row.name,
                        "current_stock": current_qty,
                        "suggested_qty": suggested_order_qty,
                        "estimated_cost": float(row.buy_price or 0) * suggested_order_qty
                    })

        if not po_items:
            return {"reply": "Hozircha omborda zaxiralar yetarli. Zayavka qilishga ehtiyoj yo'q."}

        total_cost = sum(item["estimated_cost"] for item in po_items)
        
        return {
            "reply": f"Ombor tahlil qilindi. {len(po_items)} ta mahsulot bo'yicha zayavka qoralamasi tayyorlandi. Taxminiy xarajat: {total_cost:,.0f} so'm. Tasdiqlash uchun ekranga chiqardim.",
            "action": {
                "type": "draft_purchase_order",
                "items": po_items,
                "total_estimated_cost": total_cost
            }
        }

@AIToolRegistry.register
class DraftSmsCampaignTool(AITool):
    name = "draft_sms_campaign"
    description = "Ma'lum mijozlar segmentiga (masalan: passiv mijozlar, qarzkorlar) SMS yuborish uchun kampaniya qoralamasini tayyorlash."
    required_permission = "customers.marketing"
    risk_level = "MEDIUM"
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
            Customer.phone_number != None,
            Customer.phone_number != ""
        )
        
        customers = []
        if target_group == "debtors":
            query = query.filter(Customer.debt_balance > 0)
            customers = query.all()
        elif target_group == "inactive":
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            subq = db.query(Sale.customer_id).filter(Sale.company_id == company_id, Sale.created_at >= cutoff).subquery()
            query = query.filter(~Customer.id.in_(subq))
            customers = query.all()
        elif target_group == "churn_risk":
            cutoff = datetime.now(timezone.utc) - timedelta(days=45)
            # Find users who bought >= 3 times but not in last 45 days
            subq_recent = db.query(Sale.customer_id).filter(Sale.company_id == company_id, Sale.created_at >= cutoff).subquery()
            subq_loyal = db.query(Sale.customer_id).filter(Sale.company_id == company_id).group_by(Sale.customer_id).having(func.count(Sale.id) >= 3).subquery()
            
            query = query.filter(~Customer.id.in_(subq_recent)).filter(Customer.id.in_(subq_loyal))
            customers = query.all()

        if not customers:
            return {"reply": f"'{target_group}' guruhiga mos keluvchi telefon raqamiga ega mijozlar topilmadi."}

        recipients = [{"id": c.id, "name": c.name, "phone": c.phone_number} for c in customers[:50]] # Limit for draft safety

        return {
            "reply": f"{len(recipients)} ta mijoz ('{target_group}' guruhi) uchun SMS kampaniya qoralamasi tayyorlandi. Matn: '{message_text}'. Tasdiqlash uchun ro'yxatni ekranga chiqardim.",
            "action": {
                "type": "draft_sms_campaign",
                "recipients": recipients,
                "message": message_text,
                "recipient_count": len(recipients)
            }
        }
