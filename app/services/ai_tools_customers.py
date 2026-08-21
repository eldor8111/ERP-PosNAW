from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.models.customer import Customer
from app.models.sale import Sale, SaleStatus
from app.services.ai_tools_registry import AITool, AIToolRegistry

@AIToolRegistry.register
class GetTopCustomersTool(AITool):
    name = "get_top_customers"
    description = "Eng ko'p xarid qilgan (eng yaxshi) mijozlar ro'yxatini va ularning statistikasini olish."
    required_permission = "customers.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Nechta mijozni chiqarish kerak (masalan, eng yaxshi 5 ta mijoz uchun 5). Standart: 10."},
            "days": {"type": "integer", "description": "Oxirgi necha kunlik holat bo'yicha hisoblansin? Standart: 30 kunga."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        limit = kwargs.get("limit", 10)
        days = kwargs.get("days", 30)
        
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = db.query(
            Customer.name,
            func.count(Sale.id).label("total_orders"),
            func.sum(Sale.total_amount).label("total_spent")
        ).join(Sale, Sale.customer_id == Customer.id)\
         .filter(
            Customer.company_id == company_id,
            Sale.company_id == company_id,
            Sale.status != SaleStatus.cancelled,
            Sale.created_at >= start_date
        ).group_by(Customer.id)\
         .order_by(desc("total_spent"))\
         .limit(limit).all()

        if not results:
            return {"reply": f"Oxirgi {days} kun ichida hech qanday mijoz xarid amalga oshirmagan."}

        customers_data = []
        for row in results:
            customers_data.append({
                "name": row.name,
                "total_orders": int(row.total_orders),
                "total_spent": float(row.total_spent or 0)
            })

        return {
            "reply": {"customers": customers_data, "days_checked": days},
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetInactiveCustomersTool(AITool):
    name = "get_inactive_customers"
    description = "Uzoq vaqtdan beri umuman xarid qilmagan (passiv) mijozlarni topish."
    required_permission = "customers.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "days_inactive": {"type": "integer", "description": "Mijoz oxirgi marta xarid qilganidan beri kamida necha kun o'tgan bo'lishi kerak? Standart: 30."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        days_inactive = kwargs.get("days_inactive", 30)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_inactive)

        subquery = db.query(
            Sale.customer_id,
            func.max(Sale.created_at).label("last_sale_date")
        ).filter(Sale.company_id == company_id).group_by(Sale.customer_id).subquery()

        results = db.query(
            Customer.name,
            subquery.c.last_sale_date
        ).join(subquery, subquery.c.customer_id == Customer.id)\
         .filter(
             Customer.company_id == company_id,
             subquery.c.last_sale_date < cutoff_date
         ).order_by(subquery.c.last_sale_date.asc()).limit(15).all()

        if not results:
            return {"reply": f"Barcha doimiy mijozlaringiz oxirgi {days_inactive} kunda xarid qilishgan. Passiv mijozlar yo'q."}

        customers_data = []
        for row in results:
            customers_data.append({
                "name": row.name,
                "last_purchase": row.last_sale_date.strftime("%Y-%m-%d") if row.last_sale_date else "Unknown",
                "days_since": (datetime.now(timezone.utc).date() - row.last_sale_date.date()).days if row.last_sale_date else "Unknown"
            })

        return {
            "reply": {"inactive_customers": customers_data, "inactive_threshold_days": days_inactive},
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetChurnRiskCustomersTool(AITool):
    name = "get_churn_risk_customers"
    description = "Yo'qolib ketish xavfi ostida bo'lgan (churn risk) ya'ni oldin yaxshi xarid qilib, hozir pasaygan mijozlarni topish."
    required_permission = "customers.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {}
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        # Churn logic: purchased more than 2 times, but hasn't purchased in the last 45 days.
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=45)

        subquery = db.query(
            Sale.customer_id,
            func.max(Sale.created_at).label("last_sale_date"),
            func.count(Sale.id).label("total_sales")
        ).filter(Sale.company_id == company_id).group_by(Sale.customer_id).subquery()

        results = db.query(
            Customer.name,
            subquery.c.last_sale_date,
            subquery.c.total_sales
        ).join(subquery, subquery.c.customer_id == Customer.id)\
         .filter(
             Customer.company_id == company_id,
             subquery.c.last_sale_date < cutoff_date,
             subquery.c.total_sales >= 3
         ).order_by(subquery.c.last_sale_date.asc()).limit(15).all()

        if not results:
            return {"reply": "Ayni vaqtda yo'qolib ketish xavfi yuqori bo'lgan (churn risk) mijozlar aniqlanmadi."}

        customers_data = []
        for row in results:
            customers_data.append({
                "name": row.name,
                "total_sales": int(row.total_sales),
                "last_purchase": row.last_sale_date.strftime("%Y-%m-%d") if row.last_sale_date else "Unknown",
            })

        return {
            "reply": {"churn_risk_customers": customers_data},
            "action": {"type": "show_data"}
        }
