import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from fpdf import FPDF

_LOCAL_FONT = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")

try:
    import barcode
    _BARCODE_FONT = os.path.join(os.path.dirname(barcode.__file__), "fonts", "DejaVuSansMono.ttf")
except Exception:
    _BARCODE_FONT = ""

_FONT_REGULAR_CANDIDATES = [
    _LOCAL_FONT,
    _BARCODE_FONT,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]

_FONT_BOLD_CANDIDATES = [
    _LOCAL_FONT,
    _BARCODE_FONT,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/tahomabd.ttf",
]

def _first_existing(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def fmt_money(val: Any) -> str:
    try:
        n = float(val or 0)
        return f"{n:,.0f}".replace(",", " ")
    except Exception:
        return "0"

def clean_filename(s: str) -> str:
    s = re.sub(r'[^\w\s-]', '', str(s or '')).strip()
    return re.sub(r'[-\s]+', '_', s)


def enum_value(v: Any) -> str:
    """SQLAlchemy Enum (str, Enum) -> oddiy matn ('completed', 'cash' ...)."""
    if v is None:
        return ""
    return str(getattr(v, "value", v))


def content_disposition(filename: str) -> str:
    """HTTP header latin-1 bo'lishi shart: kirill/unicode nomlar uchun ASCII zaxira + RFC 5987 filename*."""
    from urllib.parse import quote
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip("_ ")
    ascii_name = re.sub(r'[^A-Za-z0-9._-]+', '_', ascii_name) or "sotuv.pdf"
    if not ascii_name.lower().endswith(".pdf"):
        ascii_name += ".pdf"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"

def get_sale_pdf_filename(sale: Any) -> str:
    cust = ""
    if getattr(sale, "customer", None):
        cust = getattr(sale.customer, "name", "") or ""
    elif getattr(sale, "customer_name", None):
        cust = str(sale.customer_name)
    if not cust:
        cust = "Mijoz"
    cust_clean = clean_filename(cust)

    dt = getattr(sale, "created_at", None)
    if not isinstance(dt, datetime):
        dt = datetime.now()
    date_str = dt.strftime("%Y-%m-%d_%H_%M_%S")
    return f"Sotuv_{cust_clean}_{date_str}.pdf"

class SalePDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.font_family_name = "helvetica"
        self.has_unicode = False

    def setup_fonts(self):
        reg = _first_existing(_FONT_REGULAR_CANDIDATES)
        bold = _first_existing(_FONT_BOLD_CANDIDATES)
        if reg:
            self.font_family_name = "CustomUnicode"
            self.has_unicode = True
            self.add_font("CustomUnicode", "", reg)
            self.add_font("CustomUnicode", "B", bold or reg)

    def u(self, text: Any) -> str:
        s = "" if text is None else str(text)
        if not self.has_unicode:
            return s.encode("latin-1", "replace").decode("latin-1")
        return s

def generate_sale_pdf_bytes(sale: Any, company: Any = None) -> bytes:
    """
    Generates PDF according to the exact structure from the sample:
    Sotuv_Nodir_Bula_2_brgat_2026-10-25_16_31_49.pdf
    """
    pdf = SalePDF(orientation="P", unit="mm", format="A4")
    pdf.setup_fonts()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(8, 10, 8)
    pdf.add_page()

    fn = pdf.font_family_name

    # 1. Header Metadata Section
    # Customer name
    cust_name = ""
    cust_phone = ""
    if getattr(sale, "customer", None):
        cust_name = getattr(sale.customer, "name", "") or ""
        cust_phone = getattr(sale.customer, "phone", "") or ""
    elif getattr(sale, "customer_name", None):
        cust_name = str(sale.customer_name)

    if not cust_name:
        cust_name = "Noma'lum mijoz"

    # Status
    raw_status = (enum_value(getattr(sale, "status", None)) or "completed").lower()
    if "complete" in raw_status:
        status_str = "Подтверждён"
    elif "cancel" in raw_status:
        status_str = "Отменён"
    elif "refund" in raw_status:
        status_str = "Возврат"
    elif "pending" in raw_status:
        status_str = "В ожидании"
    else:
        status_str = "Подтверждён"

    # Cashier / creator
    cashier_user = getattr(sale, "cashier", None)
    cashier_name = ""
    cashier_phone = ""
    if cashier_user:
        cashier_name = getattr(cashier_user, "name", "") or getattr(cashier_user, "full_name", "") or ""
        cashier_phone = getattr(cashier_user, "phone", "") or ""
    if not cashier_name:
        cashier_name = getattr(sale, "cashier_name", "") or "Kassir"

    creator_str = cashier_name
    if cashier_phone:
        creator_str += f" ({cashier_phone})"

    # Responsible (Ответственный)
    agent_user = getattr(sale, "agent", None)
    if agent_user:
        resp_name = getattr(agent_user, "name", "") or cashier_name
    else:
        resp_name = cashier_name

    # Number
    sale_number = str(getattr(sale, "number", "") or getattr(sale, "id", ""))

    # Date
    created_at = getattr(sale, "created_at", None)
    if isinstance(created_at, datetime):
        date_str = created_at.strftime("%Y-%m-%d %H:%M:%S")
    elif created_at:
        try:
            date_str = str(created_at).replace("T", " ")[:19]
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Header top layout:
    # Col 1: Labels (30mm) | Values (70mm) | Col 2: Labels (25mm) | Values (65mm)
    y_start = pdf.get_y()
    line_h = 5.5

    # Row 1: Клиент & Статус
    pdf.set_font(fn, "B", 9)
    pdf.set_xy(8, y_start)
    pdf.cell(32, line_h, pdf.u("Клиент"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(68, line_h, pdf.u(cust_name), 0, 0, "L")

    pdf.set_font(fn, "B", 9)
    pdf.set_xy(110, y_start)
    pdf.cell(28, line_h, pdf.u("Статус"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(64, line_h, pdf.u(status_str), 0, 1, "L")

    # Row 2: Оформил & Номер
    y_r2 = y_start + line_h
    pdf.set_xy(8, y_r2)
    pdf.set_font(fn, "B", 9)
    pdf.cell(32, line_h, pdf.u("Оформил"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(68, line_h, pdf.u(creator_str), 0, 0, "L")

    pdf.set_xy(110, y_r2)
    pdf.set_font(fn, "B", 9)
    pdf.cell(28, line_h, pdf.u("Номер"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(64, line_h, pdf.u(sale_number), 0, 1, "L")

    # Row 3: Ответственный & Дата
    y_r3 = y_start + line_h * 2
    pdf.set_xy(8, y_r3)
    pdf.set_font(fn, "B", 9)
    pdf.cell(32, line_h, pdf.u("Ответственный"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(68, line_h, pdf.u(resp_name), 0, 0, "L")

    pdf.set_xy(110, y_r3)
    pdf.set_font(fn, "B", 9)
    pdf.cell(28, line_h, pdf.u("Дата"), 0, 0, "L")
    pdf.set_font(fn, "", 9)
    pdf.cell(64, line_h, pdf.u(date_str), 0, 1, "L")

    pdf.ln(4)

    # 2. Title: Список товаров
    pdf.set_font(fn, "B", 11)
    pdf.cell(0, 7, pdf.u("Список товаров"), 0, 1, "C")
    pdf.ln(1)

    # 3. Table: Список товаров
    # Table columns:
    # 1. № (8mm, C)
    # 2. Товар или услуга (54mm, L)
    # 3. Кол-во (15mm, C)
    # 4. Ед.Изм (15mm, C)
    # 5. Цена (17mm, R)
    # 6. Валюта (13mm, C)
    # 7. Скидка (15mm, R)
    # 8. Цена со скидкой (24mm, R)
    # 9. Сумма (18mm, R)
    # 10. Склад (15mm, C)
    # Total = 8+54+15+15+17+13+15+24+18+15 = 194mm (margins 8mm left + 8mm right = 210mm)
    cols = [
        ("№", 8, "C"),
        ("Товар или услуга", 54, "L"),
        ("Кол-во", 15, "C"),
        ("Ед.Изм", 15, "C"),
        ("Цена", 17, "R"),
        ("Валюта", 13, "C"),
        ("Скидка", 15, "R"),
        ("Цена со скидкой", 24, "R"),
        ("Сумма", 18, "R"),
        ("Склад", 15, "C"),
    ]

    # Draw header
    pdf.set_font(fn, "B", 8)
    for title, width, align in cols:
        pdf.cell(width, 6.5, pdf.u(title), 1, 0, "C")
    pdf.ln(6.5)

    # Draw rows
    pdf.set_font(fn, "", 8)
    items = getattr(sale, "items", []) or []
    default_wh_name = ""
    if getattr(sale, "warehouse", None):
        default_wh_name = getattr(sale.warehouse, "name", "") or ""
    if not default_wh_name:
        default_wh_name = "Ombor"

    for idx, it in enumerate(items, 1):
        prod = getattr(it, "product", None)
        prod_name = ""
        if prod:
            prod_name = getattr(prod, "name", "") or ""
        if not prod_name:
            prod_name = getattr(it, "product_name", "") or f"Tovar #{idx}"

        qty = float(getattr(it, "quantity", 0) or 0)
        unit = str(getattr(it, "unit", "") or (getattr(prod, "unit", "") if prod else "") or "Штук")
        if unit.lower() in ["dona", "pcs", "piece", "штук"]:
            unit = "Штук"

        unit_price = float(getattr(it, "unit_price", 0) or 0)
        curr = str(getattr(it, "currency_code", "") or "UZS").upper()
        discount = float(getattr(it, "discount", 0) or 0)
        subtotal = float(getattr(it, "subtotal", 0) or (unit_price * qty - discount))

        disc_price = unit_price - (discount / qty if qty > 0 else discount)

        wh = getattr(it, "warehouse", None)
        wh_name = (getattr(wh, "name", "") if wh else "") or default_wh_name

        # Clip product name if too long for single line or multi_cell
        if pdf.get_string_width(pdf.u(prod_name)) > 51:
            while prod_name and pdf.get_string_width(pdf.u(prod_name + "..")) > 51:
                prod_name = prod_name[:-1]
            prod_name += ".."

        pdf.cell(8, 6, str(idx), 1, 0, "C")
        pdf.cell(54, 6, pdf.u(prod_name), 1, 0, "L")
        pdf.cell(15, 6, f"{qty:g}", 1, 0, "C")
        pdf.cell(15, 6, pdf.u(unit), 1, 0, "C")
        pdf.cell(17, 6, fmt_money(unit_price), 1, 0, "R")
        pdf.cell(13, 6, pdf.u(curr), 1, 0, "C")
        pdf.cell(15, 6, fmt_money(discount), 1, 0, "R")
        pdf.cell(24, 6, fmt_money(disc_price), 1, 0, "R")
        pdf.cell(18, 6, fmt_money(subtotal), 1, 0, "R")
        pdf.cell(15, 6, pdf.u(wh_name[:8]), 1, 1, "C")

    pdf.ln(5)

    # 4. Bottom Calculations Section (Hisob-kitob)
    # Долг до: shu sotuvdan oldingi qarz
    # Итого: shu sotuv summasi
    # Остаток задолженности: shu sotuv bo'yicha to'lanmagan qoldiq
    # Итого долг: Долг до + Остаток задолженности

    total_amount = float(getattr(sale, "total_amount", 0) or 0)
    paid_amount = float(getattr(sale, "paid_amount", 0) or 0)
    remaining_debt = max(0.0, total_amount - paid_amount)

    # Extract before debt
    prev_debt = 0.0
    raw_before = getattr(sale, "before_debt_balances", None)
    if isinstance(raw_before, dict):
        prev_debt = float(raw_before.get("UZS", 0) or sum(float(v or 0) for v in raw_before.values() if isinstance(v, (int, float))))
    elif isinstance(raw_before, (int, float)):
        prev_debt = float(raw_before)
    elif getattr(sale, "customer", None) and hasattr(sale.customer, "debt_balance"):
        curr_cust_debt = float(sale.customer.debt_balance or 0)
        prev_debt = max(0.0, curr_cust_debt - remaining_debt)

    total_debt = prev_debt + remaining_debt

    curr_code = "UZS"

    # Print bottom summary in 3 blocks:
    # Left block (Долг до, Итого долг) -> red bold
    # Middle block (Остаток задолженности) -> red bold
    # Right block (Итого) -> black bold
    y_calc = pdf.get_y()

    # Red color for debts: RGB(185, 28, 28)
    pdf.set_text_color(185, 28, 28)
    pdf.set_font(fn, "B", 9.5)

    # Left:
    pdf.set_xy(8, y_calc)
    pdf.cell(70, 5, pdf.u(f"Долг до: {fmt_money(prev_debt)} {curr_code}"), 0, 1, "L")
    pdf.set_xy(8, y_calc + 5)
    pdf.cell(70, 5, pdf.u(f"Итого долг: {fmt_money(total_debt)} {curr_code}"), 0, 1, "L")

    # Middle:
    pdf.set_xy(85, y_calc)
    pdf.cell(55, 5, pdf.u("Остаток"), 0, 1, "L")
    pdf.set_xy(85, y_calc + 5)
    pdf.cell(55, 5, pdf.u(f"задолженности: {fmt_money(remaining_debt)} {curr_code}"), 0, 1, "L")

    # Right: black bold
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(145, y_calc)
    pdf.cell(57, 5, pdf.u(f"Итого: {fmt_money(total_amount)} {curr_code}"), 0, 1, "R")

    return bytes(pdf.output())


def generate_sales_list_pdf_bytes(
    sales: List[Any],
    date_from: Optional[str] = "",
    date_to: Optional[str] = "",
    company_name: str = "E-Code ERP",
) -> bytes:
    """
    Generates an A4 Landscape PDF report of sales list.
    """
    pdf = SalePDF(orientation="L", unit="mm", format="A4")
    pdf.setup_fonts()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()
    fn = pdf.font_family_name

    # Header
    pdf.set_font(fn, "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(180, 8, pdf.u(f"{company_name} — Sotuvlar hisoboti"), 0, 0, "L")
    pdf.set_font(fn, "", 8)
    pdf.set_text_color(100, 116, 139)
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    pdf.cell(97, 8, pdf.u(f"Chop etilgan: {now_str}"), 0, 1, "R")

    # Subtitle
    pdf.set_font(fn, "", 9)
    pdf.set_text_color(71, 85, 105)
    period_str = f"Sana oralig'i: {date_from or 'Barcha'} dan {date_to or 'Hozirgacha'} gacha | Jami: {len(sales)} ta sotuv"
    pdf.cell(0, 5, pdf.u(period_str), 0, 1, "L")
    pdf.ln(3)

    # Calculate totals
    sum_total = 0.0
    sum_paid = 0.0
    sum_debt = 0.0
    for s in sales:
        t_amt = float(getattr(s, "total_amount", 0) or 0)
        p_amt = float(getattr(s, "paid_amount", 0) or 0)
        d_amt = max(0.0, t_amt - p_amt)
        sum_total += t_amt
        sum_paid += p_amt
        sum_debt += d_amt

    # KPI summary cards (4 cards across 277mm)
    card_w = 66
    y_card = pdf.get_y()
    card_h = 13

    cards = [
        ("JAMI SOTUVLAR", f"{len(sales)} ta", (15, 23, 42)),
        ("UMUMIY SUMMA", f"{fmt_money(sum_total)} so'm", (37, 99, 235)),
        ("JAMI TO'LANGAN", f"{fmt_money(sum_paid)} so'm", (5, 150, 105)),
        ("JAMI QARZ", f"{fmt_money(sum_debt)} so'm", (220, 38, 38)),
    ]

    for idx, (label, val, color) in enumerate(cards):
        x_pos = 10 + idx * (card_w + 4.3)
        pdf.set_xy(x_pos, y_card)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(x_pos, y_card, card_w, card_h, style="DF")
        pdf.set_xy(x_pos + 2, y_card + 1.5)
        pdf.set_font(fn, "B", 7)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(card_w - 4, 4, pdf.u(label), 0, 1, "L")
        pdf.set_xy(x_pos + 2, y_card + 5.5)
        pdf.set_font(fn, "B", 10)
        pdf.set_text_color(*color)
        pdf.cell(card_w - 4, 6, pdf.u(val), 0, 1, "L")

    pdf.set_xy(10, y_card + card_h + 4)

    # Table columns (total = 277mm)
    cols = [
        ("№", 10, "C"),
        ("Raqam", 24, "C"),
        ("Mijoz", 60, "L"),
        ("Jami summa", 32, "R"),
        ("To'langan", 30, "R"),
        ("Qarz", 30, "R"),
        ("To'lov turi", 26, "C"),
        ("Holati", 25, "C"),
        ("Sana", 40, "C"),
    ]

    # Draw table header
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    pdf.set_text_color(71, 85, 105)
    pdf.set_font(fn, "B", 8)
    for title, width, align in cols:
        pdf.cell(width, 7, pdf.u(title), 1, 0, align, fill=True)
    pdf.ln(7)

    # Table rows
    pdf.set_draw_color(226, 232, 240)
    for idx, s in enumerate(sales, 1):
        if pdf.get_y() > 190:
            pdf.add_page()
            pdf.set_fill_color(241, 245, 249)
            pdf.set_draw_color(203, 213, 225)
            pdf.set_text_color(71, 85, 105)
            pdf.set_font(fn, "B", 8)
            for title, width, align in cols:
                pdf.cell(width, 7, pdf.u(title), 1, 0, align, fill=True)
            pdf.ln(7)
            pdf.set_draw_color(226, 232, 240)

        t_amt = float(getattr(s, "total_amount", 0) or 0)
        p_amt = float(getattr(s, "paid_amount", 0) or 0)
        d_amt = max(0.0, t_amt - p_amt)

        cust_name = ""
        if getattr(s, "customer", None):
            cust_name = getattr(s.customer, "name", "") or ""
        elif getattr(s, "customer_name", None):
            cust_name = str(s.customer_name)
        if not cust_name:
            cust_name = "—"
        if pdf.get_string_width(pdf.u(cust_name)) > 57:
            while cust_name and pdf.get_string_width(pdf.u(cust_name + "..")) > 57:
                cust_name = cust_name[:-1]
            cust_name += ".."

        s_num = str(getattr(s, "number", "") or f"#{getattr(s, 'id', '')}")

        pt = enum_value(getattr(s, "payment_type", None)) or "—"
        pt_map = {
            "cash": "Naqd",
            "card": "Karta",
            "uzcard": "Uzcard",
            "humo": "Humo",
            "bank": "Bank",
            "click": "Click",
            "payme": "Payme",
            "visa": "Visa",
            "uzum": "Uzum",
            "debt": "Qarz",
            "mixed": "Aralash",
            "cashback": "Keshbek",
        }
        pt_str = pt_map.get(pt.lower(), pt)

        st = (enum_value(getattr(s, "status", None)) or "completed").lower()
        st_map = {
            "completed": "Bajarildi",
            "pending": "Kutilmoqda",
            "cancelled": "Bekor",
            "refunded": "Qaytarildi",
            "partial_refund": "Qisman qaytarilgan",
        }
        st_str = st_map.get(st, st)

        dt = getattr(s, "created_at", None)
        if isinstance(dt, datetime):
            d_str = dt.strftime("%d.%m.%Y %H:%M")
        elif dt:
            d_str = str(dt).replace("T", " ")[:16]
        else:
            d_str = "—"

        row_fill = (idx % 2 == 0)
        if row_fill:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)

        row_h = 6

        pdf.set_font(fn, "", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(10, row_h, str(idx), 1, 0, "C", fill=row_fill)

        pdf.set_font(fn, "B", 8)
        pdf.set_text_color(29, 78, 216)
        pdf.cell(24, row_h, pdf.u(s_num), 1, 0, "C", fill=row_fill)

        pdf.set_font(fn, "", 8)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(60, row_h, pdf.u(cust_name), 1, 0, "L", fill=row_fill)

        pdf.set_font(fn, "B", 8)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(32, row_h, fmt_money(t_amt), 1, 0, "R", fill=row_fill)

        pdf.set_font(fn, "", 8)
        pdf.set_text_color(5, 150, 105)
        pdf.cell(30, row_h, fmt_money(p_amt), 1, 0, "R", fill=row_fill)

        if d_amt > 0:
            pdf.set_font(fn, "B", 8)
            pdf.set_text_color(220, 38, 38)
            pdf.cell(30, row_h, fmt_money(d_amt), 1, 0, "R", fill=row_fill)
        else:
            pdf.set_font(fn, "", 8)
            pdf.set_text_color(148, 163, 184)
            pdf.cell(30, row_h, "—", 1, 0, "R", fill=row_fill)

        pdf.set_text_color(71, 85, 105)
        pdf.cell(26, row_h, pdf.u(pt_str), 1, 0, "C", fill=row_fill)

        pdf.cell(25, row_h, pdf.u(st_str), 1, 0, "C", fill=row_fill)

        pdf.set_font(fn, "", 7.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(40, row_h, pdf.u(d_str), 1, 1, "C", fill=row_fill)

    # Footer total row
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font(fn, "B", 8.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(94, 7, pdf.u("JAMI:"), 1, 0, "R", fill=True)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(32, 7, fmt_money(sum_total), 1, 0, "R", fill=True)
    pdf.set_text_color(5, 150, 105)
    pdf.cell(30, 7, fmt_money(sum_paid), 1, 0, "R", fill=True)
    pdf.set_text_color(220, 38, 38)
    pdf.cell(30, 7, fmt_money(sum_debt), 1, 0, "R", fill=True)
    pdf.cell(91, 7, "", 1, 1, "C", fill=True)

    return bytes(pdf.output())

