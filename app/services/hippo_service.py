"""
hippo_service.py
────────────────
Universal Communicator (UC) bilan ishlash uchun servis qatlami.

Barcha UC metodlari hippo_client orqali bitta POST /uzpos endpointiga yuboriladi.
"""

import logging
from typing import Optional

from app.schemas.hippo import (
    RegisterReceiptRequest,
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
        """UC holati: checkStatus metodi."""
        return self.client.check_status()

    def get_version(self) -> dict:
        """UC versiyasi: getVersion metodi."""
        return self.client.get_version()

    # -- Fiscal module --------------------------------------------------

    def get_fiscal_modules(self) -> list:
        """UC da ro'yxatdagi fiskal modullar (checkStatus javobidan olinadi)."""
        result = self.client.check_status()
        # UC checkStatus fiskal modul ma'lumotini qaytaradi
        # Ro'yxat ko'rinishida qaytaramiz (mavjud frontend bilan moslik)
        if isinstance(result, dict):
            return [result]
        return result if isinstance(result, list) else [result]

    def sync_fiscal_module(self, factory_id: str) -> dict:
        """UC sinxronizatsiya (checkStatus orqali)."""
        return self.client.check_status()

    def get_fiscal_module_info(self, factory_id: str) -> dict:
        """UC modul ma'lumoti."""
        return self.client.check_status()

    def get_fiscal_module_memory_info(self, factory_id: str) -> dict:
        """UC xotira ma'lumoti."""
        return self.client.check_status()

    # -- Receipts ---------------------------------------------------------

    def register_receipt(self, request: RegisterReceiptRequest) -> dict:
        """
        Chekni UC ga ro'yxatdan o'tkazadi.
        `request.receipt.operation` = 0 → sale, 1 → refund.
        """
        receipt = request.receipt
        items = []
        for it in (receipt.items or []):
            labels = it.labels or []
            label = labels[0] if labels else ""
            vat_pct = it.vat_percent if it.vat_percent is not None else 12
            price = it.price or 0
            amount = it.quantity or 1
            discount = it.discount or 0
            from app.utils.hippo_client import _calc_vat
            items.append({
                "name":        it.name,
                "barcode":     it.barcode or "",
                "classCode":   it.spic or "",
                "packageCode": it.package_code or "",
                "label":       label,
                "amount":      amount,
                "price":       price,
                "discount":    discount,
                "vatPercent":  vat_pct,
                "vat":         _calc_vat(price, amount, discount, vat_pct),
                "ownerType":   0,
            })

        params = {
            "receivedCash":  receipt.receivedCash or 0,
            "receivedCard":  receipt.received_card or 0,
            "discount":      receipt.discount or 0,
            "items":         items,
        }

        try:
            operation = receipt.operation.value if hasattr(receipt.operation, "value") else int(receipt.operation)
            if operation == 1:
                return self.client.refund(params)
            return self.client.sale(params)
        except HippoFiscalizationError as exc:
            logger.warning(
                "Chek fiskalizatsiya qilinmadi, lokal saqlandi. factory_id=%s, payload=%s",
                request.factory_id, exc.payload,
            )
            raise

    def get_receipt(self, factory_id: str, receipt_index: int = 0) -> dict:
        """Chek ma'lumotini olish — Z-report info orqali."""
        return self.client.get_z_report_info(receipt_index)

    def print_receipt(self, local_id: int) -> dict:
        """Oxirgi chekni chop etish."""
        return self.client.print_last_paycheck()

    def list_receipts(self) -> list:
        """Cheklar ro'yxati (UC da to'g'ridan mavjud emas — Z-report count orqali)."""
        result = self.client.get_z_report_count()
        if isinstance(result, list):
            return result
        return [result] if isinstance(result, dict) else []

    def get_current_shift(self, factory_id: str) -> dict:
        """Joriy smena ma'lumoti."""
        return self.client.get_z_reports_status()

    # -- Z-report -----------------------------------------------------------

    def open_z_report(self, factory_id: str) -> dict:
        """Kassa smenasini ochish: UC openZreport."""
        return self.client.open_z_report()

    def close_z_report(self, factory_id: str) -> dict:
        """Kassa smenasini yopish: UC closeZreport."""
        return self.client.close_z_report()

    def get_z_report(self, factory_id: str, index: int = 0) -> dict:
        """Z-report ma'lumoti: UC getZreportInfo."""
        return self.client.get_z_report_info(index)

    def get_unacknowledged_z_report_indexes(self, factory_id: str) -> dict:
        """Tasdiqlanmagan Z-reportlar: UC getZReportsStatus."""
        return self.client.get_z_reports_status()

    # -- Sync -----------------------------------------------------------

    def sync_receipts(self, factory_id: str, items_count: int = 50) -> dict:
        """Cheklar sinxronizatsiyasi (UC da alohida metod yo'q — checkStatus)."""
        return self.client.check_status()

    def sync_z_reports(self, factory_id: str, items_count: int = 50) -> dict:
        """Z-reportlar sinxronizatsiyasi."""
        return self.client.get_z_reports_stats()

    # -- Settings ---------------------------------------------------------

    def get_settings(self) -> dict:
        """UC versiya ma'lumoti (sozlamalar o'rniga)."""
        return self.client.get_version()

    def update_settings(self, data: UpdateSettingsRequestModel) -> dict:
        """UC sozlamalari (bevosita UC da mavjud emas — versiya qaytariladi)."""
        logger.info("UC sozlamalari yangilash so'rovi (UC da to'g'ridan qo'llab-quvvatlanmaydi)")
        return self.client.get_version()

    def upload_logo(self, file_bytes: bytes, filename: str, content_type: str) -> dict:
        """Logo yuklash (UC da mavjud emas)."""
        logger.info("UC logo yuklash so'rovi (UC da qo'llab-quvvatlanmaydi)")
        return {"ok": True, "message": "UC logo yuklanishini qo'llab-quvvatlamaydi"}

    def get_printers(self) -> dict:
        """Printerlar ro'yxati (UC getVersion dan olinadi)."""
        return self.client.get_version()

    # -- Markirovka -------------------------------------------------------

    def validate_label(self, marking: str, class_code: str) -> dict:
        """Markirovka tekshiruvi: UC validationMarking."""
        return self.client.label_validation(marking, class_code)

    def online_validate_label(self, marking: str, class_code: str, package_code: str = "",
                              commitent_tin: str = "", owner_tin: str = "") -> dict:
        """Onlayn markirovka tekshiruvi."""
        return self.client.online_label_validation(marking, class_code, package_code, commitent_tin, owner_tin)

    def validate_multiple_labels(self, markings: list) -> dict:
        """Ko'p markirovka tekshiruvi."""
        return self.client.multiple_label_validation(markings)

    # -- Z-report qo'shimcha -----------------------------------------------

    def get_z_report_count(self) -> dict:
        return self.client.get_z_report_count()

    def get_z_report_info_by_number(self, number: int) -> dict:
        return self.client.get_z_report_info_by_number(number)

    def send_z_report_by_number(self, number: int) -> dict:
        return self.client.send_z_report_by_number(number)

    def get_z_reports_stats(self) -> dict:
        return self.client.get_z_reports_stats()


hippo_service = HippoService()
