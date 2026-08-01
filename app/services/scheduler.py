"""
Avtomatik Scheduler — Fon vazifalar boshqaruvchisi
====================================================
1. Har kuni soat 09:00 da — muddati kelgan qarz eslatmalari (mijozlarga)
2. Har kuni soat 17:30 da — do'kon rahbariga kunlik hisobot (Telegram)
3. Har kuni soat 10:00 da — muddati o'tgan qarzlar uchun rahbarga ogohlantirish
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

            # Muddati o'tgan savdolar
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

            # Rahbarlarga xabar yuborish
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

        print(f"[Scheduler] Muddati o'tgan qarzlar haqida rahbarlarga xabar yuborildi")

    except Exception as e:
        print(f"[Scheduler] notify_managers_overdue xatolik: {e}")
    finally:
        db.close()


# ─── 3. Kunlik hisobot — Rahbarga (har kuni soat 17:30) ─────────────────

async def send_daily_report_to_managers():
    """
    Har kuni soat 17:30 da barcha kompaniyalar rahbarlariga
    kunlik savdo hisobotini Telegram orqali yuboradi.
    """
    from app.services.ai_service import build_daily_report

    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        total_sent = 0

        for company in companies:
            if not company.tg_bot_token:
                continue  # Bot ulangan bo'lmasa o'tkazib yuboramiz

            # Rahbar va adminlarni topamiz (tg_chat_id si borlarini)
            managers = db.query(User).filter(
                User.company_id == company.id,
                User.role.in_([UserRole.admin, UserRole.director]),
                User.tg_chat_id.isnot(None)
            ).all()

            if not managers:
                continue

            # Kunlik hisobot matnini tayyorlaymiz
            try:
                report_text = build_daily_report(db, company.id, company.name)
            except Exception as e:
                print(f"[Scheduler] {company.name} uchun hisobot yaratishda xatolik: {e}")
                report_text = (
                    f"📊 <b>{company.name} — Kunlik Hisobot</b>\n\n"
                    f"Hisobotni yaratishda xatolik yuz berdi. "
                    f"Iltimos, ilovadan tekshiring."
                )

            # Har bir rahbarga yuboramiz
            for manager in managers:
                ok = await send_tg_msg_async(
                    company.tg_bot_token,
                    manager.tg_chat_id,
                    report_text
                )
                if ok:
                    total_sent += 1
                    print(f"[Scheduler] Hisobot yuborildi: {company.name} → {manager.name}")

        print(f"[Scheduler] Kunlik hisobot: {total_sent} ta rahbarga yuborildi")

    except Exception as e:
        print(f"[Scheduler] send_daily_report_to_managers xatolik: {e}")
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
    ┌─────────────────────────────────────────────────────────┐
    │  09:00  — Mijozlarga qarz eslatmalari (Telegram)        │
    │  10:00  — Rahbarga muddati o'tgan qarzlar ogohlantirish │
    │  17:30  — Rahbarga kunlik savdo hisoboti (Telegram)     │
    └─────────────────────────────────────────────────────────┘
    """
    last_debt_date = None
    last_overdue_date = None
    last_report_date = None

    print("[Scheduler] Ishga tushdi ✅")

    while True:
        try:
            # O'zbekiston vaqtida ishlash uchun UTC+5
            utc_now = datetime.now(timezone.utc)
            uz_now = utc_now + timedelta(hours=5)
            today = uz_now.date()

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

            # 17:30 — Kunlik hisobot (rahbarga)
            if _is_time(17, 30, uz_now) and last_report_date != today:
                print(f"[Scheduler] {uz_now.strftime('%H:%M')} — Kunlik hisobot yuborilmoqda")
                await send_daily_report_to_managers()
                last_report_date = today

        except Exception as e:
            print(f"[Scheduler] Loop xatolik: {e}")

        # Har 60 soniyada tekshiradi
        await asyncio.sleep(60)
