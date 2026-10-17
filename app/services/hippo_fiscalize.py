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
from datetime import datetime
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


def _vat_percent(product: Product, default_vat: Optional[int] = None) -> int:
    """Mahsulot VAT turini Hippo uchun foizga (int) aylantiradi.

    C4.1 (T4.2): turi belgilanmagan (NULL) mahsulot uchun `default_vat` (Company.fiscal_default_vat) ishlatiladi;
    u ham NULL bo'lsa standart 12%."""
    if product.vat_rate_type is None:
        fallback = default_vat if default_vat is not None else 12
        # T4.2: QQS turi belgilanmagan mahsulot korxona standarti (yoki 12%) bilan fiskallanadi (soliq natijasiga
        # ta'sir qiladi) — mahsulotni to'g'rilash uchun ogohlantirish yoziladi.
        logger.warning(
            "[Hippo] Product id=%s (%s): vat_rate_type belgilanmagan — standart %s%% QQS bilan fiskallanadi",
            getattr(product, "id", None), getattr(product, "name", ""), fallback,
        )
        return int(fallback)
    return _VAT_PERCENT_MAP.get(product.vat_rate_type, 12)


def _company_default_vat(sale: Sale) -> Optional[int]:
    """Sotuv korxonasining `fiscal_default_vat` qiymati (yo'q/NULL bo'lsa None)."""
    try:
        from sqlalchemy.orm import object_session
        from app.models.company import Company
        db = object_session(sale)
        if db is None or not getattr(sale, "company_id", None):
            return None
        return db.query(Company.fiscal_default_vat).filter(Company.id == sale.company_id).scalar()
    except Exception as exc:  # noqa: BLE001 — standart QQS topilmasa 12% ga qaytiladi
        logger.warning("[Hippo] Korxona standart QQS ni o'qib bo'lmadi: %s", exc)
        return None


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
    default_vat = _company_default_vat(sale)  # C4.1 (T4.2): NULL turdagi mahsulotlar uchun
    items = []
    for item in sale.items:
        product: Optional[Product] = item.product
        if not product:
            logger.warning(
                "[Hippo] SaleItem id=%s uchun product topilmadi — o'tkazib yuborildi",
                item.id,
            )
            continue

        # Chet el valyutasida sotilgan tovarlar uchun narx/chegirmani UZS'ga
        # aylantiramiz - Hippo faqat so'mda qabul qiladi, aylantirilmasa
        # soliq organiga notogri (juda kam) summa yuborilib qoladi.
        item_currency = (item.currency_code or "UZS").upper()
        item_rate = Decimal(str(item.exchange_rate or 1)) if item_currency != "UZS" else Decimal("1")

        unit_price = int((Decimal(str(item.unit_price or 0)) * item_rate).to_integral_value())
        quantity   = int(item.quantity or 1)
        discount   = int((Decimal(str(item.discount or 0)) * item_rate).to_integral_value())

        items.append({
            "name":         product.name,
            "barcode":      product.barcode or "",
            "spic":         product.mxik_code or "",
            "package_code": str(product.package_code) if product.package_code else "",
            "labels":       item.marking_codes or product.labels or [],
            "quantity":     quantity,
            "price":        unit_price,
            "discount":     discount,
            "vat_percent":  _vat_percent(product, default_vat),
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


# ── Natijani Sale ga yozish (T3.18) ──────────────────────────────────────────

def _first(result: dict, *keys):
    """Kommunikator javobidan birinchi mavjud (bo'sh bo'lmagan) kalit qiymati."""
    for k in keys:
        v = result.get(k)
        if v not in (None, ""):
            return v
    return None


def _to_int(v) -> Optional[int]:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 2147483647 else None


def save_fiscal_result(db: Session, sale: Sale, result: Optional[dict], factory_id: str) -> bool:
    """Muvaffaqiyatli fiskal natijani (`fiscal_sign`, QR, ketma-ketlik, tranzaksiya, vaqt, qurilma) `Sale` ga yozadi.

    `fiscal_sign` bo'lmasa (chek lokal saqlangan, lekin fiskallanmagan) hech narsa yozilmaydi.
    Xato bo'lsa log yoziladi va False qaytadi — sotuv va fiskal chek bekor qilinmaydi."""
    if not result or not isinstance(result, dict):
        return False
    sign = _first(result, "fiscal_sign", "FiscalSign")
    if not sign:
        return False
    try:
        sale.fiscal_sign = str(sign)[:64]
        qr = _first(result, "qr_code_url", "QRCodeURL")
        if qr:
            sale.fiscal_qr_url = str(qr)
        seq = _to_int(_first(result, "receipt_seq", "receipt_number", "ReceiptSeq"))
        if seq is not None:
            sale.fiscal_receipt_seq = seq
        tx = _first(result, "transaction_id", "TransactionID")
        if tx is not None:
            sale.fiscal_transaction_id = str(tx)[:64]
        sale.fiscal_at = datetime.utcnow()
        sale.fiscal_factory_id = str(factory_id)[:64]
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — fiskal natijani yozish xatosi sotuvni buzmasligi kerak
        db.rollback()
        logger.error("[Hippo] Sale id=%s fiskal natijani saqlashda xato: %s", sale.id, exc)
        return False


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
        # T3.18: natija Sale ga yoziladi (avval faqat qaytarilardi, saqlanmasdi)
        save_fiscal_result(db, sale, result, factory_id)
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
