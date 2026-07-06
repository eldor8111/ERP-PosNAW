from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.sms_log import SMSLog
from app.models.user import User, UserRole
from app.schemas.sms import SendSMSRequest
from app.services import eskiz_service

router = APIRouter(tags=["SMS"])

SMS_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)


@router.post("/sms/send")
async def send_sms(
        body: SendSMSRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SMS_ROLES)),
):
    """Manuel SMS yuboradi (admin/director uchun)."""
    result = await eskiz_service.send_sms(body.phone, body.message)

    log = SMSLog(
        company_id=current_user.company_id,
        phone=body.phone,
        message=body.message,
        status="sent" if result["success"] else "failed",
        eskiz_id=result.get("eskiz_id"),
        sms_type=body.sms_type,
        error=result.get("error"),
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()

    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"])

    return {"ok": True, "eskiz_id": result["eskiz_id"]}


@router.get("/sms/logs")
def sms_logs(
        limit: int = 50,
        offset: int = 0,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SMS_ROLES)),
):
    """SMS tarixini qaytaradi (faqat o'z kompaniyasi uchun)."""
    rows = (
        db.query(SMSLog)
        .filter(SMSLog.company_id == current_user.company_id)
        .order_by(desc(SMSLog.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "phone": r.phone,
            "message": r.message,
            "status": r.status,
            "eskiz_id": r.eskiz_id,
            "sms_type": r.sms_type,
            "error": r.error,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/sms/balance")
async def sms_balance(
        current_user: User = Depends(require_roles(*SMS_ROLES)),
):
    """Eskiz balansini ko'rsatadi."""
    result = await eskiz_service.get_balance()
    if result["error"]:
        raise HTTPException(status_code=502, detail=result["error"])
    return {"balance": result["balance"]}
