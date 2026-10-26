# -*- coding: utf-8 -*-
"""
Uzum Bank Merchant API Webhook Router (FastAPI)
==============================================
Rasmiy spetsifikatsiya: Uzum Bank Merchant API (1.0.0)
Hujjat: https://developer.uzumbank.uz/merchant-api/

Metodlar:
  POST /check   - To'lov imkoniyatini tekshirish
  POST /create  - Tranzaksiyani yaratish (CREATED)
  POST /confirm - Tranzaksiyani tasdiqlash va yakunlash (CONFIRMED)
  POST /reverse - Tranzaksiyani bekor qilish / qaytarish (REVERSED)
  POST /status  - Tranzaksiya holatini tekshirish
"""
import base64
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.billing import BalanceLog
from app.models.uzum_transaction import UzumTransaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uzum", tags=["Uzum Bank Merchant API"])


# ─── Pydantic Modellar (Swagger UI uchun chiroyli sxemalar) ───────────────────
class CheckRequest(BaseModel):
    serviceId: int = Field(..., example=123123, description="Xizmat identifikatori")
    timestamp: int = Field(..., example=1714377645426, description="Yuborilgan vaqt (unix timestamp ms)")
    params: Dict[str, Any] = Field(..., example={"order_id": "123123"}, description="To'lov parametrlari (order_id, org_code, user_id)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "serviceId": 123123,
                "timestamp": 1714377645426,
                "params": {
                    "order_id": "123123"
                }
            }
        }
    }


class CreateRequest(BaseModel):
    serviceId: int = Field(..., example=123123, description="Xizmat identifikatori")
    timestamp: int = Field(..., example=1714377645427, description="Yuborilgan vaqt (unix timestamp ms)")
    transId: str = Field(..., example="5c398d7e-76b6-11ee-96da-f3a095c6289d", description="Uzum Bank tranzaksiya UUID")
    params: Dict[str, Any] = Field(..., example={"order_id": "123123"}, description="To'lov parametrlari")
    amount: int = Field(..., example=2500000, description="To'lov summasi tiyinda (100 tiyin = 1 so'm)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "serviceId": 123123,
                "timestamp": 1714377645427,
                "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d",
                "params": {
                    "order_id": "123123"
                },
                "amount": 2500000
            }
        }
    }


class ConfirmRequest(BaseModel):
    serviceId: int = Field(..., example=123123, description="Xizmat identifikatori")
    timestamp: int = Field(..., example=1714377645428, description="Yuborilgan vaqt (unix timestamp ms)")
    transId: str = Field(..., example="5c398d7e-76b6-11ee-96da-f3a095c6289d", description="Uzum Bank tranzaksiya UUID")
    paymentSource: Optional[str] = Field("UZCARD", example="UZCARD", description="Manba: UZCARD, HUMO, VISA, INSTALLMENT, etc.")
    tariff: Optional[str] = Field(None, example="003", description="Tarif (INSTALLMENT bo'lsa: '003', '15-0-4')")
    processingReferenceNumber: Optional[str] = Field(None, example="00012345", description="Protsessing raqami")
    phone: Optional[str] = Field(None, example="998901234567", description="Mijoz telefon raqami")
    cardType: Optional[int] = Field(None, example=2, description="1 - korporativ, 2 - jismoniy shaxs")

    model_config = {
        "json_schema_extra": {
            "example": {
                "serviceId": 123123,
                "timestamp": 1714377645428,
                "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d",
                "paymentSource": "UZCARD",
                "tariff": None,
                "processingReferenceNumber": "00012345",
                "phone": "998901234567",
                "cardType": 2
            }
        }
    }


class ReverseRequest(BaseModel):
    serviceId: int = Field(..., example=123123, description="Xizmat identifikatori")
    timestamp: int = Field(..., example=1714377645430, description="Yuborilgan vaqt (unix timestamp ms)")
    transId: str = Field(..., example="5c398d7e-76b6-11ee-96da-f3a095c6289d", description="Uzum Bank tranzaksiya UUID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "serviceId": 123123,
                "timestamp": 1714377645430,
                "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d"
            }
        }
    }


class StatusRequest(BaseModel):
    serviceId: int = Field(..., example=123123, description="Xizmat identifikatori")
    timestamp: int = Field(..., example=1714377645429, description="Yuborilgan vaqt (unix timestamp ms)")
    transId: str = Field(..., example="5c398d7e-76b6-11ee-96da-f3a095c6289d", description="Uzum Bank tranzaksiya UUID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "serviceId": 123123,
                "timestamp": 1714377645429,
                "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d"
            }
        }
    }


# ─── Xato Kodlari Konstantalari ───────────────────────────────────────────────
class UzumErrorCode:
    UNAUTHORIZED = "10001"                         # Доступ запрещен
    ERROR_PARSING_JSON = "10002"                   # Ошибка парсинга JSON
    INVALID_OPERATION = "10003"                    # Недопустимая операция
    MISSING_REQUIRED_PARAMS = "10005"              # Отсутствуют обязательные параметры
    INVALID_SERVICE_ID = "10006"                   # Неверный serviceId
    ACCOUNT_NOT_FOUND = "10007"                    # Дополнительный атрибут платежа не найден
    PAYMENT_ALREADY_PAID = "10008"                 # Платеж уже оплачен
    PAYMENT_CANCELLED = "10009"                    # Платеж отменен
    TRANSACTION_ALREADY_EXISTS = "10010"           # Транзакция уже создана
    INVALID_AMOUNT = "10011"                       # Неверная сумма
    AMOUNT_BELOW_MIN = "10012"                     # Сумма оплаты ниже минимальной
    AMOUNT_ABOVE_MAX = "10013"                     # Сумма оплаты превышает максимальную
    TRANSACTION_NOT_FOUND = "10014"                # Транзакция не найдена
    TRANSACTION_CANCELLED = "10015"                # Транзакция отменена
    TRANSACTION_ALREADY_CONFIRMED = "10016"        # Транзакция уже подтверждена
    CANNOT_REVERSE = "10017"                       # Невозможно отменить транзакцию
    TRANSACTION_ALREADY_REVERSED = "10018"         # Транзакция уже отменена
    INTERNAL_ERROR = "99999"                       # Внутренняя ошибка сервера


def _now_ms() -> int:
    return int(time.time() * 1000)


def _err_response(service_id: Any, error_code: str, trans_id: Optional[str] = None) -> JSONResponse:
    """Uzum Bank spetsifikatsiyasi bo'yicha xato javobi (HTTP 400)."""
    payload: Dict[str, Any] = {
        "serviceId": int(service_id) if str(service_id).isdigit() else service_id,
        "timestamp": _now_ms(),
        "status": "FAILED",
        "errorCode": str(error_code),
    }
    if trans_id:
        payload["transId"] = str(trans_id)
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)


def _check_basic_auth(authorization: Optional[str]) -> bool:
    """HTTP Basic Authorization sarlavhasini tekshiradi."""
    if not authorization:
        return False
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        decoded = base64.b64decode(token).decode("utf-8")
        username, password = decoded.split(":", 1)
        
        cfg_user = settings.UZUM_USERNAME or "123123"
        cfg_pass = settings.UZUM_PASSWORD or "123123"
        
        return username == cfg_user and password == cfg_pass
    except Exception as exc:
        logger.warning("[Uzum] Basic auth tekshirishda xatolik: %s", exc)
        return False


def _is_valid_service_id(service_id: Any) -> bool:
    """serviceId mosligini tekshiradi."""
    if service_id is None:
        return False
    cfg_sid = str(settings.UZUM_SERVICE_ID or "123123")
    incoming_sid = str(service_id)
    if settings.UZUM_IS_TEST and incoming_sid in (cfg_sid, "123123", "5555", "101202", "498615742"):
        return True
    return incoming_sid == cfg_sid


def _resolve_account(account_val: str, db: Session) -> Optional[Company]:
    account_str = str(account_val).strip()
    if not account_str:
        return None

    # 1. Korxona org_code orqali qidirish
    company = db.query(Company).filter(
        Company.org_code == account_str,
        Company.is_active == True,
    ).first()
    if company:
        return company

    # 2. Agar ID ko'rinishida berilgan bo'lsa
    if account_str.isdigit():
        company = db.query(Company).filter(
            Company.id == int(account_str),
            Company.is_active == True,
        ).first()
        if company:
            return company

    # 3. Test rejimida maxsus test order_id bo'lsa
    if settings.UZUM_IS_TEST and account_str in ("123123", "3256-01-02", "test", "demo"):
        sample_company = db.query(Company).filter(Company.is_active == True).first()
        if sample_company:
            return sample_company

    return None


# ─── 1. POST /check (To'lov imkoniyatini tekshirish) ──────────────────────────
@router.post(
    "/check",
    summary="1. To'lov imkoniyatini tekshirish (/check)",
    description="Uzum Bank foydalanuvchi hisob raqamini (order_id / org_code) kiritganda tekshirish uchun ushbu so'rovni yuboradi."
)
async def check(request: Request, payload: Optional[CheckRequest] = None, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not _check_basic_auth(authorization):
        return _err_response(0, UzumErrorCode.UNAUTHORIZED)

    try:
        body = await request.json()
    except Exception:
        return _err_response(0, UzumErrorCode.ERROR_PARSING_JSON)

    service_id = body.get("serviceId")
    if not _is_valid_service_id(service_id):
        return _err_response(service_id or 0, UzumErrorCode.INVALID_SERVICE_ID)

    params = body.get("params") or {}
    account_val = None
    for key in ("order_id", "user_id", "org_code", "account", "phone", "planId"):
        if key in params and str(params[key]).strip():
            account_val = str(params[key]).strip()
            break

    if not account_val:
        return _err_response(service_id, UzumErrorCode.MISSING_REQUIRED_PARAMS)

    company = _resolve_account(account_val, db)
    if not company and not (settings.UZUM_IS_TEST and account_val in ("123123", "3256-01-02")):
        return _err_response(service_id, UzumErrorCode.ACCOUNT_NOT_FOUND)

    now_ms = _now_ms()
    company_name = company.name if company else "Test Account"

    logger.info("[Uzum] Check OK: serviceId=%s, account=%s (%s)", service_id, account_val, company_name)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "serviceId": int(service_id),
            "timestamp": now_ms,
            "status": "OK",
            "data": {
                "account": {
                    "value": str(account_val)
                },
                "userInfo": {
                    "name": company_name
                }
            }
        }
    )


# ─── 2. POST /create (Tranzaksiya yaratish) ───────────────────────────────────
@router.post(
    "/create",
    summary="2. Tranzaksiya yaratish (/create)",
    description="Foydalanuvchi to'lovni tasdiqlaganda Uzum Bank tomonidan tranzaksiyani yaratish uchun chaqiriladi."
)
async def create(request: Request, payload: Optional[CreateRequest] = None, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not _check_basic_auth(authorization):
        return _err_response(0, UzumErrorCode.UNAUTHORIZED)

    try:
        body = await request.json()
    except Exception:
        return _err_response(0, UzumErrorCode.ERROR_PARSING_JSON)

    service_id = body.get("serviceId")
    if not _is_valid_service_id(service_id):
        return _err_response(service_id or 0, UzumErrorCode.INVALID_SERVICE_ID)

    trans_id = body.get("transId")
    if not trans_id:
        return _err_response(service_id, UzumErrorCode.MISSING_REQUIRED_PARAMS)

    amount = body.get("amount")
    if amount is None or not isinstance(amount, (int, float)):
        return _err_response(service_id, UzumErrorCode.INVALID_AMOUNT, trans_id=trans_id)

    amount_tiyin = int(amount)
    if amount_tiyin <= 0:
        return _err_response(service_id, UzumErrorCode.INVALID_AMOUNT, trans_id=trans_id)
    if amount_tiyin < 100000:
        return _err_response(service_id, UzumErrorCode.AMOUNT_BELOW_MIN, trans_id=trans_id)

    params = body.get("params") or {}
    account_val = None
    for key in ("order_id", "user_id", "org_code", "account", "phone", "planId"):
        if key in params and str(params[key]).strip():
            account_val = str(params[key]).strip()
            break

    # Idempotent tekshirish
    existing = db.query(UzumTransaction).filter(UzumTransaction.trans_id == str(trans_id)).first()
    if existing:
        if existing.status == "CREATED":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "serviceId": int(service_id),
                    "transId": str(existing.trans_id),
                    "status": "CREATED",
                    "transTime": existing.trans_time or _now_ms(),
                    "data": {},
                    "amount": existing.amount
                }
            )
        else:
            return _err_response(service_id, UzumErrorCode.TRANSACTION_ALREADY_EXISTS, trans_id=trans_id)

    company = _resolve_account(account_val or "", db)
    if not company and not (settings.UZUM_IS_TEST and account_val in ("123123", "3256-01-02", None)):
        return _err_response(service_id, UzumErrorCode.ACCOUNT_NOT_FOUND, trans_id=trans_id)

    now_ms = _now_ms()
    company_id = company.id if company else None

    txn = UzumTransaction(
        trans_id=str(trans_id),
        service_id=int(service_id),
        company_id=company_id,
        amount=amount_tiyin,
        status="CREATED",
        account_identifier=str(account_val or ""),
        trans_time=now_ms,
        raw_params=params,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    logger.info("[Uzum] Create OK: transId=%s, amount=%s tiyin, account=%s", trans_id, amount_tiyin, account_val)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "serviceId": int(service_id),
            "transId": str(trans_id),
            "status": "CREATED",
            "transTime": now_ms,
            "data": {},
            "amount": amount_tiyin
        }
    )


# ─── 3. POST /confirm (Tranzaksiyani tasdiqlash) ───────────────────────────────
@router.post(
    "/confirm",
    summary="3. Tranzaksiyani tasdiqlash (/confirm)",
    description="Mijoz kartasidan pul yechib olingach, to'lovni tasdiqlash va xizmat ko'rsatish / balans to'ldirish uchun chaqiriladi."
)
async def confirm(request: Request, payload: Optional[ConfirmRequest] = None, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not _check_basic_auth(authorization):
        return _err_response(0, UzumErrorCode.UNAUTHORIZED)

    try:
        body = await request.json()
    except Exception:
        return _err_response(0, UzumErrorCode.ERROR_PARSING_JSON)

    service_id = body.get("serviceId")
    if not _is_valid_service_id(service_id):
        return _err_response(service_id or 0, UzumErrorCode.INVALID_SERVICE_ID)

    trans_id = body.get("transId")
    if not trans_id:
        return _err_response(service_id, UzumErrorCode.MISSING_REQUIRED_PARAMS)

    txn = db.query(UzumTransaction).filter(UzumTransaction.trans_id == str(trans_id)).first()
    if not txn:
        return _err_response(service_id, UzumErrorCode.TRANSACTION_NOT_FOUND, trans_id=trans_id)

    now_ms = _now_ms()

    # Idempotent: allaqachon tasdiqlangan bo'lsa
    if txn.status == "CONFIRMED":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "serviceId": int(service_id),
                "transId": str(trans_id),
                "status": "CONFIRMED",
                "confirmTime": txn.confirm_time or now_ms,
                "data": {},
                "amount": txn.amount
            }
        )

    # Bekor qilingan tranzaksiya
    if txn.status in ("REVERSED", "FAILED"):
        return _err_response(service_id, UzumErrorCode.TRANSACTION_CANCELLED, trans_id=trans_id)

    # 30 daqiqalik TTL tekshiruvi
    TTL_MS = 30 * 60 * 1000
    if txn.trans_time and (now_ms - txn.trans_time > TTL_MS):
        txn.status = "FAILED"
        db.commit()
        return _err_response(service_id, UzumErrorCode.TRANSACTION_CANCELLED, trans_id=trans_id)

    amount_som = txn.amount / 100.0

    try:
        company = None
        if txn.company_id:
            company = db.query(Company).filter(Company.id == txn.company_id).first()

        log_id = None
        if company:
            company.balance = (float(company.balance) if company.balance else 0.0) + amount_som
            log = BalanceLog(
                company_id=company.id,
                amount=amount_som,
                log_type="top_up",
                note=f"Uzum Bank orqali to'ldirildi: +{amount_som:,.0f} so'm (txn: {trans_id})",
                created_at=datetime.now(timezone.utc)
            )
            db.add(log)
            db.flush()
            log_id = log.id

        txn.status = "CONFIRMED"
        txn.confirm_time = now_ms
        txn.payment_source = body.get("paymentSource")
        txn.tariff = body.get("tariff")
        txn.processing_ref = body.get("processingReferenceNumber")
        txn.phone = body.get("phone")
        txn.card_type = body.get("cardType")
        txn.log_id = log_id

        db.commit()
        logger.info("[Uzum] Confirm OK: transId=%s, amount=%.0f so'm", trans_id, amount_som)

    except Exception as exc:
        db.rollback()
        logger.error("[Uzum] Confirm DB xatolik: %s", exc)
        return _err_response(service_id, UzumErrorCode.INTERNAL_ERROR, trans_id=trans_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "serviceId": int(service_id),
            "transId": str(trans_id),
            "status": "CONFIRMED",
            "confirmTime": now_ms,
            "data": {},
            "amount": txn.amount
        }
    )


# ─── 4. POST /reverse (Tranzaksiyani bekor qilish / qaytarish) ────────────────
@router.post(
    "/reverse",
    summary="4. Tranzaksiyani bekor qilish / qaytarish (/reverse)",
    description="To'lovni bekor qilish yoki mijozga mablag'ni qaytarish."
)
async def reverse(request: Request, payload: Optional[ReverseRequest] = None, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not _check_basic_auth(authorization):
        return _err_response(0, UzumErrorCode.UNAUTHORIZED)

    try:
        body = await request.json()
    except Exception:
        return _err_response(0, UzumErrorCode.ERROR_PARSING_JSON)

    service_id = body.get("serviceId")
    if not _is_valid_service_id(service_id):
        return _err_response(service_id or 0, UzumErrorCode.INVALID_SERVICE_ID)

    trans_id = body.get("transId")
    if not trans_id:
        return _err_response(service_id, UzumErrorCode.MISSING_REQUIRED_PARAMS)

    txn = db.query(UzumTransaction).filter(UzumTransaction.trans_id == str(trans_id)).first()
    if not txn:
        return _err_response(service_id, UzumErrorCode.TRANSACTION_NOT_FOUND, trans_id=trans_id)

    now_ms = _now_ms()

    # Idempotent: allaqachon bekor qilingan
    if txn.status == "REVERSED":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "serviceId": int(service_id),
                "transId": str(trans_id),
                "status": "REVERSED",
                "reverseTime": txn.reverse_time or now_ms,
                "data": {},
                "amount": txn.amount
            }
        )

    if txn.status not in ("CREATED", "CONFIRMED"):
        return _err_response(service_id, UzumErrorCode.CANNOT_REVERSE, trans_id=trans_id)

    try:
        if txn.status == "CONFIRMED" and txn.company_id:
            amount_som = txn.amount / 100.0
            company = db.query(Company).filter(Company.id == txn.company_id).first()
            if company:
                company.balance = (float(company.balance) if company.balance else 0.0) - amount_som
                refund_log = BalanceLog(
                    company_id=company.id,
                    amount=-amount_som,
                    log_type="refund",
                    note=f"Uzum Bank to'lovi bekor qilindi: -{amount_som:,.0f} so'm (txn: {trans_id})",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(refund_log)

        txn.status = "REVERSED"
        txn.reverse_time = now_ms
        db.commit()
        logger.info("[Uzum] Reverse OK: transId=%s", trans_id)

    except Exception as exc:
        db.rollback()
        logger.error("[Uzum] Reverse DB xatolik: %s", exc)
        return _err_response(service_id, UzumErrorCode.INTERNAL_ERROR, trans_id=trans_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "serviceId": int(service_id),
            "transId": str(trans_id),
            "status": "REVERSED",
            "reverseTime": now_ms,
            "data": {},
            "amount": txn.amount
        }
    )


# ─── 5. POST /status (Tranzaksiya holatini tekshirish) ────────────────────────
@router.post(
    "/status",
    summary="5. Tranzaksiya holatini tekshirish (/status)",
    description="Tranzaksiyaning joriy holatini (CONFIRMED, CREATED, REVERSED, FAILED) olish."
)
async def status_check(request: Request, payload: Optional[StatusRequest] = None, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not _check_basic_auth(authorization):
        return _err_response(0, UzumErrorCode.UNAUTHORIZED)

    try:
        body = await request.json()
    except Exception:
        return _err_response(0, UzumErrorCode.ERROR_PARSING_JSON)

    service_id = body.get("serviceId")
    if not _is_valid_service_id(service_id):
        return _err_response(service_id or 0, UzumErrorCode.INVALID_SERVICE_ID)

    trans_id = body.get("transId")
    if not trans_id:
        return _err_response(service_id, UzumErrorCode.MISSING_REQUIRED_PARAMS)

    txn = db.query(UzumTransaction).filter(UzumTransaction.trans_id == str(trans_id)).first()
    if not txn:
        return _err_response(service_id, UzumErrorCode.TRANSACTION_NOT_FOUND, trans_id=trans_id)

    now_ms = _now_ms()

    # 30 daqiqadan oshgan yaratilgan tranzaksiya FAILED ga o'tadi
    if txn.status == "CREATED" and txn.trans_time and (now_ms - txn.trans_time > 30 * 60 * 1000):
        txn.status = "FAILED"
        db.commit()

    logger.info("[Uzum] Status query: transId=%s, status=%s", trans_id, txn.status)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "serviceId": int(service_id),
            "transId": str(trans_id),
            "status": txn.status,
            "transTime": txn.trans_time,
            "confirmTime": txn.confirm_time,
            "reverseTime": txn.reverse_time,
            "data": {},
            "amount": txn.amount
        }
    )


# ─── 6. Uzum Bank Maxsus Alohida Swagger UI & ReDoc ──────────────────────────
@router.get("/openapi.json", include_in_schema=False)
async def uzum_custom_openapi(request: Request):
    """Faqat Uzum Bank endpointlari uchun alohida toza OpenAPI JSON."""
    schema = get_openapi(
        title="Uzum Bank Merchant API (1.0.0)",
        version="1.0.0",
        description=(
            "### Uzum Bank Merchant API Integratsiya Hujjati\n\n"
            "Ushbu sahifa faqat Uzum Bank API tekshiruvchilari va dasturchilari uchun tayyorlangan.\n\n"
            "**Avtorizatsiya:**\n"
            "- Har bir so'rovda `Authorization: Basic <base64(username:password)>` talab qilinadi.\n"
            "- Test username: `123123`\n"
            "- Test password: `123123`\n"
            "- Test serviceId: `123123`\n"
            "- Test hisob raqami (`order_id`): `123123`"
        ),
        routes=[
            r for r in router.routes 
            if getattr(r, "path", "").endswith(("/check", "/create", "/confirm", "/reverse", "/status"))
        ],
    )
    # Basic auth security qo'shish
    schema["components"] = schema.get("components", {})
    schema["components"]["securitySchemes"] = {
        "basicAuth": {
            "type": "http",
            "scheme": "basic",
            "description": "Uzum Bank Basic Auth (username:password)"
        }
    }
    for path_item in schema.get("paths", {}).values():
        for method_item in path_item.values():
            if isinstance(method_item, dict):
                method_item["security"] = [{"basicAuth": []}]

    # Agar so'rov /api/uzum orqali kelgan bo'lsa, yo'llarni ham /api bilan qaytaramiz
    if request.url.path.startswith("/api"):
        new_paths = {}
        for path_k, path_v in schema.get("paths", {}).items():
            new_k = "/api" + path_k if not path_k.startswith("/api") else path_k
            new_paths[new_k] = path_v
        schema["paths"] = new_paths

    return schema


@router.get("/docs", include_in_schema=False)
async def uzum_docs(request: Request):
    """Faqat Uzum Bank metodlari aks etadigan maxsus Swagger UI."""
    prefix = "/api/uzum" if request.url.path.startswith("/api") else "/uzum"
    return get_swagger_ui_html(
        openapi_url=f"{prefix}/openapi.json",
        title="Uzum Bank Merchant API — Swagger UI",
        swagger_favicon_url="https://uzumbank.uz/favicon.ico",
    )


@router.get("/redoc", include_in_schema=False)
async def uzum_redoc(request: Request):
    """Faqat Uzum Bank metodlari aks etadigan maxsus ReDoc hujjati."""
    prefix = "/api/uzum" if request.url.path.startswith("/api") else "/uzum"
    return get_redoc_html(
        openapi_url=f"{prefix}/openapi.json",
        title="Uzum Bank Merchant API — ReDoc",
    )
