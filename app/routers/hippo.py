
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.user import User, UserRole
from app.routers.fiscal_devices import allowed_factory_ids, ensure_factory_access, fiscal_device_for_user
from app.schemas.hippo import (
    RegisterReceiptRequest,
    UpdateSettingsRequestModel,
    ZReportRequest,
    SyncRequestModel,
)
from app.services.hippo_service import hippo_service
from app.utils.hippo_client import (
    HippoClientError,
    HippoValidationError,
    HippoLicenseError,
    HippoNotFoundError,
    HippoFiscalizationError,
    HippoServerError,
    HippoConnectionError,
)

def _hippo_enabled():
    """T3.18: server kommunikatori o'chiq bo'lsa (HIPPO_SERVER_ENABLED=false) /hippo/* umuman yo'q (404).
    Tekshiruv so'rov paytida bajariladi (sozlama o'zgarsa qayta ishga tushirish shart emas)."""
    if not settings.HIPPO_SERVER_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


# Kassa (POS) fiskal amaliyotlari: flag yoqilgan bo'lishi + POS roli (admin/director/manager/cashier) shart.
# super_admin require_roles dan har doim o'tadi. factory_id li endpointlar qo'shimcha ravishda
# fiscal_devices ro'yxati bo'yicha tekshiriladi (korxona/filialga biriktirilmagan qurilma — 403).
router = APIRouter(
    prefix="/hippo",
    tags=["Hippo Fiskalizatsiya"],
    dependencies=[
        Depends(_hippo_enabled),
        Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier)),
    ],
)


def _filter_by_factory(rows, db: Session, user: User):
    """Kommunikator ro'yxatidan foydalanuvchi korxonasi/filialidagi qurilmalar yozuvlarini qoldiradi."""
    allowed = allowed_factory_ids(db, user)
    if allowed is None or not isinstance(rows, list):
        return rows
    return [r for r in rows if isinstance(r, dict) and str(r.get("factory_id", r.get("factoryId", ""))) in allowed]

LOGO_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
LOGO_MAX_SIZE = 5 * 1024 * 1024  # 5 MB


"""HippoClientError turlarini mos HTTP statusga o'giradi."""
def _map_exception(exc: HippoClientError):
    if isinstance(exc, HippoValidationError):
        raise HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, HippoLicenseError):
        raise HTTPException(status_code=403, detail={"error": exc.message, **exc.payload})
    if isinstance(exc, HippoNotFoundError):
        raise HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, HippoFiscalizationError):
        # Chek lokal saqlangan, lekin fiskalizatsiya bo'lmagan - shuni frontendga aniq ko'rsatamiz
        raise HTTPException(status_code=422, detail={"error": exc.message, "local_saved": True, **exc.payload})
    if isinstance(exc, HippoConnectionError):
        raise HTTPException(status_code=503, detail="Hippo Communicator servisiga ulanib bo'lmadi")
    if isinstance(exc, HippoServerError):
        raise HTTPException(status_code=502, detail=exc.message)
    raise HTTPException(status_code=500, detail=exc.message)


# -- System ---------------------------------------------------------------

@router.get("/health")
def health():
    try:
        return hippo_service.check_health()
    except HippoClientError as exc:
        _map_exception(exc)


# -- Fiscal module ----------------------------------------------------------

@router.get("/fiscal-modules")
def get_fiscal_modules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _filter_by_factory(hippo_service.get_fiscal_modules(), db, current_user)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/fiscal-modules/{factory_id}/sync")
def sync_fiscal_module(factory_id: str = Depends(fiscal_device_for_user)):
    try:
        return hippo_service.sync_fiscal_module(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/fiscal-modules/info")
def get_fiscal_module_info(factory_id: str = Depends(fiscal_device_for_user)):
    try:
        return hippo_service.get_fiscal_module_info(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/fiscal-modules/memory-info")
def get_fiscal_module_memory_info(factory_id: str = Depends(fiscal_device_for_user)):
    try:
        return hippo_service.get_fiscal_module_memory_info(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Receipts -------------------------------------------------------------

@router.post("/receipt/register")
def register_receipt(
    request: RegisterReceiptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.register_receipt(request)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/receipt")
def get_receipt(factory_id: str = Depends(fiscal_device_for_user), receipt_index: int = Query(0)):
    try:
        return hippo_service.get_receipt(factory_id, receipt_index)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/receipt/{local_id}/print")
def print_receipt(local_id: int):
    try:
        return hippo_service.print_receipt(local_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/receipts")
def list_receipts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _filter_by_factory(hippo_service.list_receipts(), db, current_user)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/receipts/current-shift")
def get_current_shift(factory_id: str = Depends(fiscal_device_for_user)):
    try:
        return hippo_service.get_current_shift(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Z-report ----------------------------------------------------------------

@router.post("/z-report/open")
def open_z_report(
    request: ZReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.open_z_report(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/z-report/close")
def close_z_report(
    request: ZReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.close_z_report(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/z-report")
def get_z_report(factory_id: str = Depends(fiscal_device_for_user), index: int = Query(0)):
    try:
        return hippo_service.get_z_report(factory_id, index)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/z-report/unacknowledged")
def get_unacknowledged_z_reports(
    request: ZReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.get_unacknowledged_z_report_indexes(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Sync -------------------------------------------------------------------

@router.post("/sync/receipts")
def sync_receipts(
    request: SyncRequestModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.sync_receipts(request.factory_id, request.items_count)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/sync/z-reports")
def sync_z_reports(
    request: SyncRequestModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_factory_access(db, current_user, request.factory_id)
    try:
        return hippo_service.sync_z_reports(request.factory_id, request.items_count)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Settings -----------------------------------------------------------------

@router.get("/settings")
def get_settings():
    try:
        return hippo_service.get_settings()
    except HippoClientError as exc:
        _map_exception(exc)


@router.put("/settings")
def update_settings(
    data: UpdateSettingsRequestModel,
    # Kommunikator butun platforma uchun bitta — sozlamalarni faqat super_admin o'zgartiradi (T3.18)
    current_user: User = Depends(require_roles(UserRole.super_admin)),
):
    try:
        return hippo_service.update_settings(data)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/settings/logo")
def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(UserRole.super_admin)),
):
    if file.content_type not in LOGO_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Faqat JPEG, PNG yoki WEBP rasm qabul qilinadi")
    content = file.file.read()
    if len(content) > LOGO_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Fayl hajmi 5MB dan oshmasligi kerak")
    try:
        return hippo_service.upload_logo(content, file.filename, file.content_type)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/printers")
def get_printers():
    try:
        return hippo_service.get_printers()
    except HippoClientError as exc:
        _map_exception(exc)
