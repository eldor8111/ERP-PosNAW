"""
Payme Merchant API — JSON-RPC 2.0 Webhook Handler
===================================================
Rasmiy hujjat: https://developer.help.paycom.uz/protokol-merchant-api/

TO'G'IRLANGAN XATOLAR:
  1. Importlar yuqoriga ko'chirildi (fayl oxirida emas)
  2. amount float ham qabul qilinadi (Payme ba'zan float yuboradi)
  3. org_code None xatosi tuzatildi
  4. ERR_TXN_CANCELLED to'g'ri kod: -31008
  5. _err data parameter Optional[str]
  6. p_time o'zgaruvchi olib tashlandi (ishlatilmagan edi)
  7. PerformTransaction da try/except + rollback
  8. CheckPerformTransaction da keraksiz detail.receipt_type olib tashlandi
"""
import base64
import os
import time
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.config import settings  # type: ignore
from app.core.dependencies import get_current_user_allow_expired  # type: ignore
from app.database import get_db  # type: ignore
from app.models.billing import BalanceLog  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.payme_transaction import PaymeTransaction  # type: ignore
from app.models.user import User  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payme", tags=["Payme"])

# ─── Sozlamalar (settings dan — os.getenv EMAS!) ─────────────────────────────
# pydantic-settings .env ni os.environ ga YOZMAYDI, shuning uchun settings ishlatamiz
PAYME_MERCHANT_ID = settings.PAYME_MERCHANT_ID
PAYME_SECRET_KEY  = settings.PAYME_SECRET_KEY
PAYME_IS_TEST     = settings.PAYME_IS_TEST

# ─── Payme standart xato kodlari ─────────────────────────────────────────────
# https://developer.help.paycom.uz/protokol-merchant-api/#xato-kodlari
ERR_UNAUTHORIZED      = -32504   # Authorization xato
ERR_INVALID_REQUEST   = -32600   # JSON noto'g'ri
ERR_METHOD_NOT_FOUND  = -32601   # Metod topilmadi
ERR_INVALID_PARAMS    = -32602   # Parametrlar yetishmaydi
ERR_ORDER_NOT_FOUND   = -31050   # account (org_code) topilmadi
ERR_INVALID_AMOUNT    = -31001   # Summa noto'g'ri
ERR_TXN_NOT_FOUND     = -31003   # Tranzaksiya topilmadi
ERR_UNABLE_TO_PERFORM = -31008   # Bajarib bo'lmaydi (bekor qilingan txn ham)


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

def _now_ms() -> int:
    """Joriy vaqt millisoniyalarda."""
    return int(time.time() * 1000)


def _ok(request_id: Any, result: dict) -> JSONResponse:
    """Muvaffaqiyatli JSON-RPC javobi (HTTP 200)."""
    return JSONResponse(content={"jsonrpc": "2.0", "id": request_id, "result": result})


def _err(request_id: Any, code: int, message: str, data: Optional[str] = None) -> JSONResponse:
    """
    Xato JSON-RPC javobi.
    Muhim: Payme talabi bo'yicha XATO BO'LSA HAM HTTP 200 qaytariladi!
    """
    err_body: dict = {
        "code": code,
        "message": {"ru": message, "uz": message, "en": message},
    }
    if data:
        err_body["data"] = data
    logger.warning("[Payme] xato %s: %s", code, message)
    return JSONResponse(content={"jsonrpc": "2.0", "id": request_id, "error": err_body})


def _verify_auth(request: Request) -> bool:
    """
    Authorization: Basic base64(username:password) tekshirish.

    Payme ikki xil username ishlatadi:
      - "Paycom"      → Sandbox (test.paycom.uz) dan kelgan so'rovlar
      - MERCHANT_ID   → Production (checkout.paycom.uz) dan kelgan so'rovlar

    Ikkalasini ham qabul qilamiz, lekin password (SECRET_KEY/TEST_KEY)
    har doim to'g'ri bo'lishi shart.
    """
    if not PAYME_SECRET_KEY:
        logger.error("[Payme] PAYME_SECRET_KEY .env da yo'q!")
        return False
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        parts = decoded.split(":", 1)
        if len(parts) != 2:
            logger.error("[Payme Auth] Format noto'g'ri (colon yo'q): %s", decoded)
            return False
        username, password = parts[0], parts[1]
        
        # "Paycom" (sandbox) yoki MERCHANT_ID (production) — ikkalasi ham ok
        valid_user = username in ("Paycom", PAYME_MERCHANT_ID)
        valid_pass = password == PAYME_SECRET_KEY
        
        if not valid_user or not valid_pass:
            logger.error(
                "[Payme Auth Debug] FAILED! "
                "User=%s (Valid:%s), PassLen=%d, KeyLen=%d, "
                "Pass matches:%s",
                username, valid_user, len(password), len(PAYME_SECRET_KEY), valid_pass
            )
            # Faqat log uchun (haqiqiy parolni logga tushirmaslikka harakat qilamiz, lekin debug uchun oxirgi/bosh harflarini tekshirish mumkin)
            if not valid_pass:
                logger.error("[Payme Auth Debug] Received pass starts with: '%s', ends with: '%s'", password[:3], password[-3:])
                logger.error("[Payme Auth Debug] Expected key starts with: '%s', ends with: '%s'", PAYME_SECRET_KEY[:3], PAYME_SECRET_KEY[-3:])

        return valid_user and valid_pass
    except Exception as e:
        logger.error("[Payme Auth] Decode xatosi: %s", str(e))
        return False


def _to_amount_int(raw: Any) -> int:
    """
    FIX BUG #2: Payme amount ni int yoki float yuborishi mumkin.
    Har ikki holatda ham to'g'ri int ga aylantiradi.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _safe_str(val: Any) -> str:
    """FIX BUG #3 & #5: None yoki boshqa type ni xavfsiz str ga aylantiradi."""
    return str(val).strip() if val is not None else ""


def _txn_to_dict(txn: PaymeTransaction) -> dict:
    """Tranzaksiyani Payme standart formatida qaytaradi."""
    return {
        "id":           txn.payme_id,
        "time":         txn.create_time or 0,
        "amount":       txn.amount,
        "state":        txn.state,
        "reason":       txn.reason,
        "create_time":  txn.create_time or 0,
        "perform_time": txn.perform_time or 0,
        "cancel_time":  txn.cancel_time or 0,
        "transaction":  str(txn.id),
    }


# ─── Asosiy Webhook Endpoint ──────────────────────────────────────────────────

@router.post("/webhook")
async def payme_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Payme serveridan barcha JSON-RPC so'rovlarni qabul qiladi.
    Har doim HTTP 200 qaytariladi — Payme talabi!
    """
    # 1. Authorization
    if not _verify_auth(request):
        logger.warning("[Payme] ❌ AUTH FAILED | IP=%s | Header=%s",
                       request.client.host if request.client else "?",
                       request.headers.get("Authorization", "yo'q")[:30])
        return _err(None, ERR_UNAUTHORIZED, "Avtorizatsiya xatosi")

    # 2. JSON parse
    try:
        body = await request.json()
    except Exception:
        return _err(None, ERR_INVALID_REQUEST, "JSON parse xatosi")

    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # ── TEST LOGGING: barcha so'rovlarni to'liq ko'rish ──
    import json as _json
    logger.info(
        "[Payme] ━━━ KELGAN SO'ROV ━━━\n"
        "  Metod  : %s\n"
        "  ID     : %s\n"
        "  Params : %s",
        method, req_id,
        _json.dumps(params, ensure_ascii=False, indent=2)
    )

    # 3. Method dispatch
    dispatch = {
        "CheckPerformTransaction": _check_perform,
        "CreateTransaction":       _create_transaction,
        "PerformTransaction":      _perform_transaction,
        "CancelTransaction":       _cancel_transaction,
        "CheckTransaction":        _check_transaction,
    }
    handler = dispatch.get(method)
    if not handler:
        return _err(req_id, ERR_METHOD_NOT_FOUND, f"Metod topilmadi: {method}")

    response = handler(req_id, params, db)
    logger.info("[Payme] ━━━ YUBORILGAN JAVOB ━━━\n  %s",
                _json.dumps(response.body.decode() if hasattr(response, 'body') else str(response), ensure_ascii=False))
    return response


# ─── Metod 1: CheckPerformTransaction ────────────────────────────────────────

def _check_perform(req_id: Any, params: dict, db: Session) -> JSONResponse:
    """
    "Bu to'lov mumkinmi?" — faqat tekshiradi, hech narsa yozmaydi.
    MUHIM TARTIB (Payme Sandbox talabi):
      1. avval org_code mavjudligi (DB da) — agar yo'q → -31050
      2. keyin summa tekshiruvi                → agar noto'g'ri → -31001
    Buning sababi: Sandbox "Несуществующий счёт" testida
    IKKALASINI HAM (noto'g'ri org_code + kichik summa) yuboradi
    va -31050 kutadi. Agar avval summani tekshirsak -31001 qaytadi — XATO!
    """
    account  = params.get("account") or {}
    org_code = _safe_str(account.get("org_code"))
    amount   = _to_amount_int(params.get("amount", 0))

    # 1. AVVAL org_code ni tekshir (bo'sh bo'lsa)
    if not org_code:
        return _err(req_id, ERR_ORDER_NOT_FOUND, "account.org_code majburiy yoki noto'g'ri")

    # 2. AVVAL kompaniyani DB dan topishga urinin
    company = db.query(Company).filter(
        Company.org_code == org_code,
        Company.is_active == True,
    ).first()

    # 3. Kompaniya topilmasa → -31050 (summa qanday bo'lishidan qat'iy nazar!)
    if not company:
        return _err(req_id, ERR_ORDER_NOT_FOUND, f"Korxona topilmadi: {org_code}")

    # 4. Faqat kompaniya topilgandan keyin summani tekshir
    if amount <= 0:
        return _err(req_id, ERR_INVALID_AMOUNT, "Summa musbat bo'lishi kerak")

    if amount < 100_000:
        return _err(req_id, ERR_INVALID_AMOUNT, "Minimal to'lov summasi 1 000 so'm")

    return _ok(req_id, {"allow": True})


# ─── Metod 2: CreateTransaction ──────────────────────────────────────────────

def _create_transaction(req_id: Any, params: dict, db: Session) -> JSONResponse:
    """
    Tranzaksiya yaratadi (pul hali o'tmagan, state=1).
    Idempotent: bir xil ID bilan qayta kelsa mavjudni qaytaradi.
    FIX: p_time o'zgaruvchi olib tashlandi (ishlatilmasdi).
    FIX: amount float handling.
    """
    # FIX BUG #5: None xavfsiz str
    payme_id = _safe_str(params.get("id"))
    amount   = _to_amount_int(params.get("amount", 0))
    account  = params.get("account") or {}
    org_code = _safe_str(account.get("org_code"))

    if not payme_id:
        return _err(req_id, ERR_INVALID_PARAMS, "id majburiy")
    if not org_code:
        return _err(req_id, ERR_ORDER_NOT_FOUND, "account.org_code majburiy yoki noto'g'ri")

    # Idempotent tekshirish
    existing = db.query(PaymeTransaction).filter(
        PaymeTransaction.payme_id == payme_id
    ).first()

    if existing:
        # FIX BUG #6: bekor qilingan → -31008 (Payme standarti)
        if existing.state == -1:
            return _err(req_id, ERR_UNABLE_TO_PERFORM,
                        "Tranzaksiya allaqachon bekor qilingan")
        if existing.amount != amount:
            return _err(req_id, ERR_INVALID_AMOUNT, "Summa mos kelmaydi")
        return _ok(req_id, {
            "create_time": existing.create_time,
            "transaction": str(existing.id),
            "state":       existing.state,
        })

    # Korxona topish
    company = db.query(Company).filter(
        Company.org_code == org_code,
        Company.is_active == True,
    ).first()
    if not company:
        return _err(req_id, ERR_ORDER_NOT_FOUND, f"Korxona topilmadi: {org_code}")

    now_ms = _now_ms()
    txn = PaymeTransaction(
        payme_id         = payme_id,
        company_id       = company.id,
        amount           = amount,
        state            = 1,
        create_time      = now_ms,
        account_org_code = org_code,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    logger.info("[Payme] CreateTransaction: id=%s org=%s amount=%s tiyin",
                payme_id, org_code, amount)

    return _ok(req_id, {
        "create_time": txn.create_time,
        "transaction": str(txn.id),
        "state":       txn.state,
    })


# ─── Metod 3: PerformTransaction ─────────────────────────────────────────────

def _perform_transaction(req_id: Any, params: dict, db: Session) -> JSONResponse:
    """
    Pul o'tkazildi — korxona balansini to'ldiramiz.
    FIX BUG #7: try/except + db.rollback() qo'shildi.
    """
    payme_id = _safe_str(params.get("id"))
    if not payme_id:
        return _err(req_id, ERR_INVALID_PARAMS, "id majburiy")

    txn = db.query(PaymeTransaction).filter(
        PaymeTransaction.payme_id == payme_id
    ).first()
    if not txn:
        return _err(req_id, ERR_TXN_NOT_FOUND, "Tranzaksiya topilmadi")

    # Idempotent: allaqachon bajarilgan
    if txn.state == 2:
        return _ok(req_id, {
            "transaction":  str(txn.id),
            "perform_time": txn.perform_time,
            "state":        2,
        })

    if txn.state != 1:
        return _err(req_id, ERR_UNABLE_TO_PERFORM,
                    f"Bajarib bo'lmaydi, holat: state={txn.state}")

    company = db.query(Company).filter(Company.id == txn.company_id).first()
    if not company:
        return _err(req_id, ERR_UNABLE_TO_PERFORM, "Korxona topilmadi")

    amount_som = txn.amount / 100  # tiyindan so'mga

    # FIX BUG #7: rollback bilan xavfsiz commit
    try:
        company.balance = float(company.balance or 0) + amount_som

        log = BalanceLog(
            company_id = company.id,
            amount     = amount_som,
            log_type   = "payme_topup",
            note       = (
                f"Payme orqali to'ldirildi: +{amount_som:,.0f} so'm "
                f"(txn: {payme_id})"
            ),
            created_at = datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()  # log.id olish uchun

        now_ms = _now_ms()
        txn.state        = 2
        txn.perform_time = now_ms
        txn.log_id       = log.id

        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error("[Payme] PerformTransaction DB xato: %s", exc)
        return _err(req_id, -32400, "Server xatosi, qaytadan urining")

    logger.info("[Payme] PerformTransaction: id=%s org=%s +%.0f so'm",
                payme_id, txn.account_org_code, amount_som)

    return _ok(req_id, {
        "transaction":  str(txn.id),
        "perform_time": txn.perform_time,
        "state":        2,
    })


# ─── Metod 4: CancelTransaction ──────────────────────────────────────────────

def _cancel_transaction(req_id: Any, params: dict, db: Session) -> JSONResponse:
    """
    To'lovni bekor qiladi.
    state=1 → bekor qilish mumkin (pul o'tmagan).
    state=2 → balansdaan qaytarish (pul o'tgan).
    """
    payme_id = _safe_str(params.get("id"))
    reason   = params.get("reason", 0)

    if not payme_id:
        return _err(req_id, ERR_INVALID_PARAMS, "id majburiy")

    txn = db.query(PaymeTransaction).filter(
        PaymeTransaction.payme_id == payme_id
    ).first()
    if not txn:
        return _err(req_id, ERR_TXN_NOT_FOUND, "Tranzaksiya topilmadi")

    # Idempotent
    if txn.state == -1:
        return _ok(req_id, {
            "transaction": str(txn.id),
            "cancel_time": txn.cancel_time,
            "state":       -1,
        })

    now_ms = _now_ms()

    try:
        if txn.state == 1:
            # Pul o'tmagan — shunchaki bekor qilamiz
            txn.state       = -1
            txn.reason      = reason
            txn.cancel_time = now_ms

        elif txn.state == 2:
            # Pul o'tgan — balansdan qaytaramiz
            company = db.query(Company).filter(Company.id == txn.company_id).first()
            if company:
                amount_som = txn.amount / 100
                new_balance = float(company.balance or 0) - amount_som
                company.balance = new_balance  # manfiy bo'lishi mumkin (to'liq hisob)

                refund_log = BalanceLog(
                    company_id = company.id,
                    amount     = -amount_som,
                    log_type   = "payme_refund",
                    note       = (
                        f"Payme qaytarildi: -{amount_som:,.0f} so'm "
                        f"(txn: {payme_id}, sabab: {reason})"
                    ),
                    created_at = datetime.now(timezone.utc),
                )
                db.add(refund_log)

            txn.state       = -1
            txn.reason      = reason
            txn.cancel_time = now_ms

        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error("[Payme] CancelTransaction DB xato: %s", exc)
        return _err(req_id, -32400, "Server xatosi")

    logger.info("[Payme] CancelTransaction: id=%s reason=%s", payme_id, reason)

    return _ok(req_id, {
        "transaction": str(txn.id),
        "cancel_time": txn.cancel_time,
        "state":       -1,
    })


# ─── Metod 5: CheckTransaction ───────────────────────────────────────────────

def _check_transaction(req_id: Any, params: dict, db: Session) -> JSONResponse:
    """Tranzaksiya holatini qaytaradi."""
    payme_id = _safe_str(params.get("id"))
    if not payme_id:
        return _err(req_id, ERR_INVALID_PARAMS, "id majburiy")

    txn = db.query(PaymeTransaction).filter(
        PaymeTransaction.payme_id == payme_id
    ).first()
    if not txn:
        return _err(req_id, ERR_TXN_NOT_FOUND, "Tranzaksiya topilmadi")

    return _ok(req_id, _txn_to_dict(txn))


# ─── Checkout URL (Frontend uchun) ────────────────────────────────────────────

class PaymeCheckoutRequest(BaseModel):
    amount: float  # so'mda (masalan: 50000)


@router.post("/checkout-url")
def create_checkout_url(
    data: PaymeCheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_expired),
):
    """
    Frontend uchun Payme to'lov sahifasi URL sini yaratadi.
    Obuna muddati tugagan korxona ham to'lay olishi uchun
    get_current_user_allow_expired ishlatiladi.
    """
    if not PAYME_MERCHANT_ID:
        raise HTTPException(
            status_code=500,
            detail="Payme sozlanmagan. .env da PAYME_MERCHANT_ID yo'q."
        )

    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxonaga biriktirilmagan foydalanuvchi")

    company = db.query(Company).filter(
        Company.id == user.company_id,
        Company.is_active == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    if not company.org_code:
        raise HTTPException(
            status_code=400,
            detail="Korxonada org_code belgilanmagan. Admin bilan bog'laning."
        )

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")
    if data.amount < 1000:
        raise HTTPException(status_code=400, detail="Minimal summa 1 000 so'm")

    amount_tiyin = int(data.amount * 100)  # so'm → tiyin

    # Payme checkout URL parametrlari
    # Format: m=MERCHANT_ID;ac.org_code=ORG_CODE;a=AMOUNT_TIYIN
    raw     = f"m={PAYME_MERCHANT_ID};ac.org_code={company.org_code};a={amount_tiyin}"
    encoded = base64.b64encode(raw.encode()).decode()

    base_url     = "https://checkout.test.paycom.uz" if PAYME_IS_TEST else "https://checkout.paycom.uz"
    checkout_url = f"{base_url}/{encoded}"

    logger.info("[Payme] checkout-url: org=%s amount=%.0f so'm test=%s",
                company.org_code, data.amount, PAYME_IS_TEST)

    return {
        "checkout_url": checkout_url,
        "amount":       data.amount,
        "amount_tiyin": amount_tiyin,
        "org_code":     company.org_code,
        "is_test":      PAYME_IS_TEST,
    }
