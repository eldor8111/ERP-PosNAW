import time
import uuid
from typing import Dict, Any, Type, List
from sqlalchemy.orm import Session

from datetime import datetime, timezone, timedelta
from app.models.ai_audit import AIAuditLog
from app.models.pending_action import PendingAction
from app.models.user import User
from app.config import settings

class AITool:
    name: str = ""
    description: str = ""
    required_permission: str = ""
    risk_level: str = "LOW" # LOW, MEDIUM, HIGH
    read_only: bool = False
    parameters: dict = {}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        raise NotImplementedError()

def _sf(val):
    try: return float(val or 0)
    except: return 0.0

def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " so'm"

def summarize_reply(result: dict) -> str:
    """Audit jurnali uchun javob matni: ba'zi vositalar reply ni dict qaytaradi,
    result_summary esa Text ustun — dict yozilsa commit xato beradi."""
    reply = (result or {}).get("reply", "")
    if isinstance(reply, str):
        return reply
    import json
    return json.dumps(reply, ensure_ascii=False, default=str)


def generate_action_card_summary(tool_name: str, kwargs: dict) -> str:
    """Foydalanuvchiga tasdiqlash kartochkasida ko'rsatiladigan tushunarli xulosa."""
    kwargs = kwargs or {}
    if tool_name == "create_product":
        name = kwargs.get("name", "Noma'lum")
        price = _sf(kwargs.get("sale_price", 0))
        return f"Yangi mahsulot yaratish: '{name}' — sotuv narxi: {_fmt(price)}"
    elif tool_name == "update_product":
        p_name = kwargs.get("product_name", "Noma'lum")
        parts = []
        if kwargs.get("new_name"):
            parts.append(f"nomi: '{kwargs.get('new_name')}'")
        if kwargs.get("new_sale_price") is not None:
            parts.append(f"sotuv narxi: {_fmt(_sf(kwargs.get('new_sale_price')))}")
        if kwargs.get("new_cost_price") is not None:
            parts.append(f"tan narxi: {_fmt(_sf(kwargs.get('new_cost_price')))}")
        details = ", ".join(parts) if parts else "o'zgarishlar bilan"
        return f"Mahsulotni yangilash: '{p_name}' ({details})"
    elif tool_name == "create_customer":
        name = kwargs.get("name", "Noma'lum")
        phone = kwargs.get("phone")
        phone_str = f", tel: {phone}" if phone else ""
        return f"Yangi mijoz qo'shish: '{name}'{phone_str}"
    elif tool_name == "update_customer":
        c_name = kwargs.get("customer_name", "Noma'lum")
        parts = []
        if kwargs.get("new_name"):
            parts.append(f"yangi ism: '{kwargs.get('new_name')}'")
        if kwargs.get("new_phone"):
            parts.append(f"yangi tel: {kwargs.get('new_phone')}")
        details = ", ".join(parts) if parts else "o'zgarishlar bilan"
        return f"Mijoz ma'lumotlarini yangilash: '{c_name}' ({details})"
    elif tool_name == "create_sale":
        items = kwargs.get("items") or []
        pt = kwargs.get("payment_type", "cash")
        cust = kwargs.get("customer_name")
        cust_str = f", mijoz: '{cust}'" if cust else ""
        return f"Sotuv rasmiylashtirish: {len(items)} xil mahsulot, to'lov turi: {pt}{cust_str}"
    elif tool_name == "record_debt_payment":
        c_name = kwargs.get("customer_name", "Noma'lum")
        amount = _sf(kwargs.get("amount", 0))
        return f"Qarz to'lovi qabul qilish: '{c_name}' dan {_fmt(amount)}"
    elif tool_name == "record_new_debt":
        c_name = kwargs.get("customer_name", "Noma'lum")
        amount = _sf(kwargs.get("amount", 0))
        return f"Nasiya (qarz) yozish: '{c_name}' ga {_fmt(amount)}"
    elif tool_name in ("draft_sms_campaign", "send_customer_sms"):
        recipients = kwargs.get("recipients") or kwargs.get("customer_ids") or []
        count = kwargs.get("recipient_count") or len(recipients) or kwargs.get("count") or (1 if kwargs.get("customer_id") else 0)
        msg = kwargs.get("message") or kwargs.get("message_text") or ""
        msg_preview = (msg[:60] + "...") if len(msg) > 60 else msg
        target = kwargs.get("target_group", "")
        target_str = f" ('{target}' guruhi)" if target else ""
        cnt_str = f"{count} ta mijozga" if count else "mijozlarga"
        return f"SMS yuborish: {cnt_str}{target_str}. Xabar namunasi: '{msg_preview}'"
    else:
        return f"Amal: {tool_name}"


def validate_arguments_company_ownership(db: Session, company_id: int, kwargs: dict) -> None:
    """
    Argumentlardagi barcha ID'lar (customer_id, product_id, warehouse_id, supplier_id,
    va items ro'yxati) shu kompaniyaga tegishli ekanini qat'iy tekshiradi.
    Agar boshqa korxonaga tegishli ID topilsa, PermissionError chiqaradi.
    """
    if not kwargs or not isinstance(kwargs, dict):
        return

    from app.models.customer import Customer
    from app.models.product import Product
    from app.models.warehouse import Warehouse
    from app.models.supplier import Supplier

    # 1. Customer ID
    cid = kwargs.get("customer_id")
    if cid:
        cust = db.query(Customer).filter(Customer.id == cid).first()
        if not cust or cust.company_id != company_id:
            raise PermissionError(f"Mijoz (ID={cid}) ushbu korxonaga tegishli emas.")

    # 2. Product ID (to'g'ridan yoki items ichida)
    pid = kwargs.get("product_id")
    if pid:
        prod = db.query(Product).filter(Product.id == pid).first()
        if not prod or prod.company_id != company_id:
            raise PermissionError(f"Mahsulot (ID={pid}) ushbu korxonaga tegishli emas.")

    items = kwargs.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item_pid = item.get("product_id")
                if item_pid:
                    prod = db.query(Product).filter(Product.id == item_pid).first()
                    if not prod or prod.company_id != company_id:
                        raise PermissionError(f"Mahsulot (ID={item_pid}) ushbu korxonaga tegishli emas.")
                item_wid = item.get("warehouse_id")
                if item_wid:
                    wh = db.query(Warehouse).filter(Warehouse.id == item_wid).first()
                    if not wh or wh.company_id != company_id:
                        raise PermissionError(f"Ombor (ID={item_wid}) ushbu korxonaga tegishli emas.")
                item_sid = item.get("supplier_id")
                if item_sid:
                    sup = db.query(Supplier).filter(Supplier.id == item_sid).first()
                    if not sup or sup.company_id != company_id:
                        raise PermissionError(f"Yetkazib beruvchi (ID={item_sid}) ushbu korxonaga tegishli emas.")

    # 3. Warehouse ID
    wid = kwargs.get("warehouse_id")
    if wid:
        wh = db.query(Warehouse).filter(Warehouse.id == wid).first()
        if not wh or wh.company_id != company_id:
            raise PermissionError(f"Ombor (ID={wid}) ushbu korxonaga tegishli emas.")

    # 4. Supplier ID
    sid = kwargs.get("supplier_id")
    if sid:
        sup = db.query(Supplier).filter(Supplier.id == sid).first()
        if not sup or sup.company_id != company_id:
            raise PermissionError(f"Yetkazib beruvchi (ID={sid}) ushbu korxonaga tegishli emas.")



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
            # 1. Kompaniya ID'lari tekshiruvi (cross-tenant ID tampering oldini olish)
            try:
                validate_arguments_company_ownership(db, user.company_id, kwargs)
            except PermissionError as pe:
                log.status = "ERROR"
                log.error = str(pe)
                db.commit()
                return {"reply": f"❌ Xavfsizlik xatosi: {str(pe)}"}

            confirmation_id = str(uuid.uuid4())
            ttl_min = getattr(settings, "AI_PENDING_ACTION_TTL_MIN", 10) or 10
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=ttl_min)
            card_summary = generate_action_card_summary(name, kwargs)

            pending = PendingAction(
                id=confirmation_id,
                company_id=user.company_id,
                user_id=user.id,
                tool_name=name,
                tool_arguments=kwargs,
                description=card_summary,
                status="pending",
                created_at=now,
                expires_at=expires_at,
            )
            db.add(pending)

            log.status = "PENDING_CONFIRMATION"
            log.confirmation_id = confirmation_id
            db.commit()
            
            # We return a structured draft indicating confirmation is needed
            return {
                "reply": f"⚠️ Ushbu amalni bajarish uchun tasdiqlash talab qilinadi:\n{card_summary}",
                "action": {
                    "type": "confirm_action",
                    "confirmation_id": confirmation_id,
                    "pending_action_id": confirmation_id,
                    "tool_name": name,
                    "summary": card_summary,
                    "expires_at": expires_at.isoformat(),
                    "arguments": kwargs  # Faqat frontend kartochkasida ko'rsatish uchun
                }
            }

        # Execution for LOW / MEDIUM
        try:
            from app.services.ai_db_context import ai_tenant_context
            with ai_tenant_context(db, user.company_id, read_only=(tool_class.risk_level == "LOW")):
                tool_instance = tool_class()
                result = tool_instance.execute(db, user.company_id, user, **kwargs)
            
            log.status = "SUCCESS"
            log.result_summary = summarize_reply(result)

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
from datetime import datetime, timezone, timedelta

def _sf(val):
    try: return float(val or 0)
    except: return 0.0

def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " so'm"

# T2.9: ixtiyoriy filial parametri (LLM tool-schema). Noma'lum qiymat xato emas - aniqlashtiruvchi javob.
BRANCH_PARAM = {
    "type": "string",
    "description": "Filial nomi (ixtiyoriy). Foydalanuvchi aniq filial so'rasa shu nomni yozing; "
                   "aks holda bo'sh qoldiring (butun korxona yoki foydalanuvchining o'z filiali).",
}

PERIOD_NAMES = {"today": "Bugun", "yesterday": "Kecha", "week": "Oxirgi 7 kun", "month": "Oxirgi 30 kun"}

def _period_range(period: str):
    """AI vositalari davri → (start, end), Toshkent vaqti bo'yicha (Hisobotlar bilan bir xil)."""
    from app.utils.report_utils import _date_range, local_today
    today = local_today()
    if period == "yesterday":
        day = today - timedelta(days=1)
        return _date_range(day, day)
    if period == "week":
        return _date_range(today - timedelta(days=6), today)
    if period == "month":
        return _date_range(today - timedelta(days=29), today)
    return _date_range(today, today)

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

        # T2.6: yagona servis (`customer_ledger.pay_debt`) — Mijozlar/Moliya sahifalari bilan bir xil mantiq:
        # kassa yagona qoida bilan (kassirning kassasi -> filial kassasi), kassa topilmasa qarz O'ZGARMAYDI,
        # qarzdan ortiq to'lov rad etiladi, filial 0 yozilmaydi, jurnalga tushadi
        from fastapi import HTTPException
        from app.services import customer_ledger
        try:
            customer_ledger.pay_debt(
                db, customer, user=user,
                payments=[{"amount": amount, "currency": "UZS", "payment_type": "cash"}],
                reason=f"AI orqali qarz to'lovi: {customer.name}",
            )
        except HTTPException as exc:
            return {"reply": f"❌ {exc.detail}"}

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

        # T2.6: yagona servis — balans (UZS chelagi va hosila agregat), jurnal (kind='ai', kim va sabab bilan)
        from sqlalchemy.orm.attributes import flag_modified
        from app.services import customer_ledger
        old_balance = _sf(customer.debt_balance)
        reason = "AI orqali nasiya qo'shish"
        customer_ledger.add_debt(
            db, customer, currency="UZS", amount=amount, kind="ai", user=user, reason=reason,
        )

        history = list(customer.debt_edited or [])
        history.append({
            "edited_from": {"UZS": old_balance},
            "edited_to": {"UZS": _sf(customer.debt_balance)},
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "edited_by": {"id": user.id, "name": user.name},
            "user_id": user.id,
            "reason": reason,
        })
        customer.debt_edited = history
        flag_modified(customer, "debt_edited")

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
            "period": {"type": "string", "description": "'today', 'yesterday', 'week', 'month' - davr", "enum": ["today", "yesterday", "week", "month"]},
            "branch": BRANCH_PARAM,
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.utils.report_utils import sales_summary
        from app.services.ai_scope import resolve_tool_scope, scope_header, scope_sale_filter
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        head = scope_header(scope, note)
        period = kwargs.get("period", "today")
        start, end = _period_range(period)
        s = sales_summary(db, company_id, start, end, sale_filter=scope_sale_filter(scope))
        count = s["count"]
        pname = PERIOD_NAMES.get(period, "Bugun")

        if count == 0 and s["returns_count"] == 0:
            return {"reply": f"{head}📊 {pname} uchun hech qanday sotuv topilmadi."}

        returns_lines = (
            f"• Qaytarishlar: {s['returns_count']} ta, {_fmt(s['returns'])}\n"
            f"• Sof tushum: {_fmt(s['net'])}\n"
        ) if s["returns_count"] else ""
        return {
            "reply": (
                f"{head}"
                f"📊 {pname} savdo xulosasi:\n"
                f"• Jami tushum: {_fmt(s['gross'])}\n"
                f"{returns_lines}"
                f"• Buyurtmalar: {count} ta\n"
                f"• Naqd: {_fmt(s['cash'])}\n"
                f"• Karta: {_fmt(s['card'])}"
            ),
            "action": {"type": "show_data", "data": {"total": s["gross"], "net": s["net"], "returns": s["returns"], "count": count}}
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
            "limit": {"type": "integer", "description": "Ko'rsatiladigan mahsulotlar soni (default: 5)"},
            "branch": BRANCH_PARAM,
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.sale import SaleItem, Sale
        from app.models.product import Product
        from app.utils.report_utils import sale_or_return_filter, doc_sign, item_revenue_uzs
        from app.services.ai_scope import resolve_tool_scope, scope_header, scope_sale_filter
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        head = scope_header(scope, note)
        limit = min(int(kwargs.get("limit", 5)), 10)
        start, end = _period_range("month")

        # Sof miqdor va UZS tushum (qaytarishlar ayirilgan)
        net_qty = sqlfunc.sum(doc_sign() * SaleItem.quantity)
        q = db.query(
            Product.name,
            net_qty.label("qty"),
            sqlfunc.sum(doc_sign() * item_revenue_uzs()).label("revenue")
        ).join(SaleItem, Product.id == SaleItem.product_id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(
            Sale.company_id == company_id,
            sale_or_return_filter(),
            Sale.created_at >= start,
            Sale.created_at < end,
         )
        sale_flt = scope_sale_filter(scope)
        if sale_flt is not None:
            q = q.filter(sale_flt)
        results = q.group_by(Product.id, Product.name).order_by(net_qty.desc()).limit(limit).all()

        if not results:
            return {"reply": f"{head}📦 Oxirgi 30 kunda hech qanday sotuv topilmadi."}

        lines = []
        for i, (name, qty, rev) in enumerate(results, 1):
            lines.append(f"{i}. {name} — {int(qty or 0)} ta, {_fmt(_sf(rev))}")

        return {
            "reply": f"{head}🏆 Eng ko'p sotilgan {limit} ta mahsulot (oxirgi 30 kun):\n" + "\n".join(lines),
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
            "threshold": {"type": "integer", "description": "Zaxira chegarasi (berilmasa har bir mahsulotning minimal zaxirasi ishlatiladi)"},
            "branch": BRANCH_PARAM,
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.services.ai_scope import resolve_tool_scope, scope_header, low_stock_query
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        head = scope_header(scope, note)
        # threshold berilmasa - yagona ta'rif (T2.3): min_stock > 0 va doiradagi jami qoldiq <= min_stock;
        # berilsa - mahsulot darajasidagi SUM(qoldiq) < threshold
        threshold = int(kwargs["threshold"]) if kwargs.get("threshold") else None
        limit_text = f"{threshold} tadan kam" if threshold else "minimal chegaradan kam"

        # Qoldiq faqat doiradagi omborlar bo'yicha yig'iladi; o'chirilgan mahsulotlar kirmaydi
        if threshold:
            low_items = low_stock_query(db, company_id, scope, threshold).order_by("qty").limit(15).all()
        else:
            from app.services import stock_report
            low_items = [
                (r["product_id"], r["product_name"], r["current_qty"])
                for r in stock_report.low_stock_products(db, company_id, stock_report.scope_wh_ids(scope), limit=15)
            ]

        if not low_items:
            return {"reply": f"{head}✅ Zaxirasi {limit_text} bo'lgan mahsulot topilmadi. Ombor to'la!"}

        lines = [f"{i}. {name} — {int(qty or 0)} ta" for i, (_pid, name, qty) in enumerate(low_items, 1)]
        return {
            "reply": f"{head}⚠️ Tugayotgan {len(lines)} ta mahsulot (zaxirasi {limit_text}):\n" + "\n".join(lines),
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
            "limit": {"type": "integer", "description": "Ko'rsatiladigan mijozlar soni (default: 10)"},
            "branch": BRANCH_PARAM,
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.customer import Customer
        from app.services.ai_scope import resolve_tool_scope
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        # Qarz T2.6 gacha filial bo'yicha ajratilmagan: aniq "butun korxona" yorlig'i (chalg'itmaslik uchun)
        head = "📍 Butun korxona qarzi (qarz filial bo'yicha ajratilmagan)\n"
        if note:
            head += f"ℹ️ {note}\n"
        min_amount = _sf(kwargs.get("min_amount", 0))
        limit = min(int(kwargs.get("limit", 10)), 20)

        debtors = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.debt_balance > min_amount
        ).order_by(Customer.debt_balance.desc()).limit(limit).all()

        if not debtors:
            return {"reply": f"{head}✅ Qarz chegarasidan yuqori mijoz topilmadi."}

        lines = []
        for i, c in enumerate(debtors, 1):
            lines.append(f"{i}. {c.name} — {_format_debt(c)}")

        return {
            "reply": f"{head}📋 Qarzdorlar ro'yxati ({len(lines)} ta mijoz):\n" + "\n".join(lines),
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
            "period": {"type": "string", "description": "'today', 'yesterday', 'week', 'month'", "enum": ["today", "yesterday", "week", "month"]},
            "branch": BRANCH_PARAM,
        },
        "required": []
    }
    def execute(self, db: Session, company_id: int, user: User, **kwargs):
        from app.models.sale import Sale, SaleItem
        from app.utils.report_utils import sale_or_return_filter, doc_sign, item_revenue_uzs, item_cost_uzs
        from app.services.ai_scope import resolve_tool_scope, scope_header, scope_sale_filter
        scope, note, err = resolve_tool_scope(db, user, kwargs)
        if err:
            return err
        head = scope_header(scope, note)
        period = kwargs.get("period", "today")
        start, end = _period_range(period)

        # UZS da, qaytarishlar ayirilgan — Hisobotlar bo'limidagi "Foyda" bilan bir xil
        q = db.query(
            sqlfunc.coalesce(sqlfunc.sum(doc_sign() * item_revenue_uzs()), 0),
            sqlfunc.coalesce(sqlfunc.sum(doc_sign() * item_cost_uzs()), 0),
        ).select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).filter(
            Sale.company_id == company_id, sale_or_return_filter(),
            Sale.created_at >= start, Sale.created_at < end,
        )
        sale_flt = scope_sale_filter(scope)
        if sale_flt is not None:
            q = q.filter(sale_flt)
        revenue_sum, cost_sum = q.one()

        revenue = _sf(revenue_sum)
        cost = _sf(cost_sum)
        profit = revenue - cost
        margin = (profit / revenue * 100) if revenue > 0 else 0

        pname = PERIOD_NAMES.get(period, "Bugun")

        return {
            "reply": (
                f"{head}"
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
                StockLevel.product_id == p.id,
                __import__("sqlalchemy").or_(StockLevel.warehouse_id.is_(None), StockLevel.warehouse.has(is_active=True)),
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


# Bosqich 4: Semantik AI vositalarini ro'yxatdan o'tkazish
import app.services.ai_tools_semantic  # noqa: F401

