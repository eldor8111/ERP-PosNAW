"""
hippo_fiscalize.py
──────────────────
Sotuv yakunlangandan so'ng Hippo Communicator ga fiskal chek yuborish servisi.

Ishlatilish tartibi:
    1. sales.py router -> make_sale() -> background_tasks.add_task(fiscalize_sale, sale.id, factory_id)
    2. Bu servis Sale + SaleItem larni DB dan o'qib, Hippo formatiga o'giradi va yuboradi.
    3. Xatolik yuz bersa faqat log yoziladi — sotuv bekor qilinmaydi (fiskal xato kritik emas).
"""

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.sale import Sale, SaleItem, PaymentType
from app.models.product import Product
from app.models.mxik import VatRateType
from app.utils.hippo_client import hippo_client, HippoClientError, HippoFiscalizationError

logger = logging.getLogger("hippo.fiscalize")


# ── VAT mapping ──────────────────────────────────────────────────────────────

_VAT_PERCENT_MAP: dict[Optional[VatRateType], int] = {
    VatRateType.standard: 12,   # 12% QQS
    VatRateType.zero:      0,   # 0% QQS
    VatRateType.exempt:    0,   # Imtiyozli — 0 yuboriladi
    None:                  12,  # Belgilanmagan — standart 12%
}


def _vat_percent(product: Product) -> int:
    """Mahsulot VAT turini Hippo uchun foizga (int) aylantiradi."""
    return _VAT_PERCENT_MAP.get(product.vat_rate_type, 12)


# ── Receipt builder ──────────────────────────────────────────────────────────

def _build_receipt_payload(sale: Sale, factory_id: str) -> dict:
    """
    Sale ORM obyektidan Hippo RegisterReceiptRequestModel formatiga o'giradi.

    Pul birligi: so'm (butun son) — Hippo ichida tiyinga (×100) o'tkazadi.
    """
    # To'lov turlarini ajratamiz
    received_cash = 0
    received_card = 0

    CASH_TYPES = {"cash"}
    CARD_TYPES = {"card", "uzcard", "humo", "payme", "click", "uzum"}

    if hasattr(sale, "payments") and sale.payments:
        for p in sale.payments:
            pt = p.payment_type if isinstance(p.payment_type, str) else p.payment_type.value
            amt = int(p.amount or 0)
            if pt in CASH_TYPES:
                received_cash += amt
            elif pt in CARD_TYPES:
                received_card += amt
            # "debt", "cashback" → Hippo da maxsus maydon yo'q, naqd sifatida hisoblanadi
    else:
        # Eski format: paid_cash / paid_card
        received_cash = int(sale.paid_cash or 0)
        received_card = int(sale.paid_card or 0)

    # Chek qatorlarini qurish
    items = []
    for item in sale.items:
        product: Optional[Product] = item.product
        if not product:
            logger.warning(
                "[Hippo] SaleItem id=%s uchun product topilmadi — o'tkazib yuborildi",
                item.id,
            )
            continue

        unit_price = int(item.unit_price or 0)
        quantity   = int(item.quantity or 1)
        discount   = int(item.discount or 0)

        items.append({
            "name":         product.name,
            "barcode":      product.barcode or "",
            "spic":         product.mxik_code or "",
            "package_code": str(product.package_code) if product.package_code else "",
            "labels":       product.labels or [],
            "quantity":     quantity,
            "price":        unit_price,
            "discount":     discount,
            "vat_percent":  _vat_percent(product),
        })

    if not items:
        raise ValueError("Chek qatorlari bo'sh — fiskalizatsiya o'tkazib yuborildi")

    # Chek darajasidagi chegirma
    receipt_discount = int(sale.discount_amount or 0)

    return {
        "factory_id": factory_id,
        "receipt": {
            "receivedCash":  received_cash,
            "received_card": received_card,
            "discount":      receipt_discount,
            "type":     0,  # 0 = oddiy sotuv (Sale)
            "operation": 0,  # 0 = sotuv
            "items": items,
        },
    }


# ── Asosiy funksiya ──────────────────────────────────────────────────────────

def fiscalize_sale(
    db: Session,
    sale_id: int,
    factory_id: str,
) -> Optional[dict]:
    """
    Sotuv ID si bo'yicha DB dan sale o'qib, Hippo ga chek yuboradi.

    Background task sifatida chaqiriladi — xatolik sotuv tranzaksiyasiga ta'sir qilmaydi.

    Qaytaradi:
        dict — muvaffaqiyatli fiskalizatsiya natijasi (fiscal_sign, qr_code_url, ...)
        None — xatolik yuz berdi (log yozildi)
    """
    # Sale ni products bilan birgalikda yuklash
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.payments),
        )
        .filter(Sale.id == sale_id)
        .first()
    )

    if not sale:
        logger.error("[Hippo] Sale id=%s topilmadi — fiskalizatsiya o'tkazilmadi", sale_id)
        return None

    try:
        payload = _build_receipt_payload(sale, factory_id)
    except ValueError as exc:
        logger.warning("[Hippo] Sale id=%s payload xatosi: %s", sale_id, exc)
        return None

    logger.info(
        "[Hippo] Sale id=%s fiskalizatsiya boshlanmoqda. factory_id=%s, items=%d",
        sale_id, factory_id, len(payload["receipt"]["items"]),
    )

    try:
        result = hippo_client.post("/fiscalization/v1/receipt/register", payload)
        logger.info(
            "[Hippo] Sale id=%s muvaffaqiyatli fiskallandi. fiscal_sign=%s, qr=%s",
            sale_id,
            result.get("fiscal_sign"),
            result.get("qr_code_url"),
        )
        return result

    except HippoFiscalizationError as exc:
        # 422 — chek Hippo lokal bazasida saqlandi, lekin fiskal qurilmaga etib bormadi.
        # Bu kritik emas: Hippo keyinchalik o'zi qayta urinadi yoki sync qilish mumkin.
        logger.warning(
            "[Hippo] Sale id=%s: chek lokal saqlandi, fiskalizatsiya muvaffaqiyatsiz. "
            "Payload: %s. Xato: %s",
            sale_id, exc.payload, exc.message,
        )
        return exc.payload  # local_id ni qaytaradi — keyinroq retry uchun

    except HippoClientError as exc:
        logger.error(
            "[Hippo] Sale id=%s fiskalizatsiya xatosi [%s]: %s",
            sale_id, exc.status_code, exc.message,
        )
        return None


# ── Qaytarish (Return) fiskalizatsiyasi ──────────────────────────────────────

def fiscalize_return(
    db: Session,
    sale_id: int,
    factory_id: str,
) -> Optional[dict]:
    """
    Qaytarish chekini Hippo ga yuboradi. operation=1 (refund).
    """
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.payments),
        )
        .filter(Sale.id == sale_id)
        .first()
    )

    if not sale:
        logger.error("[Hippo] Return sale id=%s topilmadi", sale_id)
        return None

    try:
        payload = _build_receipt_payload(sale, factory_id)
        # Qaytarish uchun operation ni 1 ga o'zgartiramiz
        payload["receipt"]["operation"] = 1
    except ValueError as exc:
        logger.warning("[Hippo] Return sale id=%s payload xatosi: %s", sale_id, exc)
        return None

    logger.info("[Hippo] Return sale id=%s fiskalizatsiya boshlanmoqda", sale_id)

    try:
        result = hippo_client.post("/fiscalization/v1/receipt/register", payload)
        logger.info("[Hippo] Return sale id=%s muvaffaqiyatli fiskallandi", sale_id)
        return result

    except HippoFiscalizationError as exc:
        logger.warning(
            "[Hippo] Return sale id=%s lokal saqlandi, fiskalizatsiya muvaffaqiyatsiz: %s",
            sale_id, exc.message,
        )
        return exc.payload

    except HippoClientError as exc:
        logger.error(
            "[Hippo] Return sale id=%s xato [%s]: %s",
            sale_id, exc.status_code, exc.message,
        )
        return None
