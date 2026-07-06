from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.sms_log import SMSLog
from app.services.eskiz_service import eskiz_service


class NotificationService:

    async def _save_log(self, db: Session, company_id: int, phone: str, message: str, sms_type: str, result: dict):
        """SMS natijasini log bazasiga yozish."""
        log = SMSLog(
            company_id=company_id,
            phone=phone,
            message=message,
            status="sent" if result["success"] else "failed",
            eskiz_id=result.get("eskiz_id"),
            sms_type=sms_type,
            error=result.get("error"),
            created_at=datetime.now(timezone.utc)
        )
        db.add(log)
        db.commit()
        return result

    async def send_debt_reminder(self, customer, db: Session, company_id: int, custom_message: str = None) -> dict:
        """1. Qarz eslatmasi (Debt Reminder)"""
        if not customer.phone:
            return {"success": False, "error": "Mijoz telefon raqami yo'q"}

        message = custom_message or (
            f"Hurmatli {customer.name}!\n\n"
            f"Sizning qarzingiz: {float(customer.debt_balance):,.0f} so'm\n"
            f"Iltimos, qarzni tezroq to'lang.\n\n"
            f"Telefon: {customer.phone}"
        )

        result = await eskiz_service.send_sms(customer.phone, message)
        await self._save_log(db, company_id, customer.phone, message, "debt_reminder", result)
        return result

    async def send_payment_received_notification(
            self, customer, amount: float, remaining_debt: float, db: Session, company_id: int,
            custom_message: str = None
    ) -> dict:
        """2. To'lov eslatmasi (Payment Received)"""
        if not customer.phone:
            return {"success": False, "error": "Mijoz telefon raqami yo'q"}

        if custom_message:
            message = custom_message
        elif remaining_debt > 0:
            message = (
                f"Hurmatli {customer.name}!\n\n"
                f"Siz {amount:,.0f} so'm to'lov qildingiz.\n"
                f"Qolgan qarz: {remaining_debt:,.0f} so'm\n\n"
                f"Rahmat!"
            )
        else:
            message = (
                f"Hurmatli {customer.name}!\n\n"
                f"Siz {amount:,.0f} so'm to'lov qildingiz.\n"
                f"Qarzingiz to'liq to'landi! 🎉\n\n"
                f"Rahmat!"
            )

        result = await eskiz_service.send_sms(customer.phone, message)
        await self._save_log(db, company_id, customer.phone, message, "payment_received", result)
        return result

    async def send_purchase_notification(self, customer, sale, db: Session, company_id: int,
                                         custom_message: str = None) -> dict:
        """3. Mahsulot sotib olish eslatmasi (Purchase Notification)"""
        if not customer.phone:
            return {"success": False, "error": "Mijoz telefon raqami yo'q"}

        if custom_message:
            message = custom_message
        elif getattr(sale, "payment_type", "cash") == "debt":
            message = (
                f"Hurmatli {customer.name}!\n\n"
                f"Siz {float(sale.total_amount):,.0f} so'mlik mahsulot sotib oldingiz (qarzga).\n"
                f"Buyurtma raqami: {sale.number}\n\n"
                f"Iltimos, qarzni vaqtida to'lang."
            )
        else:
            message = (
                f"Hurmatli {customer.name}!\n\n"
                f"Siz {float(sale.total_amount):,.0f} so'mlik mahsulot sotib oldingiz.\n"
                f"Buyurtma raqami: {sale.number}\n\n"
                f"Xaridingiz uchun rahmat!"
            )

        result = await eskiz_service.send_sms(customer.phone, message)
        await self._save_log(db, company_id, customer.phone, message, "purchase_notification", result)
        return result

    async def send_bulk_debt_reminders(self, company_id: int, db: Session, min_debt_amount: float = 10000) -> dict:
        """4. Bulk eslatma (Barcha qarzdorlarga)"""
        # O'zaro circular importni oldini olish uchun modelni funksiya ichida chaqiramiz
        from app.models.customer import Customer

        debtors = (
            db.query(Customer)
            .filter(Customer.company_id == company_id)
            .filter(Customer.debt_balance >= min_debt_amount)
            .all()
        )

        success, failed = 0, 0
        for customer in debtors:
            res = await self.send_debt_reminder(customer=customer, db=db, company_id=company_id)
            if res["success"]:
                success += 1
            else:
                failed += 1

        return {"processed": len(debtors), "success": success, "failed": failed}


# Singleton obyekt yaratamiz
notification_service = NotificationService()
