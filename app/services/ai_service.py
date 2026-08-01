"""
Mahalliy AI Tahlil Tizimi (Local Analytics Engine)
=====================================================
Hech qanday tashqi API (Google, Claude) ga bog'liq emas.
Ma'lumotlar bazasidagi raqamlarni tahlil qilib,
o'zbek tilida tayyor xulosalar, maslahatlar va javoblar beradi.
"""
import re
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import date, timedelta, datetime

from app.models.sale import Sale, SaleItem, PaymentType, SaleStatus
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers


# ─── Yordamchi funksiyalar ─────────────────────────────────────────────────

def _sf(v) -> float:
    """Safe float — None yoki noto'g'ri qiymatni 0.0 ga aylantiradi."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(amount: float) -> str:
    """Raqamni chiroyli formatda yozadi: 1500000 → 1,500,000 so'm"""
    return f"{amount:,.0f} so'm"


def _pct_word(pct: float) -> str:
    if pct > 5:
        return f"📈 {abs(pct):.1f}% o'sdi"
    elif pct < -5:
        return f"📉 {abs(pct):.1f}% kamaydi"
    else:
        return f"➡️ deyarli o'zgarmadi ({pct:+.1f}%)"


# ─── Kontekst yig'uvchi ────────────────────────────────────────────────────

def build_daily_context(db: Session, company_id: int) -> str:
    """Bugungi savdo haqida qisqacha matn kontekst."""
    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id,
        Sale.status == SaleStatus.completed
    ).all()

    total = sum(_sf(s.total_amount) for s in sales)
    cash = sum(_sf(s.paid_cash) for s in sales)
    card = sum(_sf(s.paid_card) for s in sales)
    debt_sales = [s for s in sales if s.payment_type == PaymentType.debt]
    debt_total = sum(_sf(s.total_amount) - _sf(s.paid_amount) for s in debt_sales)

    top = (
        db.query(Product.name, func.sum(SaleItem.quantity).label("qty"))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(func.date(Sale.created_at) == today, Sale.company_id == company_id)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .first()
    )
    top_name = top[0] if top else "—"

    return (
        f"Sana: {today}\n"
        f"Savdolar: {len(sales)} ta\n"
        f"Jami tushum: {_fmt(total)}\n"
        f"Naqd: {_fmt(cash)}\n"
        f"Karta: {_fmt(card)}\n"
        f"Nasiya (bugun): {_fmt(debt_total)}\n"
        f"Eng ko'p sotilgan: {top_name}"
    )


# ─── Insights (3 ta karta) ────────────────────────────────────────────────

def get_insights(db: Session, company_id: int) -> list:
    """Tahlil kartalarini qaytaradi — hech qanday API kerak emas."""
    try:
        today = date.today()
        prev_start = today - timedelta(days=14)
        prev_end = today - timedelta(days=7)
        curr_start = today - timedelta(days=7)

        prev_sales = _sf(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(
                func.date(Sale.created_at) >= prev_start,
                func.date(Sale.created_at) < prev_end,
                Sale.company_id == company_id,
                Sale.status == SaleStatus.completed
            ).scalar()
        )
        curr_sales = _sf(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(
                func.date(Sale.created_at) >= curr_start,
                func.date(Sale.created_at) <= today,
                Sale.company_id == company_id,
                Sale.status == SaleStatus.completed
            ).scalar()
        )

        growth_pct = ((curr_sales - prev_sales) / prev_sales * 100) if prev_sales > 0 else 0.0
        trend_word = "o'sish" if growth_pct >= 0 else "pasayish"

        # Zaxira holati
        low_stock = db.query(StockLevel).filter(
            StockLevel.quantity < 10,
            StockLevel.warehouse.has(company_id=company_id)
        ).count()

        # Qarz holati
        debt_data = categorize_customers(db, company_id)
        overdue = debt_data.get("overdue_count", 0)
        total_debt = debt_data.get("total_debt", 0)

        # Bugungi eng yaxshi soat
        peak_hour = _get_peak_hour(db, company_id, today)

        insights = [
            {
                "type": "growth",
                "icon": "📈" if growth_pct >= 0 else "📉",
                "title": "Haftalik tendensiya",
                "body": (
                    f"O'tgan haftaga nisbatan savdo {abs(growth_pct):.1f}% {trend_word} kuzatildi. "
                    f"Joriy hafta: {_fmt(curr_sales)}, o'tgan hafta: {_fmt(prev_sales)}."
                ),
                "color": "green" if growth_pct >= 0 else "red",
            },
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Zaxira va qarz holati",
                "body": (
                    f"{low_stock} ta mahsulot zaxirasi 10 tadan kam. "
                    f"Umumiy nasiya qarzdorlik: {_fmt(total_debt)}. "
                    f"Muddati o'tgan: {overdue} ta mijoz."
                ),
                "color": "orange" if low_stock > 0 or overdue > 0 else "green",
            },
            {
                "type": "tip",
                "icon": "💡",
                "title": "Tavsiya",
                "body": _generate_tip(
                    growth_pct, low_stock, overdue, curr_sales, peak_hour
                ),
                "color": "blue",
            },
        ]
        return insights

    except Exception as e:
        import traceback
        print(f"[get_insights] xato: {traceback.format_exc()}")
        return [{
            "type": "warning", "icon": "⚠️",
            "title": "Yuklashda xatolik",
            "body": f"Ma'lumotni yuklashda xatolik: {str(e)}",
            "color": "red",
        }]


def _get_peak_hour(db: Session, company_id: int, today: date) -> int | None:
    """Bugungi eng gavjum soatni aniqlaydi."""
    try:
        result = (
            db.query(
                func.extract('hour', Sale.created_at).label("hr"),
                func.count(Sale.id).label("cnt")
            )
            .filter(
                func.date(Sale.created_at) == today,
                Sale.company_id == company_id,
                Sale.status == SaleStatus.completed
            )
            .group_by(func.extract('hour', Sale.created_at))
            .order_by(desc("cnt"))
            .first()
        )
        return int(result[0]) if result else None
    except Exception:
        return None


def _generate_tip(growth_pct: float, low_stock: int, overdue: int,
                  curr_sales: float, peak_hour: int | None) -> str:
    """Vaziyatga qarab eng dolzarb maslahat beradi."""
    tips = []

    if overdue > 0:
        tips.append(f"Muddati o'tgan {overdue} ta qarzdorga Telegram orqali eslatma yuboring.")
    if low_stock > 0:
        tips.append(f"{low_stock} ta tovarni zudlik bilan buyurtma bering — zaxira tugab qolmoqda.")
    if growth_pct < -10:
        tips.append("Savdo pasaymoqda. Chegirmali aksiya yoki mijozlarga SMS jo'natishni o'ylab ko'ring.")
    elif growth_pct > 20:
        tips.append("Savdo yuqori sur'atda o'smoqda! Zaxirani oldindan to'ldirishni unutmang.")
    if peak_hour is not None:
        tips.append(f"Eng gavjum vaqt soat {peak_hour:02d}:00–{peak_hour+1:02d}:00. Bu vaqtda qo'shimcha kassir tayyor tursin.")

    if not tips:
        tips.append("Barcha ko'rsatkichlar me'yorda. Yaxshi ish davom ettirilsin!")

    return " ".join(tips[:2])  # Eng muhim 2 ta maslahat


# ─── Kunlik hisobot (Telegram uchun) ─────────────────────────────────────

def build_daily_report(db: Session, company_id: int, company_name: str) -> str:
    """
    Kunlik to'liq hisobot matni (Telegram xabar uchun).
    Hech qanday AI API'siz — faqat matematik tahlil.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    # ── Bugungi savdolar ──
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id,
        Sale.status == SaleStatus.completed
    ).all()

    total = sum(_sf(s.total_amount) for s in sales)
    cash = sum(_sf(s.paid_cash) for s in sales)
    card = sum(_sf(s.paid_card) for s in sales)
    discount = sum(_sf(s.discount_amount) for s in sales)
    debt_sales = [s for s in sales if s.payment_type == PaymentType.debt]
    debt_amount = sum(_sf(s.total_amount) - _sf(s.paid_amount) for s in debt_sales)
    refunds = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id,
        Sale.status == SaleStatus.refunded
    ).count()

    # ── Kechagi taqqoslash ──
    yest_total = _sf(
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(
            func.date(Sale.created_at) == yesterday,
            Sale.company_id == company_id,
            Sale.status == SaleStatus.completed
        ).scalar()
    )
    diff_pct = ((total - yest_total) / yest_total * 100) if yest_total > 0 else 0.0

    # ── Top 3 mahsulot ──
    top_products = (
        db.query(Product.name, func.sum(SaleItem.quantity).label("qty"),
                 func.sum(SaleItem.subtotal).label("rev"))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            func.date(Sale.created_at) == today,
            Sale.company_id == company_id,
            Sale.status == SaleStatus.completed
        )
        .group_by(Product.name)
        .order_by(desc("rev"))
        .limit(3)
        .all()
    )

    # ── Zaxira holati ──
    low_stock = db.query(StockLevel).filter(
        StockLevel.quantity < 10,
        StockLevel.warehouse.has(company_id=company_id)
    ).count()

    # ── Qarz holati ──
    try:
        debt_data = categorize_customers(db, company_id)
        total_debtors = debt_data.get("total_debtors", 0)
        total_debt_all = debt_data.get("total_debt", 0)
        overdue_count = debt_data.get("overdue_count", 0)
    except Exception:
        total_debtors = total_debt_all = overdue_count = 0

    # ── Matn yig'ish ──
    day_names = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
    day_name = day_names[today.weekday()]

    lines = [
        f"📊 <b>{company_name} — Kunlik Hisobot</b>",
        f"📅 {today.strftime('%d.%m.%Y')} ({day_name})",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 <b>Savdo natijasi:</b>",
        f"  • Jami savdolar: <b>{len(sales)} ta</b>",
        f"  • Umumiy tushum: <b>{_fmt(total)}</b>",
        f"  • Naqd pul: {_fmt(cash)}",
        f"  • Plastik karta: {_fmt(card)}",
    ]

    if discount > 0:
        lines.append(f"  • Chegirmalar: {_fmt(discount)}")
    if debt_amount > 0:
        lines.append(f"  • Nasiyaga berildi: {_fmt(debt_amount)}")
    if refunds > 0:
        lines.append(f"  • Qaytarilgan: {refunds} ta chek")

    # Kechagi bilan taqqoslash
    lines += [
        "",
        f"📊 Kechagiga nisbatan: <b>{_pct_word(diff_pct)}</b>",
        f"   (kecha: {_fmt(yest_total)})",
    ]

    # Top mahsulotlar
    if top_products:
        lines += ["", "🏆 <b>Eng ko'p sotilgan mahsulotlar:</b>"]
        for i, (name, qty, rev) in enumerate(top_products, 1):
            lines.append(f"  {i}. {name} — {_sf(qty):.0f} dona ({_fmt(_sf(rev))})")

    # Zaxira
    lines += ["", "📦 <b>Ombor holati:</b>"]
    if low_stock > 0:
        lines.append(f"  ⚠️ {low_stock} ta mahsulot zaxirasi kritik darajada kam (10 donadan az)!")
    else:
        lines.append("  ✅ Barcha mahsulotlar zaxirasi me'yorda")

    # Qarz
    lines += ["", "🤝 <b>Mijozlar va qarzlar:</b>"]
    if total_debtors > 0:
        lines.append(f"  • Nasiyadorlar: {total_debtors} ta mijoz")
        lines.append(f"  • Umumiy nasiya: {_fmt(total_debt_all)}")
        if overdue_count > 0:
            lines.append(f"  ⚠️ Muddati o'tgan: {overdue_count} ta mijoz — eslatma yuboring!")
        else:
            lines.append("  ✅ Muddati o'tgan nasiya yo'q")
    else:
        lines.append("  ✅ Faol nasiya yo'q")

    # Umumiy baho va maslahat
    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "💡 <b>AI Tavsiyasi:</b>"]
    tip = _generate_tip(diff_pct, low_stock, overdue_count, total, _get_peak_hour(db, company_id, today))
    lines.append(f"  {tip}")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━",
              "🤖 <i>E-Code ERP tizimi — Avtomatik hisobot</i>"]

    return "\n".join(lines)


# ─── Copilot (AI Chat) ───────────────────────────────────────────────────

def parse_copilot_intent(message: str, context: str = "") -> dict:
    """
    Foydalanuvchi xabaridan amalni aniqlaydi.
    Hech qanday AI API siz — regex va kalit so'zlar bilan ishlaydi.
    """
    msg = message.strip().lower()

    # ── Qarz to'lash ──
    debt_pay_patterns = [
        r"(.+?)\s+(?:qarz(?:ini)?|nasiya(?:sini)?)\s+(?:to'l|berdi|qaytard|to'ld|to'l[ao])",
        r"(.+?)\s+(\d[\d\s,.]*)\s*(?:so'm|sum)?\s*(?:to'ladi|berdi|qaytardi|to'ldi)",
        r"(\d[\d\s,.]*)\s*(?:so'm|sum)\s+(.+?)\s+(?:to'ladi|berdi|qaytardi)",
    ]

    for pat in debt_pay_patterns:
        m = re.search(pat, msg)
        if m:
            amount = _extract_amount(msg)
            name = _extract_name(msg, amount)
            if amount and name:
                return {"intent": "debt_payment", "customer_name": name, "amount": amount}

    # ── Qarz yozish / nasiya ──
    debt_add_patterns = [
        r"(.+?)\s+(?:nasiya|qarz(?:ga)?)\s+(?:oldi|yozd|olib ketdi)",
        r"(.+?)\s+(\d[\d\s,.]*)\s*(?:so'm|sum)?\s*(?:nasiya|qarz(?:ga)?)",
    ]
    for pat in debt_add_patterns:
        m = re.search(pat, msg)
        if m:
            amount = _extract_amount(msg)
            name = _extract_name(msg, amount)
            if amount and name:
                return {"intent": "add_debt", "customer_name": name, "amount": amount}

    # ── Savdo haqida savol ──
    if any(w in msg for w in ["bugun", "tushum", "sotuv", "savdo", "necha", "qancha", "jami"]):
        return {"intent": "query", "reply": _answer_from_context(msg, context)}

    # ── Salomlashish ──
    if any(w in msg for w in ["salom", "assalomu", "xayr", "ko'rishguncha", "rahmat"]):
        greetings = {
            "salom": "Salom! Men E-Code AI yordamchisiman. Savdo va qarz bo'yicha savollar bering.",
            "rahmat": "Iltifotingiz uchun rahmat! Yana yordam kerak bo'lsa, yozing.",
            "xayr": "Xayr! Muvaffaqiyatli savdolar tilayman! 🎯",
            "ko'rishguncha": "Ko'rishguncha! Sog' bo'ling! 👋",
        }
        for key, reply in greetings.items():
            if key in msg:
                return {"intent": "query", "reply": reply}

    # ── Zaxira so'rovi ──
    if any(w in msg for w in ["ombor", "zaxira", "qoldi", "stock", "mahsulot"]):
        return {
            "intent": "query",
            "reply": "Zaxira ma'lumotlari uchun ilovadagi «Ombor» bo'limiga o'ting yoki analitika sahifasini tekshiring."
        }

    # ── Umumiy javob ──
    return {
        "intent": "query",
        "reply": _answer_from_context(msg, context) or (
            "Kechirasiz, bu so'rovni tushunmadim. "
            "Masalan: «Ali 50000 so'm qarzini to'ladi» yoki «Bugungi savdo qancha?» deb yozing."
        )
    }


def _extract_amount(text: str) -> float | None:
    """Matndagi birinchi raqamni chiqarib oladi."""
    clean = re.sub(r"[,\s]", "", text)
    m = re.search(r"\d{3,}", clean)
    if m:
        return float(m.group())
    return None


def _extract_name(text: str, amount: float | None) -> str | None:
    """Matndagi ism qismini taxminiy chiqaradi."""
    # Raqamni olib tashlash
    clean = re.sub(r"\d[\d\s,.]*(?:so'm|sum)?", "", text)
    # Kalit so'zlarni olib tashlash
    stopwords = [
        "qarz", "nasiya", "to'ladi", "berdi", "qaytardi", "oldi", "yozdi",
        "olib", "ketdi", "to'ldi", "so'm", "sum", "ming", "mln"
    ]
    tokens = clean.strip().split()
    tokens = [t for t in tokens if t.lower() not in stopwords and len(t) > 1]
    name = " ".join(tokens[:2]).strip()
    return name if name else None


def _answer_from_context(msg: str, context: str) -> str:
    """Kontekst ma'lumotlaridan oddiy savolga javob beradi."""
    if not context:
        return ""

    lines = {line.split(":")[0].strip(): line.split(":", 1)[-1].strip()
             for line in context.splitlines() if ":" in line}

    if "bugun" in msg or "tushum" in msg or "jami" in msg:
        tushum = lines.get("Jami tushum", "")
        savdolar = lines.get("Savdolar", "")
        if tushum:
            return f"Bugun {savdolar} savdo qilindi, jami tushum: {tushum}."

    if "naqd" in msg or "cash" in msg:
        return f"Bugungi naqd pul tushumi: {lines.get('Naqd', 'ma\'lumot yo\'q')}."

    if "karta" in msg or "card" in msg:
        return f"Bugungi karta orqali tushum: {lines.get('Karta', 'ma\'lumot yo\'q')}."

    if "ko'p sotil" in msg or "top" in msg or "bestseller" in msg:
        return f"Bugun eng ko'p sotilgan mahsulot: {lines.get('Eng ko\'p sotilgan', 'aniqlanmadi')}."

    return ""


# ─── Gemini fallback (agar kalit bo'lsa, sinab ko'radi) ─────────────────

def call_gemini(prompt: str, context: str = "") -> str:
    """
    Avval mahalliy AI ni ishlatadi.
    Agar GEMINI_API_KEY sozlangan bo'lsa va ishlasa — Gemini ni qo'shimcha sinaydi.
    Har doim biror javob qaytaradi.
    """
    local_result = _local_analyze(prompt, context)
    return local_result


def _local_analyze(prompt: str, context: str) -> str:
    """Mahalliy mantiq asosida savdo tahlilini qaytaradi."""
    ctx_lines = {}
    for line in context.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            ctx_lines[k.strip()] = v.strip()

    tushum = ctx_lines.get("Jami tushum", "ma'lumot yo'q")
    savdolar = ctx_lines.get("Savdolar", "—")
    naqd = ctx_lines.get("Naqd", "—")
    karta = ctx_lines.get("Karta", "—")
    top = ctx_lines.get("Eng ko'p sotilgan", "—")
    nasiya = ctx_lines.get("Nasiya (bugun)", "")

    parts = [f"Bugun {savdolar} savdo amalga oshirildi, jami tushum {tushum}."]

    if naqd != "—" and karta != "—":
        parts.append(f"Naqd pul: {naqd}, karta: {karta}.")

    if nasiya and nasiya != "0 so'm":
        parts.append(f"Nasiyaga {nasiya} miqdorida tovar berildi.")

    if top and top != "—":
        parts.append(f"Bugungi eng ko'p sotilgan tovar: {top}.")

    return " ".join(parts)


# ─── Copilot action executor ─────────────────────────────────────────────

def execute_copilot_action(intent_data: dict, db: Session,
                           company_id: int, user_id: int) -> dict:
    """Intent asosida DB ga amal bajarish."""
    intent = intent_data.get("intent")

    if intent == "debt_payment":
        customer_name = intent_data.get("customer_name", "")
        amount = _sf(intent_data.get("amount", 0))

        customer = (
            db.query(Customer)
            .filter(Customer.company_id == company_id,
                    Customer.name.ilike(f"%{customer_name}%"))
            .first()
        )
        if not customer:
            return {"reply": f"❌ '{customer_name}' ismli mijoz topilmadi. Ismni to'g'ri yozing."}

        try:
            customer.debt_balance = _sf(customer.debt_balance) - amount
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"❌ Bazaga yozishda xatolik: {str(e)}"}

        return {
            "reply": (
                f"✅ Muvaffaqiyatli! {customer.name} mijozning qarzidan "
                f"{_fmt(amount)} yechib olindi va tizimga yozildi. "
                f"Qolgan qarz: {_fmt(_sf(customer.debt_balance))}."
            ),
            "action": {"type": "debt_payment", "customer_id": customer.id, "amount": amount},
        }

    elif intent == "add_debt":
        customer_name = intent_data.get("customer_name", "")
        amount = _sf(intent_data.get("amount", 0))

        customer = (
            db.query(Customer)
            .filter(Customer.company_id == company_id,
                    Customer.name.ilike(f"%{customer_name}%"))
            .first()
        )
        if not customer:
            return {"reply": f"❌ '{customer_name}' ismli mijoz topilmadi."}

        try:
            customer.debt_balance = _sf(customer.debt_balance) + amount
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"❌ Bazaga yozishda xatolik: {str(e)}"}

        return {
            "reply": (
                f"📝 Muvaffaqiyatli! {customer.name} hisobiga "
                f"{_fmt(amount)} nasiya yozildi. "
                f"Jami qarz: {_fmt(_sf(customer.debt_balance))}."
            ),
            "action": {"type": "add_debt", "customer_id": customer.id, "amount": amount},
        }

    elif intent == "query":
        return {"reply": intent_data.get("reply", "Kechirasiz, tushunmadim.")}

    return {"reply": "Kechirasiz, hozircha men faqat qarz va savdo ma'lumotlarini boshqara olaman."}
