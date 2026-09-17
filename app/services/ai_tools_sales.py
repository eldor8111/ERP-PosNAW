"""
ai_tools_sales.py
──────────────────
AI Copilot orqali sotuv (chek) yaratish. Eng yuqori xavfli (HIGH) tool —
pul va ombor holatiga bevosita ta'sir qiladi, shuning uchun har doim
tasdiqlash (confirmation) talab qilinadi va mavjud create_sale() servisini
(POS bilan bir xil narxlash/ombor/qarz mantig'i) qayta ishlatadi.
"""
from decimal import Decimal
import types

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.product import ProductStatus
from app.models.customer_prices import CustomerPrice
from app.models.sale import PaymentType
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.ai_tools_registry import AIToolRegistry, AITool, _find_customer
from app.services.ai_tools_crud import _find_product, _fmt
from app.services.sale_helpers import resolve_price
from app.services.sale_create import create_sale


@AIToolRegistry.register
class CreateSaleTool(AITool):
    name = "create_sale"
    description = (
        "Yangi sotuv (chek) yaratish — mahsulot(lar)ni mijozga sotib, kassaga yozish. "
        "Narx tizimdagi mahsulot narxidan (yoki mijozning maxsus narxidan) avtomatik olinadi."
    )
    required_permission = "sales.create"
    risk_level = "HIGH"
    parameters = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Sotiladigan mahsulotlar ro'yxati",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string", "description": "Mahsulot nomi"},
                        "quantity": {"type": "number", "description": "Miqdori"},
                    },
                    "required": ["product_name", "quantity"],
                },
            },
            "payment_type": {
                "type": "string",
                "enum": ["cash", "card", "debt"],
                "description": "To'lov turi. 'debt' bo'lsa customer_name majburiy."
            },
            "customer_name": {
                "type": "string",
                "description": "Mijoz ismi. Qarzga sotishda majburiy, naqd/karta to'lovda ixtiyoriy."
            },
        },
        "required": ["items", "payment_type"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        items_spec = kwargs.get("items") or []
        if not items_spec:
            return {"reply": "❌ Sotiladigan mahsulotlar ko'rsatilmagan."}

        payment_type_str = (kwargs.get("payment_type") or "").strip().lower()
        if payment_type_str not in ("cash", "card", "debt"):
            return {"reply": "❌ To'lov turi noto'g'ri — 'cash', 'card' yoki 'debt' bo'lishi kerak."}

        customer = None
        customer_name = (kwargs.get("customer_name") or "").strip()
        if customer_name:
            customer, err = _find_customer(db, company_id, customer_name)
            if err:
                return {"reply": err}

        if payment_type_str == "debt" and not customer:
            return {"reply": "❌ Qarzga sotish uchun mijoz ismini ko'rsating."}

        resolved_items = []
        lines = []
        total = Decimal("0")

        for spec in items_spec:
            pname = (spec.get("product_name") or "").strip()
            qty = spec.get("quantity")
            if not pname or qty is None or float(qty) <= 0:
                return {"reply": f"❌ Noto'g'ri mahsulot yoki miqdor: {spec}"}

            product, err = _find_product(db, company_id, pname)
            if err:
                return {"reply": err}
            if product.status != ProductStatus.active:
                return {"reply": f"❌ '{product.name}' faol emas, sotib bo'lmaydi."}

            qty_dec = Decimal(str(qty))

            customer_price = None
            if customer:
                customer_price = db.query(CustomerPrice).filter(
                    CustomerPrice.customer_id == customer.id,
                    CustomerPrice.product_id == product.id,
                ).first()
            # POS bilan bir xil narxlash mantig'ini ishlatamiz (resolve_price)
            unit_price = resolve_price(types.SimpleNamespace(unit_price=None), product, customer_price, customer)
            unit_price = Decimal(str(unit_price or 0))
            if unit_price <= 0:
                return {"reply": f"❌ '{product.name}' mahsulotining narxi belgilanmagan."}

            subtotal = unit_price * qty_dec
            total += subtotal
            resolved_items.append(SaleItemCreate(product_id=product.id, quantity=qty_dec))
            lines.append(f"• {product.name} x{qty_dec} = {_fmt(float(subtotal))}")

        paid_amount = Decimal("0") if payment_type_str == "debt" else total

        sale_data = SaleCreate(
            items=resolved_items,
            payment_type=PaymentType(payment_type_str),
            paid_amount=paid_amount,
            paid_cash=paid_amount if payment_type_str == "cash" else Decimal("0"),
            paid_card=paid_amount if payment_type_str == "card" else Decimal("0"),
            customer_id=customer.id if customer else None,
            note="AI Copilot orqali yaratildi",
        )

        try:
            sale = create_sale(db=db, data=sale_data, current_user=user, ip=None, background_tasks=None)
            db.commit()
            db.refresh(sale)
        except HTTPException as e:
            db.rollback()
            return {"reply": f"❌ Xatolik: {e.detail}"}

        summary = "\n".join(lines)
        tail = (
            f" — {customer.name} nomiga qarzga yozildi." if payment_type_str == "debt"
            else f" ({'naqd' if payment_type_str == 'cash' else 'karta'} to'landi)."
        )

        return {
            "reply": f"✅ Sotuv yaratildi (#{sale.number})!\n{summary}\nJami: {_fmt(float(total))}{tail}",
            "action": {"type": "sale_created", "sale_id": sale.id, "sale_number": sale.number},
        }
