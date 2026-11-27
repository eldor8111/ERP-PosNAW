"""
hippo_fiscalize.py
──────────────────
Sotuv yakunlangandan so'ng Universal Communicator (UC) ga fiskal chek yuborish servisi.

UC format:
    POST http://localhost:8347/uzpos
    {
      "token": "...",
      "method": "sale",           # "refund" qaytarish uchun
      "companyName": "...",
      "companyAddress": "...",
      "companyINN": "...",
      "staffName": "...",
      "printerSize": 58,
      "params": {
        "receivedCash": 150000,
        "receivedCard": 650000,
        "items": [
          {
            "name": "...",
            "barcode": "...",
            "classCode": "02202003001002001",  # MXIK
            "packageCode": "1254782",
            "label": "",                        # markirovka (string)
            "amount": 1,                        # miqdor (dona)
            "price": 500000,                    # dona narxi (so'm)
            "discount": 0,                      # chegirma (so'm)
            "vatPercent": 12,
            "vat": 54054,                       # QQS summasi (hisoblangan)
            "ownerType": 0,                     # 0=o'z, 1=komissioner
          }
        ]
      }
    }

Ishlatilish tartibi:
    1. sales.py router -> make_sale() -> background_tasks.add_task(fiscalize_sale, sale.id, factory_id)
    2. Bu servis Sale + SaleItem larni DB dan o'qib, UC formatiga o'giradi va yuboradi.
    3. Xatolik yuz bersa faqat log yoziladi — sotuv bekor qilinmaydi.
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
    """Mahsulot VAT turini UC uchun foizga (int) aylantiradi."""
    if product.vat_rate_type is None:
        fallback = default_vat if default_vat is not None else 12
        logger.warning(
            "[UC] Product id=%s (%s): vat_rate_type belgilanmagan — standart %s%% QQS bilan fiskallanadi",
            getattr(product, "id", None), getattr(product, "name", ""), fallback,
        )
        return int(fallback)
    return _VAT_PERCENT_MAP.get(product.vat_rate_type, 12)


def _calc_vat(price: int, amount: int, discount: int, vat_percent: int) -> int:
    """
    UC uchun QQS summasi (so'mda):
        vat = round((price * amount - discount) * vatPercent / (100 + vatPercent))
    """
    gross = max(0, price * amount - discount)
    if vat_percent <= 0:
        return 0
    return round(gross * vat_percent / (100 + vat_percent))


def _company_default_vat(sale: Sale) -> Optional[int]:
    """Sotuv korxonasining `fiscal_default_vat` qiymati (yo'q/NULL bo'lsa None)."""
    try:
        from sqlalchemy.orm import object_session
        from app.models.company import Company
        db = object_session(sale)
        if db is None or not getattr(sale, "company_id", None):
            return None
        return db.query(Company.fiscal_default_vat).filter(Company.id == sale.company_id).scalar()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[UC] Korxona standart QQS ni o'qib bo'lmadi: %s", exc)
        return None


def _company_info(sale: Sale) -> dict:
    """
    Korxona ma'lumotlarini UC so'rovi uchun tayyorlaydi.
    Sale.company -> Company modelidan olinadi.
    """
    info = {
        "companyName": "",
        "companyAddress": "",
        "companyINN": "",
        "staffName": "",
        "printerSize": 58,
    }
    try:
        from sqlalchemy.orm import object_session
        from app.models.company import Company
        from app.models.user import User
        db = object_session(sale)
        if db is None:
            return info
        # Korxona
        company = db.query(Company).filter(Company.id == sale.company_id).first()
        if company:
            info["companyName"] = company.name or ""
            info["companyAddress"] = getattr(company, "address", "") or ""
            info["companyINN"] = str(getattr(company, "inn", "") or "")
        # Kassir (Sale.user_id bo'lsa)
        if sale.user_id:
            user = db.query(User).filter(User.id == sale.user_id).first()
            if user:
                full = f"{user.first_name or ''} {user.last_name or ''}".strip()
                info["staffName"] = full or user.username or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("[UC] Korxona ma'lumotlarini o'qib bo'lmadi: %s", exc)
    return info


# ── Receipt builder ──────────────────────────────────────────────────────────

def _build_uc_payload(sale: Sale) -> dict:
    """
    Sale ORM obyektidan UC `sale`/`refund` formatiga o'giradi.

    Pul birligi: so'm (butun son).
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
    else:
        received_cash = int(sale.paid_cash or 0)
        received_card = int(sale.paid_card or 0)

    # Chek qatorlarini qurish
    default_vat = _company_default_vat(sale)
    items = []
    for item in sale.items:
        product: Optional[Product] = item.product
        if not product:
            logger.warning("[UC] SaleItem id=%s uchun product topilmadi — o'tkazib yuborildi", item.id)
            continue

        # Chet el valyutasini UZS ga o'tkazamiz
        item_currency = (item.currency_code or "UZS").upper()
        item_rate = Decimal(str(item.exchange_rate or 1)) if item_currency != "UZS" else Decimal("1")

        unit_price = int((Decimal(str(item.unit_price or 0)) * item_rate).to_integral_value())
        amount     = int(item.quantity or 1)
        discount   = int((Decimal(str(item.discount or 0)) * item_rate).to_integral_value())
        vat_pct    = _vat_percent(product, default_vat)

        # Markirovka: UC da string "label" (birinchi kod yoki bo'sh)
        labels = item.marking_codes or product.labels or []
        label = labels[0] if labels else ""

        items.append({
            "name":        product.name,
            "barcode":     product.barcode or "",
            "classCode":   product.mxik_code or "",          # UC: classCode = MXIK/SPIC
            "packageCode": str(product.package_code) if product.package_code else "",
            "label":       label,                             # UC: string (1 ta)
            "amount":      amount,                            # UC: miqdor (dona)
            "price":       unit_price,                        # UC: dona narxi (so'm)
            "discount":    discount,                          # UC: chegirma (so'm)
            "vatPercent":  vat_pct,                           # UC: camelCase
            "vat":         _calc_vat(unit_price, amount, discount, vat_pct),  # hisoblangan QQS
            "ownerType":   0,                                 # 0 = o'z tovar
        })

    if not items:
        raise ValueError("Chek qatorlari bo'sh — fiskalizatsiya o'tkazib yuborildi")

    # Chek darajasidagi chegirma
    receipt_discount = int(sale.discount_amount or 0)

    params = {
        "receivedCash":  received_cash,
        "receivedCard":  received_card,
        "discount":      receipt_discount,
        "items":         items,
    }

    return params


# ── Natijani Sale ga yozish ───────────────────────────────────────────────────

def _first(result: dict, *keys):
    """UC javobidan birinchi mavjud (bo'sh bo'lmagan) kalit qiymati."""
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
    """
    Muvaffaqiyatli fiskal natijani (`fiscal_sign`, QR, ketma-ketlik, tranzaksiya, vaqt, qurilma) `Sale` ga yozadi.

    UC javobida `fiscal_sign` / `fiscalSign` bo'lmasa hech narsa yozilmaydi.
    """
    if not result or not isinstance(result, dict):
        return False
    sign = _first(result, "fiscal_sign", "fiscalSign", "FiscalSign")
    if not sign:
        return False
    try:
        sale.fiscal_sign = str(sign)[:64]
        qr = _first(result, "qr_code_url", "qrCodeUrl", "QRCodeURL")
        if qr:
            sale.fiscal_qr_url = str(qr)
        seq = _to_int(_first(result, "receipt_seq", "receiptSeq", "receipt_number", "ReceiptSeq"))
        if seq is not None:
            sale.fiscal_receipt_seq = seq
        tx = _first(result, "transaction_id", "transactionId", "TransactionID")
        if tx is not None:
            sale.fiscal_transaction_id = str(tx)[:64]
        sale.fiscal_at = datetime.utcnow()
        sale.fiscal_factory_id = str(factory_id)[:64]
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("[UC] Sale id=%s fiskal natijani saqlashda xato: %s", sale.id, exc)
        return False


# ── Asosiy funksiyalar ────────────────────────────────────────────────────────

def fiscalize_sale(
    db: Session,
    sale_id: int,
    factory_id: str,
) -> Optional[dict]:
    """
    Sotuv ID si bo'yicha DB dan sale o'qib, UC ga chek yuboradi.

    Background task sifatida chaqiriladi — xatolik sotuv tranzaksiyasiga ta'sir qilmaydi.
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
        logger.error("[UC] Sale id=%s topilmadi — fiskalizatsiya o'tkazilmadi", sale_id)
        return None

    try:
        params = _build_uc_payload(sale)
    except ValueError as exc:
        logger.warning("[UC] Sale id=%s payload xatosi: %s", sale_id, exc)
        return None

    company_info = _company_info(sale)

    logger.info(
        "[UC] Sale id=%s fiskalizatsiya boshlanmoqda. factory_id=%s, items=%d",
        sale_id, factory_id, len(params["items"]),
    )

    try:
        result = hippo_client.sale(params, **company_info)
        logger.info(
            "[UC] Sale id=%s muvaffaqiyatli fiskallandi. fiscal_sign=%s",
            sale_id, result.get("fiscal_sign") or result.get("fiscalSign"),
        )
        save_fiscal_result(db, sale, result, factory_id)
        return result

    except HippoFiscalizationError as exc:
        logger.warning(
            "[UC] Sale id=%s: chek lokal saqlandi, fiskalizatsiya muvaffaqiyatsiz. Xato: %s",
            sale_id, exc.message,
        )
        return exc.payload

    except HippoClientError as exc:
        logger.error(
            "[UC] Sale id=%s fiskalizatsiya xatosi [%s]: %s",
            sale_id, exc.status_code, exc.message,
        )
        return None


def fiscalize_return(
    db: Session,
    sale_id: int,
    factory_id: str,
) -> Optional[dict]:
    """Qaytarish chekini UC ga yuboradi (method=refund)."""
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
        logger.error("[UC] Return sale id=%s topilmadi", sale_id)
        return None

    try:
        params = _build_uc_payload(sale)
    except ValueError as exc:
        logger.warning("[UC] Return sale id=%s payload xatosi: %s", sale_id, exc)
        return None

    company_info = _company_info(sale)

    logger.info("[UC] Return sale id=%s fiskalizatsiya boshlanmoqda", sale_id)

    try:
        result = hippo_client.refund(params, **company_info)
        logger.info("[UC] Return sale id=%s muvaffaqiyatli fiskallandi", sale_id)
        return result

    except HippoFiscalizationError as exc:
        logger.warning(
            "[UC] Return sale id=%s lokal saqlandi, fiskalizatsiya muvaffaqiyatsiz: %s",
            sale_id, exc.message,
        )
        return exc.payload

    except HippoClientError as exc:
        logger.error(
            "[UC] Return sale id=%s xato [%s]: %s",
            sale_id, exc.status_code, exc.message,
        )
        return None
