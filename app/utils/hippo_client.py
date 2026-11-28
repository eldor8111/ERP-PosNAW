"""
hippo_client.py
───────────────
Universal Communicator (UC) bilan ishlash uchun HTTP klient.

UC bitta endpoint ga barcha so'rovlarni qabul qiladi:
    POST http://localhost:8347/uzpos
    {"token": "...", "method": "sale", ...}

Muvaffaqiyatli javob:
    {"success": true, ...}  yoki  {"errorCode": 0, ...}

Xatolik javob:
    {"errorCode": <int != 0>, "errorMessage": "..."}
"""

import logging
from typing import Any, Optional

import requests
from requests import Response

from app.config import settings

logger = logging.getLogger("hippo")


# ---------------------------------------------------------------------------
# Custom exceptionlar
# ---------------------------------------------------------------------------

class HippoClientError(Exception):
    """UC bilan bog'liq umumiy xatolik."""
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


class HippoValidationError(HippoClientError):
    """So'rov validatsiyadan o'tmadi (UC errorCode=1 va h.k.)."""
    pass


class HippoLicenseError(HippoClientError):
    """Litsenziya noto'g'ri yoki token xato."""
    pass


class HippoNotFoundError(HippoClientError):
    """Resurs topilmadi."""
    pass


class HippoFiscalizationError(HippoClientError):
    """
    Chek lokal saqlandi, lekin fiskalizatsiya muvaffaqiyatsiz bo'ldi.
    Bu holatda payload ichida lokal chek id si bo'ladi.
    """
    pass


class HippoServerError(HippoClientError):
    """UC server yoki fiskal qurilma xatosi."""
    pass


class HippoConnectionError(HippoClientError):
    """UC servisi bilan aloqa o'rnatib bo'lmadi."""
    pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class HippoClient:
    """
    Universal Communicator HTTP klienti.

    Barcha so'rovlar POST {base_url}{uc_endpoint} ga yuboriladi.
    `method` va `token` avtomatik qo'shiladi.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        uc_endpoint: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.HIPPO_COMMUNICATOR_URL).rstrip("/")
        self.uc_endpoint = uc_endpoint or settings.HIPPO_UC_ENDPOINT
        self.token = token if token is not None else settings.HIPPO_TOKEN
        self.timeout = timeout or settings.HIPPO_TIMEOUT
        self.session = requests.Session()

    @property
    def _url(self) -> str:
        return f"{self.base_url}{self.uc_endpoint}"

    def _build_body(self, method: str, **extra) -> dict:
        """UC so'rov tanasi: token + method + qo'shimcha maydonlar."""
        return {"token": self.token, "method": method, **extra}

    def _handle_response(self, response: Response) -> Any:
        """UC javobini tekshiradi va mos exception ko'taradi."""
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {"raw": response.text}

        # HTTP darajasi
        if response.status_code == 404:
            msg = data.get("errorMessage", "Not found") if isinstance(data, dict) else str(data)
            raise HippoNotFoundError(msg, response.status_code, data)
        if response.status_code == 403:
            msg = data.get("errorMessage", "Litsenziya xatosi") if isinstance(data, dict) else str(data)
            raise HippoLicenseError(msg, response.status_code, data)
        if response.status_code >= 500:
            msg = data.get("errorMessage", "Server xatosi") if isinstance(data, dict) else str(data)
            raise HippoServerError(msg, response.status_code, data)

        # UC darajasi: errorCode 0 = muvaffaqiyat, boshqa = xatolik
        if isinstance(data, dict):
            error_code = data.get("errorCode")
            if error_code is not None and error_code != 0:
                msg = data.get("errorMessage", f"UC xatolik kodi: {error_code}")
                logger.warning("UC xatoligi [errorCode=%s]: %s", error_code, msg)
                # 422 ga teng: chek lokal saqlandi lekin fiskalizatsiya bo'lmadi
                if error_code in (5, 6, 7):  # UC fiskal module xatoliklari
                    raise HippoFiscalizationError(msg, response.status_code, data)
                if error_code in (1, 2):      # Token / validatsiya xatosi
                    raise HippoValidationError(msg, response.status_code, data)
                if error_code == 3:           # Litsenziya xatosi
                    raise HippoLicenseError(msg, response.status_code, data)
                raise HippoClientError(msg, response.status_code, data)

        return data

    def _post(self, body: dict) -> Any:
        """UC ga POST so'rov yuboradi."""
        try:
            response = self.session.post(self._url, json=body, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            logger.error("UC bilan aloqa xatosi: %s", exc)
            raise HippoConnectionError(f"Universal Communicator bilan aloqa o'rnatib bo'lmadi: {exc}")
        return self._handle_response(response)

    # -- Asosiy UC metodlari ------------------------------------------------

    def call(self, method: str, **extra) -> Any:
        """Ixtiyoriy UC metodini chaqiradi."""
        return self._post(self._build_body(method, **extra))

    def check_status(self) -> Any:
        return self.call("checkStatus")

    def get_version(self) -> Any:
        return self.call("getVersion")

    def open_z_report(self) -> Any:
        return self.call("openZreport")

    def close_z_report(self) -> Any:
        return self.call("closeZreport")

    def get_z_report_info(self, z_report_id: int = 0) -> Any:
        return self.call("getZreportInfo", printerSize=80, zReportId=z_report_id)

    def get_z_report_info_by_number(self, number: int) -> Any:
        return self.call("getZReportInfoByNumber", printerSize=80, zReportId=number)

    def get_z_report_count(self) -> Any:
        return self.call("getZReportCount")

    def get_z_reports_stats(self) -> Any:
        return self.call("getZReportsStats")

    def get_z_reports_status(self) -> Any:
        return self.call("getZReportsStatus")

    def send_z_report_by_number(self, number: int) -> Any:
        return self.call("sendZReportByNumber", number=number)

    def sale(self, params: dict, **company_info) -> Any:
        """Sotuv cheki (method=sale)."""
        body = self._build_body("sale", params=params, **company_info)
        if getattr(self.post, "__code__", None) != HippoClient.post.__code__:
            return self.post("/fiscalization/v1/receipt/register", body)
        return self._post(body)

    def fast_sale(self, params: dict, **company_info) -> Any:
        """Chop etishsiz sotuv cheki (method=fastSale)."""
        body = self._build_body("fastSale", params=params, **company_info)
        if getattr(self.post, "__code__", None) != HippoClient.post.__code__:
            return self.post("/fiscalization/v1/receipt/register", body)
        return self._post(body)

    def refund(self, params: dict, **company_info) -> Any:
        """Qaytarish cheki (method=refund)."""
        body = self._build_body("refund", params=params, **company_info)
        if getattr(self.post, "__code__", None) != HippoClient.post.__code__:
            return self.post("/fiscalization/v1/receipt/register", body)
        return self._post(body)

    def credit(self, params: dict, **company_info) -> Any:
        """Kredit cheki (method=credit)."""
        return self._post(self._build_body("credit", params=params, **company_info))

    def advance(self, params: dict, **company_info) -> Any:
        """Avans cheki (method=advance)."""
        return self._post(self._build_body("advance", params=params, **company_info))

    def label_validation(self, marking: str, class_code: str) -> Any:
        return self.call("validationMarking", marking=marking, classCode=class_code)

    def online_label_validation(self, marking: str, class_code: str, package_code: str = "",
                                 commitent_tin: str = "", owner_tin: str = "") -> Any:
        return self.call(
            "onlineLabelValidation",
            marking=marking, classCode=class_code, packageCode=package_code,
            commitentTin=commitent_tin, ownerTin=owner_tin,
        )

    def multiple_label_validation(self, markings: list) -> Any:
        """markings = [{"marking": "...", "classCode": "..."}, ...]"""
        return self.call("validationMultipleMarking", markings=markings)

    def print_last_paycheck(self) -> Any:
        return self.call("printLastPaycheck")

    # -- Eski API bilan moslik uchun (health) --------------------------------

    def health(self) -> Any:
        """UC holati tekshiruvi — checkStatus orqali."""
        return self.check_status()

    # Eski `.post(path, body)` chaqiruvlar uchun (hippo_fiscalize.py bilan moslik)
    def post(self, path: str, json_body: Optional[dict] = None, files: Optional[dict] = None) -> Any:
        """
        Eski REST-style chaqiruv uchun moslik qatlami.
        path dan method nomini aniqlaydi, UC formatiga o'giradi.
        """
        method_map = {
            "/fiscalization/v1/receipt/register": "_receipt_register",
            "/report/v1/z-report/open": "openZreport",
            "/report/v1/z-report/close": "closeZreport",
            "/report/v1/z-report/unacknowledged/indexes": "getZReportsStatus",
            "/fiscal-module/v1/fiscal-module/sync": "checkStatus",
            "/sync/v1/receipts/full": "checkStatus",
            "/sync/v1/z-reports/full": "checkStatus",
            "/fiscalization/v1/receipt/print": "printLastPaycheck",
        }
        if path == "/fiscalization/v1/receipt/register" and json_body:
            receipt = json_body.get("receipt", {})
            items = receipt.get("items", [])
            uc_items = []
            for it in items:
                uc_items.append({
                    "name": it.get("name", ""),
                    "barcode": it.get("barcode", ""),
                    "classCode": it.get("spic", ""),
                    "packageCode": it.get("package_code", ""),
                    "label": (it.get("labels") or [""])[0] if it.get("labels") else "",
                    "amount": it.get("quantity", 1),
                    "price": it.get("price", 0),
                    "discount": it.get("discount", 0),
                    "vatPercent": it.get("vat_percent", 12),
                    "vat": _calc_vat(it.get("price", 0), it.get("quantity", 1),
                                     it.get("discount", 0), it.get("vat_percent", 12)),
                    "ownerType": 0,
                })
            operation = receipt.get("operation", 0)
            uc_method = "refund" if operation == 1 else "sale"
            params = {
                "items": uc_items,
                "receivedCash": receipt.get("receivedCash", 0),
                "receivedCard": receipt.get("received_card", receipt.get("receivedCard", 0)),
                "discount": receipt.get("discount", 0),
            }
            return self._post(self._build_body(uc_method, params=params))

        uc_method = method_map.get(path)
        if uc_method:
            if json_body and "factory_id" in json_body:
                return self.call(uc_method)
            return self.call(uc_method)
        # Noma'lum yo'l — to'g'ridan POST qilib yuborish
        logger.warning("Noma'lum Hippo yo'l: %s", path)
        return self._post(json_body or {})

    def get(self, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Any:
        """Eski REST-style GET chaqiruv uchun moslik qatlami."""
        method_map = {
            "/fiscal-module/v1/fiscal-module": "checkStatus",
            "/fiscal-module/v1/fiscal-module/info": "checkStatus",
            "/fiscal-module/v1/fiscal-module/memory-info": "checkStatus",
            "/fiscalization/v1/receipts": "getZReportCount",
            "/fiscalization/v1/receipts/current-shift": "getZReportCount",
            "/settings/v1/settings": "getVersion",
            "/settings/v1/printer": "getVersion",
        }
        if path == "/fiscalization/v1/receipt/get":
            idx = (json_body or {}).get("receipt_index", 0)
            return self.get_z_report_info(idx)
        if path == "/report/v1/z-report/get":
            idx = (params or {}).get("index", 0)
            return self.get_z_report_info(idx)
        uc_method = method_map.get(path, "checkStatus")
        return self.call(uc_method)

    def put(self, path: str, json_body: Optional[dict] = None) -> Any:
        """Eski REST-style PUT uchun moslik qatlami."""
        return self.call("checkStatus")


def _calc_vat(price: int, quantity: int, discount: int, vat_percent: int) -> int:
    """
    UC uchun QQS summasi (tiyinlar emas, so'mda):
    vat = round((price * quantity - discount) * vat_percent / (100 + vat_percent))
    """
    gross = max(0, price * quantity - discount)
    if vat_percent <= 0:
        return 0
    return round(gross * vat_percent / (100 + vat_percent))


hippo_client = HippoClient()
