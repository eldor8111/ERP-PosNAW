
import logging
from typing import Any, Optional

import requests
from requests import Response

from app.config import settings

logger = logging.getLogger("hippo")


# Custom exceptionlar

class HippoClientError(Exception):
    """Hippo bilan bog'liq umumiy xatolik."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


class HippoValidationError(HippoClientError):
    """400 - so'rov validatsiyadan o'tmadi."""
    pass


class HippoLicenseError(HippoClientError):
    """403 - litsenziya noto'g'ri yoki yo'q."""
    pass


class HippoNotFoundError(HippoClientError):
    """404 - resurs topilmadi."""
    pass


class HippoFiscalizationError(HippoClientError):
    """
    422 - chek/lokal saqlandi, lekin fiskalizatsiya muvaffaqiyatsiz bo'ldi.
    Bu holatda payload ichida odatda lokal chek id si bo'ladi - keyin qayta
    urinish (retry) uchun ishlatiladi.
    """
    pass


class HippoServerError(HippoClientError):
    """500 - Hippo server yoki fiskal qurilma xatosi."""
    pass


class HippoConnectionError(HippoClientError):
    """Hippo Communicator servisi bilan aloqa o'rnatib bo'lmadi (masalan, ishga tushmagan)."""
    pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class HippoClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = (base_url or settings.HIPPO_COMMUNICATOR_URL).rstrip("/")
        self.api_prefix = settings.HIPPO_API_PREFIX
        self.timeout = timeout or settings.HIPPO_TIMEOUT
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.api_prefix}{path}"

    def _handle_response(self, response: Response) -> Any:
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {"raw": response.text}

        if response.status_code == 200:
            return data

        message = data.get("error", "Noma'lum xatolik") if isinstance(data, dict) else str(data)
        logger.warning("Hippo xatoligi [%s]: %s", response.status_code, message)

        if response.status_code == 400:
            raise HippoValidationError(message, response.status_code, data)
        if response.status_code == 403:
            raise HippoLicenseError(message, response.status_code, data)
        if response.status_code == 404:
            raise HippoNotFoundError(message, response.status_code, data)
        if response.status_code == 422:
            raise HippoFiscalizationError(message, response.status_code, data)
        if response.status_code >= 500:
            raise HippoServerError(message, response.status_code, data)

        raise HippoClientError(message, response.status_code, data)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = self._url(path)
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            logger.error("Hippo Communicator bilan aloqa xatosi: %s", exc)
            raise HippoConnectionError(f"Hippo Communicator bilan aloqa o'rnatib bo'lmadi: {exc}")
        return self._handle_response(response)

    def get(self, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Any:
        # Eslatma: /receipt/get kabi ba'zi endpointlar GET metodida JSON body qabul qiladi
        return self._request("GET", path, params=params, json=json_body)

    def post(self, path: str, json_body: Optional[dict] = None, files: Optional[dict] = None) -> Any:
        if files:
            return self._request("POST", path, files=files)
        return self._request("POST", path, json=json_body)

    def put(self, path: str, json_body: Optional[dict] = None) -> Any:
        return self._request("PUT", path, json=json_body)

    def health(self) -> Any:
        """GET /health - /api prefiksisiz, root darajada joylashgan."""
        url = f"{self.base_url}/health"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            logger.error("Hippo Communicator bilan aloqa xatosi: %s", exc)
            raise HippoConnectionError(f"Hippo Communicator bilan aloqa o'rnatib bo'lmadi: {exc}")
        return self._handle_response(response)


hippo_client = HippoClient()