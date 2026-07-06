
import logging
from typing import Optional

from app.schemas.hippo import (
    RegisterReceiptRequest,
    ReceiptGetRequest,
    PrintReceiptRequest,
    FiscalModuleSyncRequest,
    ZReportRequest,
    SyncRequestModel,
    UpdateSettingsRequestModel,
)
from app.utils.hippo_client import hippo_client, HippoFiscalizationError

logger = logging.getLogger("hippo.service")


class HippoService:
    def __init__(self, client=hippo_client):
        self.client = client

    # -- System -------------------------------------------------------
    def check_health(self) -> dict:
        return self.client.health()

    # -- Fiscal module --------------------------------------------------
    def get_fiscal_modules(self) -> list:
        return self.client.get("/fiscal-module/v1/fiscal-module")

    def sync_fiscal_module(self, factory_id: str) -> dict:
        payload = FiscalModuleSyncRequest(factory_id=factory_id)
        return self.client.post("/fiscal-module/v1/fiscal-module/sync", payload.model_dump())

    def get_fiscal_module_info(self, factory_id: str) -> dict:
        return self.client.get("/fiscal-module/v1/fiscal-module/info", params={"factory_id": factory_id})

    def get_fiscal_module_memory_info(self, factory_id: str) -> dict:
        return self.client.get("/fiscal-module/v1/fiscal-module/memory-info", params={"factory_id": factory_id})

    # -- Receipts ---------------------------------------------------------
    def register_receipt(self, request: RegisterReceiptRequest) -> dict:
        """
        Chekni ro'yxatdan o'tkazadi.
        422 kelsa - chek lokal saqlangan, fiskalizatsiya bo'lmagan degani.
        Bu holatni chaqiruvchi kod (router) alohida ushlashi kerak, shuning
        uchun bu yerda xatolikni qayta ko'taramiz (re-raise), lekin log yozamiz.
        """
        try:
            return self.client.post("/fiscalization/v1/receipt/register", request.model_dump())
        except HippoFiscalizationError as exc:
            logger.warning(
                "Chek fiskalizatsiya qilinmadi, lokal saqlandi. factory_id=%s, payload=%s",
                request.factory_id, exc.payload,
            )
            raise

    def get_receipt(self, factory_id: str, receipt_index: int = 0) -> dict:
        payload = ReceiptGetRequest(factory_id=factory_id, receipt_index=receipt_index)
        return self.client.get("/fiscalization/v1/receipt/get", json_body=payload.model_dump())

    def print_receipt(self, local_id: int) -> dict:
        payload = PrintReceiptRequest(id=local_id)
        return self.client.post("/fiscalization/v1/receipt/print", payload.model_dump())

    def list_receipts(self) -> list:
        return self.client.get("/fiscalization/v1/receipts")

    def get_current_shift(self, factory_id: str) -> dict:
        return self.client.get("/fiscalization/v1/receipts/current-shift", params={"factory_id": factory_id})

    # -- Z-report -----------------------------------------------------------
    def open_z_report(self, factory_id: str) -> dict:
        payload = ZReportRequest(factory_id=factory_id)
        return self.client.post("/report/v1/z-report/open", payload.model_dump())

    def close_z_report(self, factory_id: str) -> dict:
        payload = ZReportRequest(factory_id=factory_id)
        return self.client.post("/report/v1/z-report/close", payload.model_dump())

    def get_z_report(self, factory_id: str, index: int = 0) -> dict:
        return self.client.get("/report/v1/z-report/get", params={"factory_id": factory_id, "index": index})

    def get_unacknowledged_z_report_indexes(self, factory_id: str) -> dict:
        payload = ZReportRequest(factory_id=factory_id)
        return self.client.post("/report/v1/z-report/unacknowledged/indexes", payload.model_dump())

    # -- Sync -----------------------------------------------------------
    def sync_receipts(self, factory_id: str, items_count: int = 50) -> dict:
        payload = SyncRequestModel(factory_id=factory_id, items_count=items_count)
        return self.client.post("/sync/v1/receipts/full", payload.model_dump())

    def sync_z_reports(self, factory_id: str, items_count: int = 50) -> dict:
        payload = SyncRequestModel(factory_id=factory_id, items_count=items_count)
        return self.client.post("/sync/v1/z-reports/full", payload.model_dump())

    # -- Settings ---------------------------------------------------------
    def get_settings(self) -> dict:
        return self.client.get("/settings/v1/settings")

    def update_settings(self, data: UpdateSettingsRequestModel) -> dict:
        return self.client.put("/settings/v1/settings", data.model_dump(exclude_unset=True))

    def upload_logo(self, file_bytes: bytes, filename: str, content_type: str) -> dict:
        files = {"logo": (filename, file_bytes, content_type)}
        return self.client.post("/settings/v1/settings/logo", files=files)

    def get_printers(self) -> dict:
        return self.client.get("/settings/v1/printer")


hippo_service = HippoService()