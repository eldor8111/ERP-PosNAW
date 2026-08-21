from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.inventory import StockLevel
from app.services.ai_tools_registry import AITool, AIToolRegistry

@AIToolRegistry.register
class GetTopProductsTool(AITool):
    name = "get_top_products"
    description = "Eng ko'p sotilgan mahsulotlarni (dona yoki summa bo'yicha) ko'rsatish."
    required_permission = "products.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Nechta mahsulotni chiqarish kerak? Standart: 10."},
            "days": {"type": "integer", "description": "Oxirgi necha kun hisobga olinsin? Standart: 30."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        limit = kwargs.get("limit", 10)
        days = kwargs.get("days", 30)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = db.query(
            Product.name,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.sum(SaleItem.subtotal).label("total_revenue")
        ).join(SaleItem, SaleItem.product_id == Product.id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(
            Product.company_id == company_id,
            Sale.company_id == company_id,
            Sale.status != SaleStatus.cancelled,
            Sale.created_at >= start_date
        ).group_by(Product.id)\
         .order_by(desc("total_qty"))\
         .limit(limit).all()

        if not results:
            return {"reply": f"Oxirgi {days} kun ichida hech qanday mahsulot sotilmagan."}

        products_data = []
        for row in results:
            products_data.append({
                "name": row.name,
                "total_sold_qty": float(row.total_qty or 0),
                "total_revenue": float(row.total_revenue or 0)
            })

        return {
            "reply": {"top_products": products_data, "days_checked": days},
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetLowStockProductsTool(AITool):
    name = "get_low_stock"
    description = "Omborda qoldig'i kam qolgan yoki tugab qolgan mahsulotlarni topish."
    required_permission = "inventory.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "description": "Nechta donadan kam qolganlari ko'rsatilsin? Standart: 10"}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        threshold = kwargs.get("threshold", 10)

        results = db.query(
            Product.name,
            func.sum(StockLevel.quantity).label("total_stock")
        ).join(StockLevel, StockLevel.product_id == Product.id)\
         .filter(Product.company_id == company_id)\
         .group_by(Product.id)\
         .having(func.sum(StockLevel.quantity) <= threshold)\
         .order_by(func.sum(StockLevel.quantity).asc())\
         .limit(20).all()

        if not results:
            return {"reply": f"Omborda zaxirasi {threshold} dan kam bo'lgan mahsulotlar yo'q."}

        products_data = []
        for row in results:
            products_data.append({
                "name": row.name,
                "stock_quantity": float(row.total_stock or 0)
            })

        return {
            "reply": {"low_stock_products": products_data, "threshold": threshold},
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class PredictStockDepletionTool(AITool):
    name = "predict_stock_depletion"
    description = "Qaysi mahsulotlar yaqin kunlarda tugashini (sotilish tezligiga qarab) bashorat qilish."
    required_permission = "inventory.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "days_ahead": {"type": "integer", "description": "Kelasi necha kun ichida tugaydigan mahsulotlar ko'rsatilsin? Standart: 7."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        days_ahead = kwargs.get("days_ahead", 7)
        # 14 kunlik savdo tezligini (sotilish sur'atini) hisoblaymiz
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
            Product.name,
            sales_subquery.c.total_sold_14d,
            stock_subquery.c.current_stock
        ).join(sales_subquery, sales_subquery.c.product_id == Product.id)\
         .join(stock_subquery, stock_subquery.c.product_id == Product.id)\
         .filter(
             Product.company_id == company_id,
             sales_subquery.c.total_sold_14d > 0
         ).all()

        predictions = []
        for row in results:
            daily_speed = float(row.total_sold_14d) / history_days
            current_qty = float(row.current_stock or 0)
            
            if daily_speed > 0:
                days_left = current_qty / daily_speed
                if days_left <= days_ahead:
                    predictions.append({
                        "name": row.name,
                        "current_stock": current_qty,
                        "daily_sales_speed": round(daily_speed, 1),
                        "estimated_days_left": round(days_left, 1)
                    })
        
        # Sort by days_left asc
        predictions.sort(key=lambda x: x["estimated_days_left"])
        # Take top 15 most urgent
        predictions = predictions[:15]

        if not predictions:
            return {"reply": f"Hozirgi sotilish sur'atiga ko'ra, kelasi {days_ahead} kun ichida hech qanday mahsulot tugamaydi."}

        return {
            "reply": {"depletion_prediction": predictions, "days_ahead": days_ahead},
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetProductProfitTool(AITool):
    name = "get_product_profit"
    description = "Sotilgan mahsulotlarning keltirgan foydasi va marjasini hisoblash (daromad tahlili)."
    required_permission = "products.analytics"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Standart: 10 ta"},
            "days": {"type": "integer", "description": "Standart: 30 kunga."}
        }
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        limit = kwargs.get("limit", 10)
        days = kwargs.get("days", 30)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = db.query(
            Product.name,
            func.sum(SaleItem.quantity).label("qty"),
            func.sum(SaleItem.subtotal).label("revenue"),
            # Cost price * quantity = Total Cost
            func.sum(Product.buy_price * SaleItem.quantity).label("total_cost")
        ).join(SaleItem, SaleItem.product_id == Product.id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(
            Product.company_id == company_id,
            Sale.company_id == company_id,
            Sale.status != SaleStatus.cancelled,
            Sale.created_at >= start_date
        ).group_by(Product.id)\
         .order_by(desc("revenue"))\
         .limit(limit).all()

        if not results:
            return {"reply": f"Oxirgi {days} kun ichida sotuv bo'lmagan."}

        profits_data = []
        for row in results:
            rev = float(row.revenue or 0)
            cost = float(row.total_cost or 0)
            profit = rev - cost
            margin = (profit / rev * 100) if rev > 0 else 0
            
            profits_data.append({
                "name": row.name,
                "quantity": float(row.qty or 0),
                "revenue": rev,
                "profit": profit,
                "margin_percent": round(margin, 1)
            })

        # Sort by profit desc instead of revenue
        profits_data.sort(key=lambda x: x["profit"], reverse=True)

        return {
            "reply": {"profit_analysis": profits_data, "days_checked": days},
            "action": {"type": "show_data"}
        }
