import re
from datetime import datetime, timedelta
from typing import Dict, Any

import httpx

from app.config import settings


class EskizService:
    def __init__(self):
        self.base_url = settings.ESKIZ_BASE_URL
        self.email = settings.ESKIZ_EMAIL
        self.password = settings.ESKIZ_PASSWORD
        self.from_whom = settings.ESKIZ_FROM
        self._token = None
        self._token_expires_at = None
        self.prefix_list = ["20", "33", "50", "55", "77", "88", "90", "91", "93", "94", "95", "97", "98", "99"]

    def clean_phone(self, phone: str) -> str:
        """O'zbekiston telefon raqamini normalizatsiya qiladi."""
        if not phone:
            return ""

        digits = re.sub(r'\D', '', phone)

        if len(digits) == 12 and digits.startswith("998"):
            if digits[3:5] in self.prefix_list:
                return digits

        if len(digits) == 9 and digits.startswith(tuple(self.prefix_list)):
            return "998" + digits

        return ""

    async def _get_token(self) -> str:
        """Eskiz API tokenini oladi yoki keshdan qaytaradi."""
        if self._token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._token

        if not self.email or not self.password:
            raise Exception("Eskiz email yoki password sozlanmagan")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.base_url}/auth/login",
                    data={"email": self.email, "password": self.password}
                )
                response.raise_for_status()
                data = response.json()
                self._token = data.get("data", {}).get("token")
                self._token_expires_at = datetime.now() + timedelta(days=25)
                return self._token
        except Exception as e:
            raise Exception(f"Eskiz login xatoligi: {e}")

    async def send_sms(self, phone: str, message: str) -> Dict[str, Any]:
        """SMS yuborish va natijani standart formatda qaytarish."""
        clean_phone = self.clean_phone(phone)
        if not clean_phone:
            return {"success": False, "eskiz_id": None, "error": f"Noto'g'ri telefon raqami: {phone}"}

        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "mobile_phone": clean_phone,
                "message": message,
                "from": self.from_whom
            }

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.base_url}/message/sms/send",
                    data=payload,
                    headers=headers
                )

                # Agar token eskirgan bo'lsa (401), yangilab qaytadan urinib ko'ramiz
                if response.status_code == 401:
                    self._token = None
                    token = await self._get_token()
                    headers = {"Authorization": f"Bearer {token}"}
                    response = await client.post(
                        f"{self.base_url}/message/sms/send",
                        data=payload,
                        headers=headers
                    )

                response.raise_for_status()
                res_data = response.json()
                eskiz_id = str(res_data.get("id") or res_data.get("data", {}).get("id") or "")
                return {
                    "success": True,
                    "eskiz_id": eskiz_id,
                    "error": None
                }

        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text}"
            return {"success": False, "eskiz_id": None, "error": error}
        except Exception as e:
            return {
                "success": False,
                "eskiz_id": None,
                "error": str(e)
            }

    async def get_balance(self) -> Dict[str, Any]:
        """Balans ma'lumotlarini olish."""
        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/nick/me",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                balance = data.get("data", {}).get("balance")
                return {"balance": balance, "error": None}
        except Exception as e:
            return {"balance": None, "error": str(e)}


# Singleton obyekt yaratamiz
eskiz_service = EskizService()
