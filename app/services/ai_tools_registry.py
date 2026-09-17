import time
import uuid
from typing import Dict, Any, Type, List
from sqlalchemy.orm import Session

from app.models.ai_audit import AIAuditLog
from app.models.user import User

class AITool:
    name: str = ""
    description: str = ""
    required_permission: str = ""
    risk_level: str = "LOW" # LOW, MEDIUM, HIGH
    parameters: dict = {}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        raise NotImplementedError()

class AIToolRegistry:
    _tools: Dict[str, Type[AITool]] = {}

    @classmethod
    def register(cls, tool_class: Type[AITool]):
        cls._tools[tool_class.name] = tool_class
        return tool_class

    @classmethod
    def get_tool(cls, name: str) -> Type[AITool]:
        return cls._tools.get(name)

    @classmethod
    def get_all_tools_for_llm(cls, user: User) -> List[dict]:
        from app.models.user import UserRole
        HIGH_RISK_ROLES = [UserRole.admin, UserRole.director, UserRole.super_admin]
        tools = []
        for name, tool_class in cls._tools.items():
            if tool_class.risk_level == "HIGH" and user and user.role not in HIGH_RISK_ROLES:
                continue
            if tool_class.risk_level == "MEDIUM" and user and user.role not in [UserRole.admin, UserRole.director, UserRole.super_admin, UserRole.manager]:
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_class.name,
                    "description": tool_class.description,
                    "parameters": tool_class.parameters
                }
            })
        return tools

    @classmethod
    def execute_tool(cls, db: Session, name: str, kwargs: dict, user: User, prompt: str = "", conversation_id: str = "") -> dict:
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        tool_class = cls.get_tool(name)
        if not tool_class:
            return {"reply": f"❌ '{name}' nomli funksiya topilmadi."}

        # Create audit log initially
        log = AIAuditLog(
            request_id=request_id,
            conversation_id=conversation_id,
            company_id=user.company_id,
            user_id=user.id,
            prompt=prompt,
            tool_name=name,
            tool_arguments=kwargs,
            permission=tool_class.required_permission,
            risk_level=tool_class.risk_level,
            status="PENDING",
            confirmation_required=(tool_class.risk_level == "HIGH"),
        )
        db.add(log)
        db.commit()

        # Permission check
        from app.models.user import UserRole
        HIGH_RISK_ROLES = [UserRole.admin, UserRole.director, UserRole.super_admin]
        has_permission = True  # LOW tools - default
        if tool_class.risk_level == "HIGH":
            has_permission = user.role in HIGH_RISK_ROLES
        elif tool_class.risk_level == "MEDIUM":
            has_permission = user.role in [UserRole.admin, UserRole.director, UserRole.super_admin, UserRole.manager] 
        if not has_permission:
            log.status = "ERROR"
            log.error = "Permission denied"
            db.commit()
            return {"reply": "❌ Kechirasiz, sizda bu amalni bajarish uchun ruxsat yo'q."}

        # Risk check
        if tool_class.risk_level == "HIGH":
            confirmation_id = str(uuid.uuid4())
            log.status = "PENDING_CONFIRMATION"
            log.confirmation_id = confirmation_id
            db.commit()
            
            # We return a structured draft indicating confirmation is needed
            return {
                "reply": "⚠️ Ushbu amalni bajarish uchun tasdiqlash talab qilinadi.",
                "action": {
                    "type": "confirm_action",
                    "confirmation_id": confirmation_id,
                    "tool_name": name,
                    "arguments": kwargs
                }
            }

        # Execution for LOW / MEDIUM
        try:
            tool_instance = tool_class()
            result = tool_instance.execute(db, user.company_id, user, **kwargs)
            
            log.status = "SUCCESS"
            log.result_summary = result.get("reply", "")
            
        except Exception as e:
            db.rollback()
            log.status = "ERROR"
            log.error = str(e)
            result = {"reply": f"❌ Xatolik yuz berdi: {str(e)}"}
            
        log.execution_time_ms = (time.time() - start_time) * 1000
        db.commit()
        
        return result

from app.models.customer import Customer
from sqlalchemy import or_
from datetime import datetime, timezone

def _sf(val):
    try: return float(val or 0)
    except: return 0.0

def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " so'm"

def _transliterate_to_latin(text):
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'j', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh', 'ъ': '',
        'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya', 'ў': "o'", 'ғ': "g'", 'қ': "q", 'ҳ': "h"
    }
    return "".join(mapping.get(c.lower(), c) for c in text)

def _transliterate_to_cyrillic(text):
    mapping = {
        'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е',
        'j': 'ж', 'z': 'з', 'i': 'и', 'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м',
        'n': 'н', 'o': 'о', 'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у',
        'f': 'ф', 'x': 'х', 'q': 'қ', 'h': 'ҳ'
    }
    res, i = "", 0
    while i < len(text):
        c = text[i].lower()
        if i < len(text) - 1:
            nxt = text[i+1].lower()
            if c == 'c' and nxt == 'h': res += 'ч'; i += 2; continue
            if c == 's' and nxt == 'h': res += 'ш'; i += 2; continue
            if c == 't' and nxt == 's': res += 'ц'; i += 2; continue
            if c == 'y' and nxt == 'o': res += 'ё'; i += 2; continue
            if c == 'y' and nxt == 'u': res += 'ю'; i += 2; continue
            if c == 'y' and nxt == 'a': res += 'я'; i += 2; continue
            if c == 'o' and nxt == "'": res += 'ў'; i += 2; continue
            if c == 'g' and nxt == "'": res += 'ғ'; i += 2; continue
        res += mapping.get(c, c)
        i += 1
    return res

def _find_customer(db: Session, company_id: int, name: str):
    name = name.strip()
    lat = _transliterate_to_latin(name)
    cyr = _transliterate_to_cyrillic(name)
    customers = db.query(Customer).filter(
        Customer.company_id == company_id,
        or_(
            Customer.name.ilike(f"%{name}%"),
            Customer.name.ilike(f"%{lat}%"),
            Customer.name.ilike(f"%{cyr}%")
        )
    ).all()
    if not customers: return None, f"❌ '{name}' ismli mijoz topilmadi."
    if len(customers) > 1:
        names = ", ".join(c.name for c in customers[:3])
        return None, f"⚠️ '{name}' so'ziga mos {len(customers)} ta mijoz topildi ({names}...). Iltimos, ismni to'liqroq yozing."
    return customers[0], None

def _format_debt(customer: Customer) -> str:
    parts = []
    if customer.debt_balances and isinstance(customer.debt_balances, dict):
        for cur, amt in customer.debt_balances.items():
            if float(amt) > 0: parts.append(f"{amt:,.0f} {cur}")
    if parts: return " va ".join(parts)
    return _fmt(_sf(customer.debt_balance))


@AIToolRegistry.register
class CheckCustomerDebtTool(AITool):
    name = "check_customer_debt"
    description = "Mijozning hozirgi qarzini bilish uchun ishlatiladi."
    required_permission = "customers.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "customer_name": {"type": "string", "description": "Qarzi tekshirilayotgan mijozning ismi."}
        },
        "required": ["customer_name"]
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        customer_name = kwargs.get("customer_name", "")
        customer, err = _find_customer(db, company_id, customer_name)
        if err: return {"reply": err}

        debt_amount = _sf(customer.debt_balance)
        if debt_amount <= 0:
            return {"reply": f"✅ {customer.name} ismli mijozning hech qanday qarzi yo'q."}
        else:
            return {"reply": f"⚠️ {customer.name} ismli mijozning joriy qarzdorligi: {_format_debt(customer)}."}


@AIToolRegistry.register
class RecordDebtPaymentTool(AITool):
    name = "record_debt_payment"
    description = "Mijoz qarzini/nasiyasini qaytarib to'laganda ishlatiladi."
    required_permission = "customers.payment"
    risk_level = "HIGH"
    parameters = {
        "type": "object",
        "properties": {
            "customer_name": {"type": "string", "description": "Qarzini to'lagan mijozning ismi."},
            "amount": {"type": "number", "description": "To'langan summa."}
        },
        "required": ["customer_name", "amount"]
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        # Note: This executes ONLY after confirmation now!
        customer_name = kwargs.get("customer_name", "")
        amount = _sf(kwargs.get("amount", 0))
        if amount <= 0:
            return {"reply": "❌ To'lov summasi musbat bo'lishi kerak."}

        customer, err = _find_customer(db, company_id, customer_name)
        if err: return {"reply": err}

        from app.models.moliya import Wallet, Transaction
        from sqlalchemy.orm.attributes import flag_modified
        
        wallet = db.query(Wallet).filter(
            Wallet.company_id == company_id, Wallet.is_open == True, Wallet.is_active == True
        ).first()

        old_balance = _sf(customer.debt_balance)
        new_balance = max(0, old_balance - amount)
        customer.debt_balance = new_balance
        
        if customer.debt_balances and "UZS" in customer.debt_balances:
            customer.debt_balances["UZS"] = max(0, float(customer.debt_balances["UZS"]) - amount)
            flag_modified(customer, "debt_balances")
        
        if wallet:
            wallet.balance = float(wallet.balance or 0) + amount

        tx = Transaction(
            company_id=company_id,
            branch_id=user.branch_id or 0,
            wallet_id=wallet.id if wallet else None,
            type="income",
            currency_code="UZS",
            payment_type="cash",
            reference_type="customer_payment",
            reference_id=customer.id,
            description=f"AI orqali qarz to'lovi: {customer.name}",
            amount=amount,
            user_id=user.id,
        )
        db.add(tx)
        
        return {
            "reply": (
                f"✅ Muvaffaqiyatli! {customer.name} mijozning qarzidan "
                f"{_fmt(amount)} yechib olindi va kassa to'lovi sifatida yozildi. "
                f"Qolgan qarz: {_format_debt(customer)}."
            ),
            "action": {"type": "debt_payment", "customer_id": customer.id, "amount": amount},
        }

@AIToolRegistry.register
class RecordNewDebtTool(AITool):
    name = "record_new_debt"
    description = "Mijoz do'kondan nasiyaga mol olib ketganda ishlatiladi."
    required_permission = "customers.edit_debt"
    risk_level = "HIGH"
    parameters = {
        "type": "object",
        "properties": {
            "customer_name": {"type": "string", "description": "Qarzga mol olgan mijozning ismi."},
            "amount": {"type": "number", "description": "Nasiya summasi."}
        },
        "required": ["customer_name", "amount"]
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        customer_name = kwargs.get("customer_name", "")
        amount = _sf(kwargs.get("amount", 0))
        if amount <= 0:
            return {"reply": "❌ Nasiya summasi musbat bo'lishi kerak."}

        customer, err = _find_customer(db, company_id, customer_name)
        if err: return {"reply": err}

        from sqlalchemy.orm.attributes import flag_modified
        old_balance = _sf(customer.debt_balance)
        new_balance = old_balance + amount
        
        if customer.debt_balances:
            customer.debt_balances["UZS"] = float(customer.debt_balances.get("UZS", 0)) + amount
            flag_modified(customer, "debt_balances")
        
        history = list(customer.debt_edited or [])
        history.append({
            "edited_from": {"UZS": old_balance},
            "edited_to": {"UZS": new_balance},
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "reason": "AI orqali nasiya qo'shish"
        })
        customer.debt_edited = history
        flag_modified(customer, "debt_edited")
        customer.debt_balance = new_balance

        return {
            "reply": (
                f"📝 Muvaffaqiyatli! {customer.name} hisobiga "
                f"{_fmt(amount)} nasiya yozildi. "
                f"Jami qarz: {_format_debt(customer)}."
            ),
            "action": {"type": "add_debt", "customer_id": customer.id, "amount": amount},
        }
import app.services.ai_tools_customers
import app.services.ai_tools_products
import app.services.ai_tools_actions
import app.services.ai_tools_crud
import app.services.ai_tools_sales

# ───────────────────────────────────────────────
# Yangi AI Toollar
# ───────────────────────────────────────────────
from datetime import date, timedelta
from sqlalchemy import func as sqlfunc

@AIToolRegistry.register
class GetSalesSummaryTool(AITool):
    name = "get_sales_summary"
    description = "Bugungi yoki boshqa kun uchun savdo xulosasini ko'rsatadi: jami tushum, buyurtmalar soni, naqd va karta to'lovlari."
    required_permission = "sales.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "period": {"type": "string", "description": "'today', 'yesterday', 'week', 'month' - davr", "enum": ["today", "yesterday", "week", "month"]}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.sale import Sale, SaleStatus
        period = kwargs.get("period", "today")
        today = date.today()
        if period == "yesterday":
            d = today - timedelta(days=1)
            date_filter = sqlfunc.date(Sale.created_at) == d
        elif period == "week":
            d = today - timedelta(days=6)
            date_filter = sqlfunc.date(Sale.created_at) >= d
        elif period == "month":
            d = today - timedelta(days=29)
            date_filter = sqlfunc.date(Sale.created_at) >= d
        else:
            date_filter = sqlfunc.date(Sale.created_at) == today

        sales = db.query(Sale).filter(
            date_filter, Sale.company_id == company_id, Sale.status == SaleStatus.completed
        ).all()

        total = sum(_sf(s.total_amount) for s in sales)
        cash = sum(_sf(s.paid_cash) for s in sales)
        card = sum(_sf(s.paid_card) for s in sales)
        count = len(sales)
        period_names = {"today": "Bugun", "yesterday": "Kecha", "week": "Oxirgi 7 kun", "month": "Oxirgi 30 kun"}
        pname = period_names.get(period, "Bugun")

        if count == 0:
            return {"reply": f"📊 {pname} uchun hech qanday sotuv topilmadi."}

        return {
            "reply": (
                f"📊 {pname} savdo xulosasi:\n"
                f"• Jami tushum: {_fmt(total)}\n"
                f"• Buyurtmalar: {count} ta\n"
                f"• Naqd: {_fmt(cash)}\n"
                f"• Karta: {_fmt(card)}"
            ),
            "action": {"type": "show_data", "data": {"total": total, "count": count}}
        }

@AIToolRegistry.register
class GetTopProductsTool(AITool):
    name = "get_top_products"
    description = "Eng ko'p sotilgan mahsulotlar ro'yxatini ko'rsatadi."
    required_permission = "products.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Ko'rsatiladigan mahsulotlar soni (default: 5)"}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.sale import SaleItem, Sale, SaleStatus
        from app.models.product import Product
        limit = min(int(kwargs.get("limit", 5)), 10)
        today = date.today()
        start = today - timedelta(days=29)

        results = db.query(
            Product.name,
            sqlfunc.sum(SaleItem.quantity).label("qty"),
            sqlfunc.sum(SaleItem.subtotal).label("revenue")
        ).join(SaleItem, Product.id == SaleItem.product_id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(
            Sale.company_id == company_id,
            Sale.status == SaleStatus.completed,
            sqlfunc.date(Sale.created_at) >= start
         ).group_by(Product.name).order_by(sqlfunc.sum(SaleItem.quantity).desc()).limit(limit).all()

        if not results:
            return {"reply": "📦 Oxirgi 30 kunda hech qanday sotuv topilmadi."}

        lines = []
        for i, (name, qty, rev) in enumerate(results, 1):
            lines.append(f"{i}. {name} — {int(qty or 0)} ta, {_fmt(_sf(rev))}")

        return {
            "reply": f"🏆 Eng ko'p sotilgan {limit} ta mahsulot (oxirgi 30 kun):\n" + "\n".join(lines),
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetLowStockTool(AITool):
    name = "get_low_stock"
    description = "Zaxirasi kam (tugayotgan) mahsulotlarni ko'rsatadi."
    required_permission = "products.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "description": "Minimal zaxira chegarasi (default: 10)"}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.product import Product
        from app.models.inventory import StockLevel
        threshold = int(kwargs.get("threshold", 10))

        low_items = db.query(
            Product.name,
            sqlfunc.sum(StockLevel.quantity).label("qty")
        ).join(StockLevel, Product.id == StockLevel.product_id)\
         .filter(Product.company_id == company_id)\
         .group_by(Product.id, Product.name)\
         .having(sqlfunc.sum(StockLevel.quantity) < threshold)\
         .order_by(sqlfunc.sum(StockLevel.quantity)).limit(15).all()

        if not low_items:
            return {"reply": f"✅ Zaxirasi {threshold} tadan kam bo'lgan mahsulot topilmadi. Ombor to'la!"}

        lines = [f"{i}. {name} — {int(qty or 0)} ta" for i, (name, qty) in enumerate(low_items, 1)]
        return {
            "reply": f"⚠️ Tugayotgan {len(lines)} ta mahsulot (zaxirasi {threshold} tadan kam):\n" + "\n".join(lines),
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetDebtorsListTool(AITool):
    name = "get_debtors_list"
    description = "Qarz summasi bo'yicha eng yirik qarzdorlar ro'yxatini ko'rsatadi."
    required_permission = "customers.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "min_amount": {"type": "number", "description": "Minimal qarz summasi (default: 0)"},
            "limit": {"type": "integer", "description": "Ko'rsatiladigan mijozlar soni (default: 10)"}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.customer import Customer
        min_amount = _sf(kwargs.get("min_amount", 0))
        limit = min(int(kwargs.get("limit", 10)), 20)

        debtors = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.debt_balance > min_amount
        ).order_by(Customer.debt_balance.desc()).limit(limit).all()

        if not debtors:
            return {"reply": "✅ Qarz chegarasidan yuqori mijoz topilmadi."}

        lines = []
        for i, c in enumerate(debtors, 1):
            lines.append(f"{i}. {c.name} — {_format_debt(c)}")

        return {
            "reply": f"📋 Qarzdorlar ro'yxati ({len(lines)} ta mijoz):\n" + "\n".join(lines),
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register
class GetProfitTodayTool(AITool):
    name = "get_profit_today"
    description = "Bugungi yoki boshqa davr uchun foyda (sotish narxi - xarid narxi) hisoblab ko'rsatadi."
    required_permission = "sales.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "period": {"type": "string", "description": "'today', 'yesterday', 'week', 'month'", "enum": ["today", "yesterday", "week", "month"]}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.sale import Sale, SaleItem, SaleStatus
        period = kwargs.get("period", "today")
        today = date.today()
        if period == "yesterday":
            d = today - timedelta(days=1)
            date_filter = sqlfunc.date(Sale.created_at) == d
        elif period == "week":
            date_filter = sqlfunc.date(Sale.created_at) >= today - timedelta(days=6)
        elif period == "month":
            date_filter = sqlfunc.date(Sale.created_at) >= today - timedelta(days=29)
        else:
            date_filter = sqlfunc.date(Sale.created_at) == today

        items = db.query(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).filter(
            date_filter, Sale.company_id == company_id, Sale.status == SaleStatus.completed
        ).all()

        revenue = sum(_sf(i.subtotal) for i in items)
        cost = sum(_sf(i.cost_price or 0) * _sf(i.quantity) for i in items)
        profit = revenue - cost
        margin = (profit / revenue * 100) if revenue > 0 else 0

        period_names = {"today": "Bugun", "yesterday": "Kecha", "week": "Oxirgi 7 kun", "month": "Oxirgi 30 kun"}
        pname = period_names.get(period, "Bugun")

        return {
            "reply": (
                f"💰 {pname} foyda hisobi:\n"
                f"• Jami tushum: {_fmt(revenue)}\n"
                f"• Tannarx: {_fmt(cost)}\n"
                f"• Sof foyda: {_fmt(profit)}\n"
                f"• Marja: {margin:.1f}%"
            ),
            "action": {"type": "show_data", "data": {"revenue": revenue, "profit": profit, "margin": margin}}
        }

@AIToolRegistry.register
class FindProductInfoTool(AITool):
    name = "find_product_info"
    description = "Mahsulot nomi bo'yicha narxi, zaxirasi va boshqa ma'lumotlarini ko'rsatadi."
    required_permission = "products.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "Qidirilayotgan mahsulot nomi"}
        },
        "required": ["product_name"]
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.product import Product
        from app.models.inventory import StockLevel
        name = kwargs.get("product_name", "").strip()
        products = db.query(Product).filter(
            Product.company_id == company_id,
            Product.name.ilike(f"%{name}%")
        ).limit(5).all()

        if not products:
            return {"reply": f"❌ '{name}' nomli mahsulot topilmadi."}

        lines = []
        for p in products:
            stock_qty = db.query(sqlfunc.sum(StockLevel.quantity)).filter(
                StockLevel.product_id == p.id
            ).scalar() or 0
            price = _sf(p.sale_price)
            lines.append(f"📦 {p.name}\n   Narxi: {_fmt(price)} | Zaxira: {int(stock_qty)} ta")

        return {
            "reply": "\n\n".join(lines),
            "action": {"type": "show_data"}
        }

@AIToolRegistry.register  
class GetNewCustomersStatTool(AITool):
    name = "get_new_customers_stat"
    description = "Yangi qo'shilgan mijozlar statistikasini ko'rsatadi."
    required_permission = "customers.view"
    risk_level = "LOW"
    parameters = {
        "type": "object",
        "properties": {
            "period": {"type": "string", "description": "'today', 'week', 'month'", "enum": ["today", "week", "month"]}
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.customer import Customer
        period = kwargs.get("period", "week")
        today = date.today()
        if period == "today":
            d = today
            date_filter = sqlfunc.date(Customer.created_at) == d
        elif period == "month":
            d = today - timedelta(days=29)
            date_filter = sqlfunc.date(Customer.created_at) >= d
        else:
            d = today - timedelta(days=6)
            date_filter = sqlfunc.date(Customer.created_at) >= d

        count = db.query(sqlfunc.count(Customer.id)).filter(
            Customer.company_id == company_id,
            date_filter
        ).scalar() or 0

        total = db.query(sqlfunc.count(Customer.id)).filter(
            Customer.company_id == company_id
        ).scalar() or 0

        period_names = {"today": "bugun", "week": "oxirgi 7 kunda", "month": "oxirgi 30 kunda"}
        pname = period_names.get(period, "oxirgi 7 kunda")

        return {
            "reply": f"👥 {pname.capitalize()} {count} ta yangi mijoz qo'shildi. Jami mijozlar: {total} ta.",
            "action": {"type": "show_data", "data": {"new": count, "total": total}}
        }
