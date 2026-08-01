"""
Avtomatik Scheduler — Fon vazifalar boshqaruvchisi
====================================================
1. Har kuni soat 09:00 da — muddati kelgan qarz eslatmalari (mijozlarga Telegram)
2. Har kuni soat 10:00 da — muddati o'tgan qarzlar haqida rahbarga ogohlantirish (Telegram)
3. Har bir do'konning sozlamasida belgilangan vaqtda — kunlik hisobot:
   • Telegram → rahbar/admin lar
   • FCM Push Notification → rahbar/admin lar (mobil ilova)
"""
import asyncio
from datetime import datetime, date, timezone, timedelta
import httpx

from app.database import SessionLocal
from app.models.sale import Sale, SaleStatus, PaymentType
from app.models.customer import Customer
from app.models.company import Company
from app.models.user import User, UserRole


# ─── Telegram yuboruvchi ─────────────────────────────────────────────────

async def send_tg_msg_async(token: str, chat_id: str, text: str,
                             parse_mode: str = "HTML") -> bool:
    """Telegram orqali xabar yuboradi. True = muvaffaqiyatli."""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            })
            return resp.status_code == 200
    except Exception as e:
        print(f"[TG] Xabar yuborishda xatolik: {e}")
        return False


# ─── FCM Push Notification yuboruvchi ────────────────────────────────────

def _send_fcm_to_managers(company: Company, db, title: str, body: str, data: dict = None):
    """
    Kompaniya rahbar/adminlari uchun FCM push notification yuboradi.
    fcm_token mavjud bo'lgan barcha admin/director larga yuboradi.
    """
    try:
        from app.services.fcm_service import send_multicast_notification
        tokens = []
        managers = db.query(User).filter(
            User.company_id == company.id,
            User.role.in_([UserRole.admin, UserRole.director]),
            User.fcm_token.isnot(None),
        ).all()
        tokens = [u.fcm_token for u in managers if u.fcm_token]
        if not tokens:
            return
        result = send_multicast_notification(
            tokens=tokens,
            title=title,
            body=body,
            data=data or {"type": "daily_report", "company_id": str(company.id)},
        )
        print(
            f"[Scheduler][FCM] {company.name}: {result['success']} ta push yuborildi, "
            f"{result['failure']} ta xato"
        )
    except Exception as e:
        print(f"[Scheduler][FCM] Xatolik ({company.name}): {e}")


# ─── 1. Qarz eslatmalari (Mijozlarga — har kuni soat 09:00) ─────────────

async def process_daily_debts():
    """Muddati yaqin yoki o'tgan qarzdorlarga Telegram xabar yuboradi."""
    db = SessionLocal()
    try:
        today = date.today()
        unpaid_sales = db.query(Sale).filter(
            Sale.status == SaleStatus.completed,
            Sale.payment_type == PaymentType.debt,
            Sale.paid_amount < Sale.total_amount,
            Sale.debt_due_date.isnot(None)
        ).all()

        sent_count = 0
        for sale in unpaid_sales:
            debt_amount = float(sale.total_amount or 0) - float(sale.paid_amount or 0)
            if debt_amount <= 0:
                continue

            customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
            if not customer or not customer.tg_chat_id:
                continue

            company = db.query(Company).filter(Company.id == sale.company_id).first()
            if not company or not company.tg_bot_token:
                continue

            due = sale.debt_due_date
            diff_days = (due - today).days

            msg = None
            if diff_days == 3:
                msg = (
                    f"❗️ <b>Eslatma</b>\n\n"
                    f"Hurmatli <b>{customer.name}</b>,\n"
                    f"<b>{company.name}</b> do'konidan olgan <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingizni to'lash muddatigacha <b>3 kun</b> qoldi.\n"
                    f"To'lov sanasi: <b>{due.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Iltimos, vaqtida to'lashni unutmang!"
                )
            elif diff_days == 1:
                msg = (
                    f"⚡️ <b>Ertaga to'lov kuni!</b>\n\n"
                    f"Hurmatli <b>{customer.name}</b>,\n"
                    f"<b>{company.name}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingiz ertaga (<b>{due.strftime('%d.%m.%Y')}</b>) to'lanishi kerak."
                )
            elif diff_days == 0:
                msg = (
                    f"🚨 <b>Diqqat — Bugun To'lov Kuni!</b>\n\n"
                    f"Hurmatli <b>{customer.name}</b>,\n"
                    f"<b>{company.name}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingizni to'lash muddati <b>bugun</b>!\n"
                    f"Iltimos, kun davomida to'lovni amalga oshiring."
                )
            elif diff_days < 0:
                overdue = abs(diff_days)
                msg = (
                    f"⚠️ <b>Kechiktirilgan To'lov — {overdue} kun!</b>\n\n"
                    f"Hurmatli <b>{customer.name}</b>,\n"
                    f"<b>{company.name}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingiz to'lov muddatidan <b>{overdue} kun</b> o'tib ketdi.\n"
                    f"Zudlik bilan bog'laning yoki to'lovni amalga oshiring!"
                )

            if msg:
                ok = await send_tg_msg_async(company.tg_bot_token, customer.tg_chat_id, msg)
                if ok:
                    sent_count += 1

        print(f"[Scheduler] Qarz eslatmalari: {sent_count} ta xabar yuborildi")

    except Exception as e:
        print(f"[Scheduler] process_daily_debts xatolik: {e}")
    finally:
        db.close()


# ─── 2. Muddati o'tgan qarzlar — Rahbarga ogohlantirish (soat 10:00) ────

async def notify_managers_overdue():
    """Muddati o'tgan qarzdorlar haqida rahbarlarga xabar yuboradi."""
    db = SessionLocal()
    try:
        today = date.today()
        companies = db.query(Company).filter(Company.is_active == True).all()

        for company in companies:
            if not company.tg_bot_token:
                continue

            overdue_sales = db.query(Sale).filter(
                Sale.company_id == company.id,
                Sale.status == SaleStatus.completed,
                Sale.payment_type == PaymentType.debt,
                Sale.paid_amount < Sale.total_amount,
                Sale.debt_due_date < today,
                Sale.debt_due_date.isnot(None)
            ).all()

            if not overdue_sales:
                continue

            total_overdue = sum(
                float(s.total_amount or 0) - float(s.paid_amount or 0)
                for s in overdue_sales
            )

            managers = db.query(User).filter(
                User.company_id == company.id,
                User.role.in_([UserRole.admin, UserRole.director]),
                User.tg_chat_id.isnot(None)
            ).all()

            msg = (
                f"🔴 <b>Muddati o'tgan qarzlar — {today.strftime('%d.%m.%Y')}</b>\n\n"
                f"<b>{company.name}</b> do'konida:\n"
                f"• Qarzdorlar soni: <b>{len(overdue_sales)} ta</b>\n"
                f"• Umumiy qarz: <b>{total_overdue:,.0f} so'm</b>\n\n"
                f"Iltimos, mijozlar bilan bog'laning!"
            )

            for manager in managers:
                await send_tg_msg_async(company.tg_bot_token, manager.tg_chat_id, msg)

            # FCM push ham yuborish
            _send_fcm_to_managers(
                company=company,
                db=db,
                title=f"⚠️ {company.name}: Muddati o'tgan qarzlar",
                body=f"{len(overdue_sales)} ta mijozda jami {total_overdue:,.0f} so'm muddati o'tgan qarz bor.",
                data={"type": "overdue_debt", "company_id": str(company.id)},
            )

        print("[Scheduler] Muddati o'tgan qarzlar haqida rahbarlarga xabar yuborildi")

    except Exception as e:
        print(f"[Scheduler] notify_managers_overdue xatolik: {e}")
    finally:
        db.close()


# ─── 3. Kunlik hisobot — har bir do'konning o'z vaqtida ─────────────────

async def send_daily_report_for_company(company: Company, db):
    """
    Bitta kompaniya uchun kunlik hisobot yuboradi:
    - Telegram orqali rahbar/adminlarga
    - FCM Push orqali mobil ilovaga
    """
    from app.services.ai_service import build_daily_report

    try:
        report_text = build_daily_report(db, company.id, company.name)
    except Exception as e:
        print(f"[Scheduler] {company.name} uchun hisobot yaratishda xatolik: {e}")
        report_text = (
            f"📊 <b>{company.name} — Kunlik Hisobot</b>\n\n"
            f"Hisobotni yaratishda xatolik yuz berdi. "
            f"Iltimos, ilovadan tekshiring."
        )

    # Telegram orqali
    if company.tg_bot_token:
        managers_tg = db.query(User).filter(
            User.company_id == company.id,
            User.role.in_([UserRole.admin, UserRole.director]),
            User.tg_chat_id.isnot(None),
        ).all()
        for manager in managers_tg:
            ok = await send_tg_msg_async(
                company.tg_bot_token,
                manager.tg_chat_id,
                report_text,
            )
            if ok:
                print(f"[Scheduler][TG] Hisobot: {company.name} → {manager.name}")

    # FCM Push Notification orqali (qisqa xulosa)
    _send_fcm_to_managers(
        company=company,
        db=db,
        title=f"📊 {company.name} — Kunlik Hisobot",
        body="Bugungi savdo hisoboti tayyor. Ko'rish uchun bosing.",
        data={"type": "daily_report", "company_id": str(company.id)},
    )


async def check_and_send_reports():
    """
    Barcha faol kompaniyalarning hisobot vaqtini tekshiradi.
    Vaqti kelgan kompaniya uchun hisobot yuboradi.
    """
    db = SessionLocal()
    try:
        utc_now = datetime.now(timezone.utc)
        uz_now = utc_now + timedelta(hours=5)
        current_hhmm = uz_now.strftime("%H:%M")  # M-n: "17:30"

        companies = db.query(Company).filter(Company.is_active == True).all()

        for company in companies:
            # daily_report_time ustuni mavjud bo'lmasa yoki None bo'lsa
            report_time = getattr(company, "daily_report_time", None) or "17:30"
            if report_time == current_hhmm:
                print(
                    f"[Scheduler] {company.name} uchun kunlik hisobot vaqti keldi "
                    f"({current_hhmm}). Yuborilmoqda..."
                )
                await send_daily_report_for_company(company, db)

    except Exception as e:
        print(f"[Scheduler] check_and_send_reports xatolik: {e}")
    finally:
        db.close()


# ─── Vaqt tekshiruvchi yordamchi ─────────────────────────────────────────

def _is_time(hour: int, minute: int, now: datetime) -> bool:
    """Berilgan soat:daqiqada bir marta ishga tushiradi."""
    return now.hour == hour and now.minute == minute


# ─── Asosiy Scheduler loop ───────────────────────────────────────────────

async def start_scheduler():
    """
    Fon vazifalar boshqaruvchisi.
    Har daqiqada vaqtni tekshirib, belgilangan vazifalarni bajaradi.

    Jadval (O'zbekiston vaqti — UTC+5):
    ┌──────────────────────────────────────────────────────────────────┐
    │  09:00     — Mijozlarga qarz eslatmalari (Telegram)             │
    │  10:00     — Rahbarga muddati o'tgan qarzlar ogohlantirish      │
    │  Har daqiqa— Har bir do'konning o'z vaqtida kunlik hisobot      │
    │              (Telegram + FCM Push Notification)                  │
    └──────────────────────────────────────────────────────────────────┘
    """
    last_debt_date = None
    last_overdue_date = None
    # Hisobot uchun: {company_id: last_report_date}
    last_report_dates: dict = {}

    print("[Scheduler] Ishga tushdi ✅")

    while True:
        try:
            utc_now = datetime.now(timezone.utc)
            uz_now = utc_now + timedelta(hours=5)
            today = uz_now.date()
            current_hhmm = uz_now.strftime("%H:%M")

            # 09:00 — Qarz eslatmalari (mijozlarga)
            if _is_time(9, 0, uz_now) and last_debt_date != today:
                print(f"[Scheduler] {uz_now.strftime('%H:%M')} — Qarz eslatmalari ishga tushdi")
                await process_daily_debts()
                last_debt_date = today

            # 10:00 — Muddati o'tgan qarzlar (rahbarga)
            if _is_time(10, 0, uz_now) and last_overdue_date != today:
                print(f"[Scheduler] {uz_now.strftime('%H:%M')} — Muddati o'tgan qarzlar tekshirilmoqda")
                await notify_managers_overdue()
                last_overdue_date = today

            # Har daqiqa — Har bir do'konning o'z vaqtida kunlik hisobot
            # (Telegram + FCM Push)
            db = SessionLocal()
            try:
                companies = db.query(Company).filter(Company.is_active == True).all()
                for company in companies:
                    report_time = getattr(company, "daily_report_time", None) or "17:30"
                    if (
                        report_time == current_hhmm
                        and last_report_dates.get(company.id) != today
                    ):
                        print(
                            f"[Scheduler] {company.name} — hisobot vaqti keldi "
                            f"({current_hhmm}). Yuborilmoqda..."
                        )
                        await send_daily_report_for_company(company, db)
                        last_report_dates[company.id] = today
            finally:
                db.close()

        except Exception as e:
            print(f"[Scheduler] Loop xatolik: {e}")

        # Har 60 soniyada tekshiradi
        await asyncio.sleep(60)
