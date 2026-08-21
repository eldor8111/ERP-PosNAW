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
        tools = []
        for name, tool_class in cls._tools.items():
            # TODO: filter by user permission here if needed so LLM doesn't even see tools it can't use
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
        # TODO: Implement actual permission check using user.role
        has_permission = True 
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
