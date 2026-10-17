"""
Avtomatik Scheduler — Fon vazifalar boshqaruvchisi
====================================================
1. Har kuni soat 09:00 da — muddati kelgan qarz eslatmalari (mijozlarga Telegram)
2. Har kuni soat 10:00 da — muddati o'tgan qarzlar haqida rahbarga ogohlantirish (Telegram)
3. Har bir do'konning sozlamasida belgilangan vaqtda (kechikish oynasi ichida) — kunlik hisobot:
   • Telegram → rahbar/admin lar
Kunlik bajarilish holati DB'da (scheduler_runs) saqlanadi — restart/ko'p worker uchun xavfsiz.
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timezone, timedelta
import httpx

from app.database import SessionLocal
from app.models.sale import Sale, SaleStatus, PaymentType
from app.models.customer import Customer
from app.models.company import Company
from app.models.user import User, UserRole
from app.admin_tg_bot.recipients import resolve_recipients
from app.utils.report_utils import sale_doc_filter, sale_rate, local_today, LOCAL_TZ
from app.utils.telegram_text import esc, strip_tags, split_html_message

logger = logging.getLogger(__name__)


# ─── Telegram yuboruvchi ─────────────────────────────────────────────────

_TG_PARSE_ERR = "can't parse entities"
_TG_RETRY_MAX_WAIT = 60  # 429 da kutishning yuqori chegarasi (soniya)


def _short(s: str, n: int = 500) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


async def send_tg_msg_async(token: str, chat_id: str, text: str,
                             parse_mode: str = "HTML", errors: list = None) -> bool:
    """Telegram orqali xabar yuboradi. True = muvaffaqiyatli.

    Xato bo'lsa javob matni (resp.text) log'ga yoziladi va `errors` ro'yxatiga qo'shiladi.
    - 400 "can't parse entities" → teglarsiz (strip_tags) bir marta qayta yuboriladi;
    - 429 → `retry_after` kutib bir marta qayta yuboriladi.
    """
    def _fail(msg: str) -> bool:
        logger.error("[TG] Xabar yuborilmadi (chat %s): %s", chat_id, msg)
        if errors is not None:
            errors.append(msg)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    plain_tried = False
    retried_429 = False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                body = resp.text or ""
                if (resp.status_code == 400 and _TG_PARSE_ERR in body.lower()
                        and not plain_tried and parse_mode):
                    plain_tried = True
                    payload = {"chat_id": chat_id, "text": strip_tags(text)}
                    continue
                if resp.status_code == 429 and not retried_429:
                    retried_429 = True
                    wait = 1
                    try:
                        wait = int((resp.json().get("parameters") or {}).get("retry_after") or 1)
                    except Exception:
                        pass
                    await asyncio.sleep(min(max(wait, 1), _TG_RETRY_MAX_WAIT))
                    continue
                return _fail(f"HTTP {resp.status_code}: {_short(body)}")
    except Exception as e:
        return _fail(f"{type(e).__name__}: {_short(str(e))}")


async def send_tg_chunks(token: str, chat_id: str, text: str,
                         parse_mode: str = "HTML", errors: list = None) -> bool:
    """Uzun xabarni 4096 belgidan oshmaydigan bo'laklarga bo'lib yuboradi.
    True = barcha bo'laklar yetkazildi. Xatolar `errors` ro'yxatiga yoziladi."""
    chunks = split_html_message(text)
    if not chunks:
        return True
    all_ok = True
    for chunk in chunks:
        ok = await send_tg_msg_async(token, chat_id, chunk, parse_mode, errors=errors)
        all_ok = all_ok and bool(ok)
    return all_ok


def _open_debt_sales_filter():
    """Qarzi ochiq qolgan sotuvlar: qisman qaytarilganlari ham (to'liq qaytarilgan va
    qaytarish hujjatlari emas). paid_amount sotuv valyutasida, total_amount UZS da."""
    return (
        sale_doc_filter(),
        Sale.status != SaleStatus.refunded,
        Sale.payment_type == PaymentType.debt,
        Sale.paid_amount * sale_rate() < Sale.total_amount - 0.01,
    )


def _outstanding_uzs(sale: Sale) -> float:
    rate = float(sale.exchange_rate or 0) or 1.0
    return float(sale.total_amount or 0) - float(sale.paid_amount or 0) * rate


# ─── 1. Qarz eslatmalari (Mijozlarga — har kuni soat 09:00) ─────────────

async def process_daily_debts():
    """Muddati yaqin yoki o'tgan qarzdorlarga Telegram xabar yuboradi."""
    db = SessionLocal()
    try:
        today = local_today()
        unpaid_sales = db.query(Sale).filter(
            *_open_debt_sales_filter(),
            Sale.debt_due_date.isnot(None)
        ).all()

        sent_count = 0
        for sale in unpaid_sales:
            debt_amount = _outstanding_uzs(sale)
            if debt_amount <= 0:
                continue

            customer = db.query(Customer).filter(
                Customer.id == sale.customer_id, Customer.is_active.is_(True),  # T0.26
            ).first()
            if not customer or not customer.tg_chat_id:
                continue

            # Mijoz "Qarz to'lash" orqali qarzini yopganda faqat Customer.debt_balance
            # yangilanadi — bu Sale.paid_amount ni o'zgartirmaydi. Shu sabab eski Sale
            # hamon "to'lanmagan" ko'rinib, qarz allaqachon yopilgan bo'lsa ham eslatma
            # ketaveradi. Mijozning haqiqiy (joriy) umumiy qarzini tekshirib chiqib
            # yuboramiz.
            if float(customer.debt_balance or 0) <= 0:
                continue

            company = db.query(Company).filter(Company.id == sale.company_id).first()
            if not company or not company.tg_bot_token:
                continue

            # Agar qarz muddati bildirishnomasi o'chirilgan bo'lsa, xabar yubormaslik
            if company.debt_deadline_alert is False:
                continue

            due = sale.debt_due_date
            diff_days = (due - today).days

            msg = None
            if diff_days == 3:
                msg = (
                    f"❗️ <b>Eslatma</b>\n\n"
                    f"Hurmatli <b>{esc(customer.name)}</b>,\n"
                    f"<b>{esc(company.name)}</b> do'konidan olgan <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingizni to'lash muddatigacha <b>3 kun</b> qoldi.\n"
                    f"To'lov sanasi: <b>{due.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Iltimos, vaqtida to'lashni unutmang!"
                )
            elif diff_days == 1:
                msg = (
                    f"⚡️ <b>Ertaga to'lov kuni!</b>\n\n"
                    f"Hurmatli <b>{esc(customer.name)}</b>,\n"
                    f"<b>{esc(company.name)}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingiz ertaga (<b>{due.strftime('%d.%m.%Y')}</b>) to'lanishi kerak."
                )
            elif diff_days == 0:
                msg = (
                    f"🚨 <b>Diqqat — Bugun To'lov Kuni!</b>\n\n"
                    f"Hurmatli <b>{esc(customer.name)}</b>,\n"
                    f"<b>{esc(company.name)}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingizni to'lash muddati <b>bugun</b>!\n"
                    f"Iltimos, kun davomida to'lovni amalga oshiring."
                )
            elif diff_days < 0:
                overdue = abs(diff_days)
                msg = (
                    f"⚠️ <b>Kechiktirilgan To'lov — {overdue} kun!</b>\n\n"
                    f"Hurmatli <b>{esc(customer.name)}</b>,\n"
                    f"<b>{esc(company.name)}</b> do'koniga <b>{debt_amount:,.0f} so'm</b> "
                    f"qarzingiz to'lov muddatidan <b>{overdue} kun</b> o'tib ketdi.\n"
                    f"Zudlik bilan bog'laning yoki to'lovni amalga oshiring!"
                )

            if msg:
                # T3.7: shu sotuv filialining nomi va telefoni (mijoz qaysi filialga borishini bilsin).
                # Filial topilmasa (eski sotuv, omborsiz) faqat shu qator qo'shilmaydi.
                br = sale.branch or (sale.warehouse.branch if sale.warehouse else None)
                if br is not None:
                    msg += f"\n\n🏬 Filial: <b>{esc(br.name)}</b>"
                    if br.phone:
                        msg += f"\n📞 Tel: {esc(br.phone)}"
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
    """Muddati o'tgan qarzdorlar haqida rahbarlarga xabar yuboradi (ADMIN bot orqali, T3.16)."""
    from app.admin_tg_bot.models import CompanyBot

    db = SessionLocal()
    try:
        today = local_today()
        companies = db.query(Company).filter(Company.is_active == True).all()

        for company in companies:
            # Agar qarz muddati bildirishnomasi o'chirilgan bo'lsa, rahbarlarga ham xabar yubormaslik
            if company.debt_deadline_alert is False:
                continue

            # Rahbarlar admin botga ulangan — xabar shu bot tokeni bilan (mijoz boti tokeni emas).
            # Admin bot yo'q korxonada Telegram o'tkazib yuboriladi.
            admin_bot = db.query(CompanyBot).filter(
                CompanyBot.company_id == company.id,
                CompanyBot.bot_type == "admin",
                CompanyBot.is_active == True
            ).first()
            if not admin_bot or not admin_bot.bot_token:
                continue

            overdue_sales = db.query(Sale).filter(
                Sale.company_id == company.id,
                *_open_debt_sales_filter(),
                Sale.debt_due_date < today,
                Sale.debt_due_date.isnot(None)
            ).all()

            # "Qarz to'lash" orqali yopilgan qarzlar Sale.paid_amount'ni
            # yangilamaydi — Customer.debt_balance orqali haqiqiy qarzi
            # qolganlarini ajratamiz (process_daily_debts bilan bir xil mantiq).
            customer_ids = {s.customer_id for s in overdue_sales}
            debt_positive_ids = set()
            if customer_ids:
                for c in db.query(Customer.id, Customer.debt_balance).filter(Customer.id.in_(customer_ids)).all():
                    if float(c.debt_balance or 0) > 0:
                        debt_positive_ids.add(c.id)
            overdue_sales = [s for s in overdue_sales if s.customer_id in debt_positive_ids]

            if not overdue_sales:
                continue

            total_overdue = sum(_outstanding_uzs(s) for s in overdue_sales)
            debtor_count = len({s.customer_id for s in overdue_sales})

            managers = resolve_recipients(db, company.id, kind="debt")

            msg = (
                f"🔴 <b>Muddati o'tgan qarzlar — {today.strftime('%d.%m.%Y')}</b>\n\n"
                f"<b>{esc(company.name)}</b> do'konida:\n"
                f"• Qarzdorlar soni: <b>{debtor_count} ta</b>\n"
                f"• Umumiy qarz: <b>{total_overdue:,.0f} so'm</b>\n\n"
                f"Iltimos, mijozlar bilan bog'laning!"
            )

            for manager in managers:
                # xato bo'lsa send_tg_msg_async javob matnini log'ga yozadi
                await send_tg_msg_async(admin_bot.bot_token, manager.tg_chat_id, msg)

        print("[Scheduler] Muddati o'tgan qarzlar haqida rahbarlarga xabar yuborildi")

    except Exception as e:
        print(f"[Scheduler] notify_managers_overdue xatolik: {e}")
    finally:
        db.close()


def _build_expiring_message(batches, days_before: int, today) -> str:
    """Muddati tugayotgan partiyalar xabari: ombor/filial → mahsulot bo'yicha guruhlangan.
    Dinamik nomlar HTML-escape qilinadi; har bir teg bir qator ichida (bo'laklash uchun)."""
    groups: dict = {}
    for b in batches:
        wh = b.warehouse
        key = wh.id if wh else 0
        g = groups.setdefault(key, {"wh": wh, "products": {}})
        g["products"].setdefault(b.product_id, {"name": b.product.name if b.product else "?", "rows": []})["rows"].append(b)

    def _sort_key(g):
        wh = g["wh"]
        br = getattr(wh, "branch", None) if wh else None
        return ((br.name if br else "") or "", (wh.name if wh else "") or "")

    msg = (
        f"⚠️ <b>Yaroqlilik muddati tugayotgan mahsulotlar!</b>\n\n"
        f"Quyidagi tovarlarning muddati {days_before} kun ichida tugaydi:\n"
    )
    for g in sorted(groups.values(), key=_sort_key):
        wh = g["wh"]
        br = getattr(wh, "branch", None) if wh else None
        if wh:
            head = f"🏬 <b>Ombor: {esc(wh.name)}</b>"
            if br:
                head += f" (Filial: {esc(br.name)})"
        else:
            head = "🏬 <b>Ombor: —</b>"
        msg += f"\n{head}\n"
        for prod in g["products"].values():
            msg += f"📦 <b>{esc(prod['name'])}</b>\n"
            for b in prod["rows"]:
                # expiry_date datetime yoki date bo'lishi mumkin
                b_date = b.expiry_date.date() if isinstance(b.expiry_date, datetime) else b.expiry_date
                days_left = (b_date - today).days
                msg += f"   Miqdor: {b.quantity} · Muddat: {b_date.strftime('%Y-%m-%d')} ({days_left} kun qoldi)\n"
    return msg


# ─── 2.2 Muddati tugayotgan mahsulotlar ogohlantirishi (11:00) ────────────
async def notify_expiring_products():
    """Muddati tugashiga belgilangan kundan kam qolgan tovarlar haqida rahbarlarga xabar yuboradi."""
    db = SessionLocal()
    try:
        from app.admin_tg_bot.models import CompanyBot
        from app.models.batch import Batch
        from app.models.warehouse import Warehouse
        from sqlalchemy.orm import joinedload
        from app.services.expiry import expired_batches_query
        
        utc_now = datetime.now(timezone.utc)
        uz_now = utc_now + timedelta(hours=5)
        today = uz_now.date()
        
        companies = db.query(Company).filter(Company.is_active == True).all()
        for company in companies:
            admin_bot = db.query(CompanyBot).filter(
                CompanyBot.company_id == company.id,
                CompanyBot.bot_type == "admin",
                CompanyBot.is_active == True
            ).first()
            
            if not admin_bot or not admin_bot.bot_token or not admin_bot.notify_expired_products:
                continue
                
            days_before = admin_bot.expired_days_before or 7
            target_date = today + timedelta(days=days_before)
            
            # T1.8: ro'yxat va cron bilan bir xil qoida (perishable kategoriya, qoldiq > 0)
            expiring_batches = expired_batches_query(
                db, company.id, today, expiry_from=today, expiry_until=target_date,
            ).options(
                joinedload(Batch.product), joinedload(Batch.warehouse).joinedload(Warehouse.branch),
            ).order_by(Batch.expiry_date.asc()).all()

            if not expiring_batches:
                continue

            msg = _build_expiring_message(expiring_batches, days_before, today)

            managers = resolve_recipients(db, company.id, kind="expiry")

            for manager in managers:
                errs: list = []
                ok = await send_tg_chunks(admin_bot.bot_token, manager.tg_chat_id, msg, errors=errs)
                if not ok:
                    logger.error("[Scheduler] %s: muddati tugayotgan tovarlar xabari yuborilmadi: %s",
                                 company.name, "; ".join(errs[-3:]))

            # Filial menejerlari (daily_report_recipients=all_managers va notify_branch_managers yoqilgan bo'lsa):
            # faqat o'z filiali omborlaridagi partiyalar
            by_branch: dict = {}
            for b in expiring_batches:
                if b.warehouse is not None and b.warehouse.branch_id:
                    by_branch.setdefault(b.warehouse.branch_id, []).append(b)
            for br_id, br_batches in by_branch.items():
                br_managers = resolve_recipients(db, company.id, branch_id=br_id, kind="expiry", managers_only=True)
                if not br_managers:
                    continue
                br_msg = _build_expiring_message(br_batches, days_before, today)
                for manager in br_managers:
                    errs = []
                    if not await send_tg_chunks(admin_bot.bot_token, manager.tg_chat_id, br_msg, errors=errs):
                        logger.error("[Scheduler] %s: filial menejeriga muddat xabari yuborilmadi: %s",
                                     company.name, "; ".join(errs[-3:]))

            print(f"[Scheduler] {company.name} rahbarlariga muddati tugayotgan mahsulotlar yuborildi")
            
    except Exception as e:
        print(f"[Scheduler] notify_expiring_products xatolik: {e}")
    finally:
        db.close()


# ─── 2.5 Muddati o'tganlarni avtomatik hisobdan chiqarish (00:05) ────────
async def auto_write_off_expired():
    """Muddati o'tgan partiyalarni (Batch) avtomatik EXPIRED holatiga o'tkazib, qoldiqdan ayiradi.
    T1.8: qoida ro'yxat/qo'lda hisobdan chiqarish bilan bir xil (`expired_batches_query`: faqat
    perishable kategoriya, korxona bo'yicha); har partiya alohida tranzaksiyada, qulf + qayta tekshiruv."""
    db = SessionLocal()
    try:
        from app.models.batch import Batch
        from app.models.inventory import StockLevel, StockMovement, MovementType
        from app.services.expiry import expired_batches_query

        utc_now = datetime.now(timezone.utc)
        uz_now = utc_now + timedelta(hours=5)
        today = uz_now.date()

        company_ids = [r[0] for r in db.query(Company.id).filter(Company.is_active == True).all()]
        batch_ids = []
        for cid in company_ids:
            batch_ids.extend(
                r[0] for r in expired_batches_query(db, cid, today, only_expired=True).with_entities(Batch.id).all()
            )
        db.rollback()  # o'qish tranzaksiyasini yopamiz — keyingi bosqich har partiya uchun alohida

        count = 0
        for batch_id in batch_ids:
            try:
                # Parallel worker bilan to'qnashmaslik: qulfda bo'lsa o'tkazib yuboramiz, qulfdan keyin qayta tekshiramiz
                batch = db.query(Batch).filter(Batch.id == batch_id).with_for_update(skip_locked=True).first()
                if batch is None or (batch.quantity or 0) <= 0:
                    db.rollback()
                    continue

                stock_level = db.query(StockLevel).filter(
                    StockLevel.product_id == batch.product_id,
                    StockLevel.warehouse_id == batch.warehouse_id,
                    StockLevel.variant_id == batch.variant_id
                ).with_for_update().first()

                if not stock_level:
                    logger.warning(
                        "[Scheduler] Partiya #%s (mahsulot %s, ombor %s): qoldiq qatori topilmadi, o'tkazib yuborildi",
                        batch.id, batch.product_id, batch.warehouse_id,
                    )
                    db.rollback()
                    continue

                # Faqat o'z omboridagi mavjud qoldiq bilan cheklab yechamiz — qoldiq manfiyga tushmaydi
                # (partiya ko'chirilgan/sotilgan bo'lsa "fantom" qismi faqat nolga tushiriladi)
                available = max(stock_level.quantity or 0, 0)
                qty_to_write_off = min(batch.quantity, available)
                phantom = batch.quantity - qty_to_write_off

                if qty_to_write_off > 0:
                    qty_before = stock_level.quantity
                    stock_level.quantity -= qty_to_write_off
                    qty_after = stock_level.quantity

                    db.add(StockMovement(
                        product_id=batch.product_id,
                        variant_id=batch.variant_id,
                        warehouse_id=batch.warehouse_id,
                        type=MovementType.EXPIRED,
                        qty_before=qty_before,
                        qty_after=qty_after,
                        quantity=qty_to_write_off,
                        reference_type="auto_batch_write_off",
                        reference_id=batch.id,
                        reason=f"Avtomatik muddat o'tishi (Cron)"
                    ))

                if phantom > 0:
                    logger.warning(
                        "[Scheduler] Partiya #%s (mahsulot %s, ombor %s): qoldiq yetmadi, %s fantom qism nolga tushirildi",
                        batch.id, batch.product_id, batch.warehouse_id, phantom,
                    )

                batch.quantity = 0
                db.commit()
                count += 1
            except Exception as e:
                logger.error("[Scheduler] Partiya #%s hisobdan chiqarishda xatolik: %s", batch_id, e)
                db.rollback()

        if count > 0:
            print(f"[Scheduler] {count} ta muddati o'tgan partiya avtomatik hisobdan chiqarildi.")

    except Exception as e:
        print(f"[Scheduler] auto_write_off_expired xatolik: {e}")
        db.rollback()
    finally:
        db.close()


# ─── Vaqt tekshiruvchi yordamchilar ──────────────────────────────────────

def _cleanup_old_locations(days: int = 90) -> None:
    db = SessionLocal()
    try:
        from app.models.employee_location import EmployeeLocation
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        n = db.query(EmployeeLocation).filter(EmployeeLocation.recorded_at < cutoff).delete(synchronize_session=False)
        db.commit()
        if n:
            print(f"[Scheduler] {n} ta eski GPS nuqta o'chirildi")
    except Exception as e:
        db.rollback()
        print(f"[Scheduler] GPS tozalashda xato: {e}")
    finally:
        db.close()


def _due(now_local: datetime, hour: int, minute: int, window_minutes: int) -> bool:
    """Vazifa vaqti keldimi: `belgilangan <= hozir < belgilangan + oyna` (shu kun ichida).

    Aniq daqiqaga tenglik emas — sikl bir daqiqani o'tkazib yuborsa ham, oyna ichida
    keyingi iteratsiyada vazifa bajariladi. Kuniga bir martalikni `claim_run` kafolatlaydi."""
    scheduled = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return scheduled <= now_local < scheduled + timedelta(minutes=window_minutes)


def _parse_hhmm(value, default: tuple) -> tuple:
    """'HH:MM' (shuningdek '9:5') → (soat, daqiqa); noto'g'ri qiymatda `default`."""
    m = re.match(r"^\s*(\d{1,2}):(\d{1,2})\s*$", value or "")
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
    return default


# ─── Kunlik bajarilish registri (scheduler_runs) ─────────────────────────

RUN_MAX_ATTEMPTS = 3       # xatoda urinishlar soni (jami)
RUN_STALE_MINUTES = 10     # 'running' shundan eski bo'lsa (worker o'lgan) qayta olinadi
RUN_RETRY_DELAY_MIN = 5    # 'failed' dan keyin qayta urinishgacha kutish
REPORT_WINDOW_MIN = 180    # kunlik hisobot kechikish oynasi (3 soat)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def claim_run(db, job: str, scope: str, run_date, max_attempts: int = RUN_MAX_ATTEMPTS,
              now: datetime = None) -> bool:
    """Vazifani (job, scope, run_date) uchun egallaydi. True = shu chaqiruvchi bajarishi kerak.

    `INSERT .. ON CONFLICT DO NOTHING` — parallel worker/server dan faqat bittasi yutadi.
    Qator mavjud bo'lsa: 'failed' (urinish < max, kutish o'tgan) yoki eski 'running'
    (urinish < max) qayta olinadi. Registr xatosi vazifani bajarmaydi (False) va siklni to'xtatmaydi."""
    from sqlalchemy import and_, or_, update
    from app.models.scheduler_run import SchedulerRun as SR
    now = now or _utcnow_naive()
    try:
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        stmt = (
            dialect_insert(SR)
            .values(job=job, scope=scope, run_date=run_date, status="running", attempts=1, claimed_at=now)
            .on_conflict_do_nothing(index_elements=["job", "scope", "run_date"])
            .returning(SR.id)
        )
        if db.execute(stmt).first() is not None:
            db.commit()
            return True

        stale = now - timedelta(minutes=RUN_STALE_MINUTES)
        retry_at = now - timedelta(minutes=RUN_RETRY_DELAY_MIN)
        res = db.execute(
            update(SR)
            .where(
                SR.job == job, SR.scope == scope, SR.run_date == run_date,
                SR.attempts < max_attempts,
                or_(
                    and_(SR.status == "failed", SR.finished_at <= retry_at),
                    and_(SR.status == "running", SR.claimed_at <= stale),
                ),
            )
            .values(status="running", attempts=SR.attempts + 1, claimed_at=now, finished_at=None)
        )
        db.commit()
        return res.rowcount == 1
    except Exception as e:
        logger.error("[Scheduler] Registrga yozishda xato (%s/%s): %s", job, scope, e)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def finish_run(db, job: str, scope: str, run_date, ok: bool, detail: str = None,
               now: datetime = None) -> None:
    """Egallangan vazifani 'done' yoki 'failed' qilib yopadi (detail — xato matni)."""
    from sqlalchemy import update
    from app.models.scheduler_run import SchedulerRun as SR
    try:
        db.execute(
            update(SR)
            .where(SR.job == job, SR.scope == scope, SR.run_date == run_date)
            .values(status="done" if ok else "failed", finished_at=now or _utcnow_naive(),
                    detail=_short(detail, 2000) if detail else None)
        )
        db.commit()
    except Exception as e:
        logger.error("[Scheduler] Registrni yopishda xato (%s/%s): %s", job, scope, e)
        try:
            db.rollback()
        except Exception:
            pass


def purge_old_runs(days: int = 30) -> None:
    """30 kundan eski registr qatorlarini o'chiradi."""
    from app.models.scheduler_run import SchedulerRun as SR
    db = SessionLocal()
    try:
        db.query(SR).filter(SR.run_date < local_today() - timedelta(days=days)).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("[Scheduler] Eski registr qatorlarini tozalashda xato: %s", e)
    finally:
        db.close()


async def _run_job(job: str, scope: str, run_date, fn, max_attempts: int = RUN_MAX_ATTEMPTS) -> bool:
    """Vazifani egallab (claim_run) bajaradi va natijani registrga yozadi.

    `fn` — argumentsiz async funksiya (yoki oddiy funksiya, alohida thread'da); `(ok, detail)`
    qaytarishi yoki None (= muvaffaqiyatli). Istisno 'failed' + detail bilan qayd etiladi.
    True = vazifa bajarildi va muvaffaqiyatli."""
    reg = SessionLocal()
    try:
        if not claim_run(reg, job, scope, run_date, max_attempts=max_attempts):
            return False
        try:
            if asyncio.iscoroutinefunction(fn):
                res = await fn()
            else:
                res = await asyncio.to_thread(fn)
        except Exception as e:
            logger.exception("[Scheduler] %s (%s) bajarilmadi", job, scope)
            finish_run(reg, job, scope, run_date, False, f"{type(e).__name__}: {e}")
            return False
        ok, detail = res if isinstance(res, tuple) else (True, None)
        finish_run(reg, job, scope, run_date, bool(ok), detail)
        return bool(ok)
    finally:
        reg.close()


# ─── 3. Kunlik hisobot — har bir do'konning o'z vaqtida ─────────────────

def _daily_report_text(db, company: Company, *, scope=None, include_branches: bool = True) -> tuple:
    """(matn, xato). Qo'shimcha argumentlar faqat standartdan farq qilganda uzatiladi."""
    from app.services.ai_service import build_daily_report
    try:
        if scope is None and include_branches:
            return build_daily_report(db, company.id, company.name), None
        kw = {}
        if scope is not None:
            kw["scope"] = scope
        if not include_branches:
            kw["include_branches"] = False
        return build_daily_report(db, company.id, company.name, **kw), None
    except Exception as e:
        logger.exception("[Scheduler] %s uchun hisobot yaratishda xatolik", company.name)
        return (f"📊 <b>{esc(company.name)} - Kunlik Hisobot</b>\n\nXatolik yuz berdi.",
                f"hisobot yaratilmadi: {type(e).__name__}: {e}")


async def _send_company_tg_report(db, company: Company, admin_bot) -> tuple:
    """Bitta korxona Telegram hisoboti. (ok, detail): hech bo'lmasa bitta qabul qiluvchiga
    yetsa ok; hammasiga yetmasa — xato matni bilan False (qayta uriniladi).

    Avval korxona umumiy hisoboti admin/direktorlarga (filiallar bo'limi bilan, `report_by_branch` yoqilgan bo'lsa),
    so'ng har bir filial menejeriga FAQAT o'z filiali hisoboti (qarz bo'limisiz)."""
    from app.models.branch import Branch
    from app.services.ai_scope import _make_scope

    report_text, build_err = _daily_report_text(db, company, include_branches=admin_bot.report_by_branch is not False)

    managers = resolve_recipients(db, company.id, kind="daily_report")

    # Filial menejerlari: (filial_id, [menejerlar])
    branch_groups = []
    branch_ids = [r[0] for r in db.query(Branch.id).filter(
        Branch.company_id == company.id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).all()]
    for br_id in branch_ids:
        mgrs = resolve_recipients(db, company.id, branch_id=br_id, kind="daily_report", managers_only=True)
        if mgrs:
            branch_groups.append((br_id, mgrs))

    if not managers and not branch_groups:
        return True, "qabul qiluvchi yo'q"

    errs: list = []
    sent = 0
    total = len(managers)
    for manager in managers:
        if await send_tg_chunks(admin_bot.bot_token, manager.tg_chat_id, report_text, errors=errs):
            sent += 1
            print(f"[Scheduler][TG] Hisobot: {company.name} -> {manager.name}")

    for br_id, mgrs in branch_groups:
        scope = _make_scope(db, company.id, [br_id], True)
        br_text, br_err = _daily_report_text(db, company, scope=scope, include_branches=False)
        build_err = build_err or br_err
        for manager in mgrs:
            total += 1
            if await send_tg_chunks(admin_bot.bot_token, manager.tg_chat_id, br_text, errors=errs):
                sent += 1
                print(f"[Scheduler][TG] Filial hisoboti: {company.name} -> {manager.name}")

    parts = [f"{sent}/{total} yuborildi"]
    if build_err:
        parts.append(build_err)
    if errs:
        parts.append("; ".join(errs[-3:]))
    return sent > 0, " | ".join(parts)


async def _company_reports_tick(uz_now: datetime, today) -> None:
    """Har korxona uchun Telegram kunlik hisobotini (oyna ichida, kuniga bir marta) yuboradi."""
    from app.admin_tg_bot.models import CompanyBot

    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        for company in companies:
            try:
                scope = f"company:{company.id}"

                # Telegram (Admin Bot) orqali yuborish
                admin_bot = db.query(CompanyBot).filter(
                    CompanyBot.company_id == company.id,
                    CompanyBot.bot_type == "admin",
                    CompanyBot.is_active == True
                ).first()
                if admin_bot and admin_bot.notify_scheduled and admin_bot.bot_token:
                    th, tm = _parse_hhmm(admin_bot.scheduled_time, (20, 0))
                    if _due(uz_now, th, tm, REPORT_WINDOW_MIN):
                        async def _tg(c=company, b=admin_bot):
                            return await _send_company_tg_report(db, c, b)
                        await _run_job("daily_report_tg", scope, today, _tg)
            except Exception as e:
                logger.exception("[Scheduler] %s kunlik hisobot siklida xatolik: %s", company.name, e)
                try:
                    db.rollback()
                except Exception:
                    pass
    finally:
        db.close()


async def _auto_write_off_job():
    """00:05: muddati o'tganlarni yechish + eski registr qatorlarini tozalash."""
    await auto_write_off_expired()
    await asyncio.to_thread(purge_old_runs)


def _daily_jobs() -> list:
    """(job, soat, daqiqa, oyna_daqiqa, max_urinish, async_funksiya). Funksiyalar chaqiruv paytida olinadi.
    Ko'p qabul qiluvchiga xabar yuboradigan vazifalar qayta urinilmaydi — dublikat xabar bo'lmasligi uchun."""
    async def _gps():
        await asyncio.to_thread(_cleanup_old_locations)

    async def _debts():
        await process_daily_debts()

    async def _overdue():
        await notify_managers_overdue()

    async def _expiring():
        await notify_expiring_products()

    return [
        ("debt_reminder", 9, 0, 360, 1, _debts),
        ("overdue_debts", 10, 0, 360, 1, _overdue),
        ("expiring_products", 11, 0, 360, 1, _expiring),
        ("gps_cleanup", 3, 0, 1200, RUN_MAX_ATTEMPTS, _gps),
        ("auto_write_off", 0, 5, 1200, RUN_MAX_ATTEMPTS, _auto_write_off_job),
    ]


async def _scheduler_tick(uz_now: datetime = None) -> None:
    """Bitta iteratsiya: vaqti kelgan (oyna ichidagi) vazifalarni registr orqali bajaradi."""
    uz_now = uz_now or datetime.now(LOCAL_TZ)
    today = uz_now.date()

    for job, hh, mm, window, max_att, fn in _daily_jobs():
        if _due(uz_now, hh, mm, window):
            await _run_job(job, "global", today, fn, max_attempts=max_att)

    await _company_reports_tick(uz_now, today)


# ─── Mir-maza buyurtmalarini tortish (alohida sikl) ──────────────────────

async def _marketplace_pull_once() -> None:
    # T0.36: BIR marta global so'rov, element egasi korxona externalId orqali aniqlanadi;
    # modul hech bir faol korxonada yoqilmagan bo'lsa so'rov yuborilmaydi
    db_mp = SessionLocal()
    try:
        from app.services.marketplace_service import pull_mirmaza_orders
        has_mp = db_mp.query(Company.id).filter(
            Company.is_active == True,  # noqa: E712
            Company.marketplace_agents_enabled == True,  # noqa: E712
        ).first()
        if has_mp:
            # httpx sinxron — event loop'ni bloklamaslik uchun alohida thread
            await asyncio.to_thread(pull_mirmaza_orders, db_mp)
    except Exception as e:
        logger.error("[Scheduler] Mir-Maza order pull xatoligi: %s", e)
        try:
            db_mp.rollback()
        except Exception:
            pass
    finally:
        db_mp.close()


def _pull_slot_free() -> bool:
    """Rahbar almashayotgan (HUP) qisqa oynada ikki jarayon bir vaqtda tortmasligi uchun qisqa ijara.
    Ijara xatosi tortishni to'xtatmaydi (True)."""
    from app.services.background_jobs import _acquire, process_holder
    try:
        return _acquire("mirmaza_pull", process_holder(), ttl=240)
    except Exception as e:
        logger.error("[Scheduler] Mir-Maza pull ijarasi olinmadi: %s", e)
        return True


async def _marketplace_pull_loop() -> None:
    """Har 5 daqiqada (soat devoriga tekislangan) — asosiy sikldan mustaqil."""
    while True:
        await asyncio.sleep(max(1, 300 - (time.time() % 300)))
        try:
            if not await asyncio.to_thread(_pull_slot_free):
                continue
            await _marketplace_pull_once()
        except Exception as e:
            logger.error("[Scheduler] Mir-Maza pull sikli xatoligi: %s", e)


# ─── Asosiy Scheduler loop ───────────────────────────────────────────────

async def start_scheduler():
    """
    Fon vazifalar boshqaruvchisi.
    Har daqiqada vaqtni tekshirib, vaqti kelgan (kechikish oynasi ichidagi) vazifalarni bajaradi.
    "Bugun bajarildi" holati DB'da (scheduler_runs) — restart va ko'p worker uchun xavfsiz.

    Jadval (O'zbekiston vaqti — UTC+5), oyna ichida kuniga bir marta:
    ┌──────────────────────────────────────────────────────────────────┐
    │  00:05     — Muddati o'tgan tovarlarni hisobdan chiqarish (20 s)│
    │  03:00     — Eski GPS nuqtalarni tozalash (20 soat)             │
    │  09:00     — Mijozlarga qarz eslatmalari (Telegram, 6 soat)     │
    │  10:00     — Rahbarga muddati o'tgan qarzlar (6 soat)           │
    │  11:00     — Muddati tugayotgan mahsulotlar (6 soat)            │
    │  Korxona   — Kunlik hisobot (Telegram), oyna 3 soat             │
    └──────────────────────────────────────────────────────────────────┘
    """
    print("[Scheduler] Ishga tushdi")
    pull_task = asyncio.create_task(_marketplace_pull_loop())

    try:
        while True:
            try:
                await _scheduler_tick()
            except Exception as e:
                print(f"[Scheduler] Loop xatolik: {e}")

            # Keyingi daqiqa boshigacha (ishlov vaqti siljitmasin)
            await asyncio.sleep(max(1, 60 - datetime.now().second))
    finally:
        pull_task.cancel()
