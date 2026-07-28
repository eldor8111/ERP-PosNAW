
from fastapi import APIRouter, HTTPException, UploadFile, File, Query

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

router = APIRouter(prefix="/hippo", tags=["Hippo Fiskalizatsiya"])


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
def get_fiscal_modules():
    try:
        return hippo_service.get_fiscal_modules()
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/fiscal-modules/{factory_id}/sync")
def sync_fiscal_module(factory_id: str):
    try:
        return hippo_service.sync_fiscal_module(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/fiscal-modules/info")
def get_fiscal_module_info(factory_id: str = Query(...)):
    try:
        return hippo_service.get_fiscal_module_info(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/fiscal-modules/memory-info")
def get_fiscal_module_memory_info(factory_id: str = Query(...)):
    try:
        return hippo_service.get_fiscal_module_memory_info(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Receipts -------------------------------------------------------------

@router.post("/receipt/register")
def register_receipt(request: RegisterReceiptRequest):
    try:
        return hippo_service.register_receipt(request)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/receipt")
def get_receipt(factory_id: str = Query(...), receipt_index: int = Query(0)):
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
def list_receipts():
    try:
        return hippo_service.list_receipts()
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/receipts/current-shift")
def get_current_shift(factory_id: str = Query(...)):
    try:
        return hippo_service.get_current_shift(factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Z-report ----------------------------------------------------------------

@router.post("/z-report/open")
def open_z_report(request: ZReportRequest):
    try:
        return hippo_service.open_z_report(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/z-report/close")
def close_z_report(request: ZReportRequest):
    try:
        return hippo_service.close_z_report(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/z-report")
def get_z_report(factory_id: str = Query(...), index: int = Query(0)):
    try:
        return hippo_service.get_z_report(factory_id, index)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/z-report/unacknowledged")
def get_unacknowledged_z_reports(request: ZReportRequest):
    try:
        return hippo_service.get_unacknowledged_z_report_indexes(request.factory_id)
    except HippoClientError as exc:
        _map_exception(exc)


# -- Sync -------------------------------------------------------------------

@router.post("/sync/receipts")
def sync_receipts(request: SyncRequestModel):
    try:
        return hippo_service.sync_receipts(request.factory_id, request.items_count)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/sync/z-reports")
def sync_z_reports(request: SyncRequestModel):
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
def update_settings(data: UpdateSettingsRequestModel):
    try:
        return hippo_service.update_settings(data)
    except HippoClientError as exc:
        _map_exception(exc)


@router.post("/settings/logo")
def upload_logo(file: UploadFile = File(...)):
    try:
        content = file.file.read()
        return hippo_service.upload_logo(content, file.filename, file.content_type)
    except HippoClientError as exc:
        _map_exception(exc)


@router.get("/printers")
def get_printers():
    try:
        return hippo_service.get_printers()
    except HippoClientError as exc:
        _map_exception(exc)
