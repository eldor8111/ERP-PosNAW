import os
from datetime import datetime
from decimal import Decimal
from PIL import Image, ImageDraw, ImageFont

def _get_font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates.extend([
            "DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "DejaVuSans.ttf", "arial.ttf", "segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ])
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def _fmt(val):
    try:
        v = float(val or 0)
        return f"{int(v):,}".replace(",", " ") if v == int(v) else f"{v:,.1f}".replace(",", " ")
    except Exception:
        return str(val or "0")

def build_sale_image(sale, company, customer, store_address="Manzil ko'rsatilmagan", footer_text="Xaridingiz uchun rahmat!") -> str:
    """A4 uslubidagi chiroyli nakladnoy rasmini (PNG) yaratadi va fayl yo'lini qaytaradi."""
    templates = getattr(company, 'receipt_templates', {}) or {}
    nak = templates.get('nak', {}) if isinstance(templates, dict) else {}
    
    comp_name = nak.get("company") or (company.name if company else "Do'kon")
    addr = nak.get("address") or store_address or ""
    phone = nak.get("phone") or getattr(company, 'phone', '') or ""
    inn = nak.get("inn") or ""
    final_footer = nak.get("footer_note") or footer_text or "Xaridingiz uchun rahmat!"
    
    # Fontlar
    f_title = _get_font(22, bold=True)
    f_header = _get_font(18, bold=True)
    f_sub = _get_font(13, bold=False)
    f_bold = _get_font(13, bold=True)
    f_body = _get_font(12, bold=False)
    f_small = _get_font(11, bold=False)
    
    width = 800
    margin = 40
    content_w = width - 2 * margin
    
    # Balandlikni hisoblash
    items = list(getattr(sale, "items", []))
    item_row_h = 28
    base_h = 380 + (len(items) * item_row_h) + 160
    height = max(700, base_h)
    
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    y = 30
    
    # 1. Korxona nomi va rekvizitlar
    draw.text((width // 2, y), str(comp_name), fill=(17, 24, 39), font=f_title, anchor="mt")
    y += 32
    if addr:
        draw.text((width // 2, y), str(addr), fill=(75, 85, 99), font=f_sub, anchor="mt")
        y += 20
    if phone:
        draw.text((width // 2, y), f"Tel: {phone}", fill=(75, 85, 99), font=f_sub, anchor="mt")
        y += 20
    if inn:
        draw.text((width // 2, y), f"STIR: {inn}", fill=(75, 85, 99), font=f_sub, anchor="mt")
        y += 20
        
    y += 10
    draw.line([(margin, y), (width - margin, y)], fill=(209, 213, 219), width=2)
    y += 16
    
    # 2. Hujjat sarlavhasi
    sale_num = getattr(sale, "number", None) or f"#{sale.id}"
    draw.text((width // 2, y), f"NAKLADNOY № {sale_num}", fill=(17, 24, 39), font=f_header, anchor="mt")
    y += 26
    
    created_at = getattr(sale, "created_at", None) or datetime.now()
    sana_str = created_at.strftime("%d.%m.%Y %H:%M") if hasattr(created_at, "strftime") else str(created_at)
    draw.text((width // 2, y), f"Sana: {sana_str}", fill=(107, 114, 128), font=f_sub, anchor="mt")
    y += 28
    
    # 3. Mijoz va filial ma'lumoti
    c_name = getattr(customer, "name", "Mijoz") if customer else "Mijoz"
    c_phone = getattr(customer, "phone", "") if customer else ""
    c_debt = getattr(customer, "debt_balance", 0) if customer else 0
    
    draw.text((margin, y), f"Mijoz: {c_name}", fill=(17, 24, 39), font=f_bold)
    if c_phone:
        draw.text((width - margin, y), f"Tel: {c_phone}", fill=(55, 65, 81), font=f_body, anchor="rt")
    y += 22
    
    branch = getattr(sale, "branch", None) or (getattr(sale, "warehouse", None).branch if getattr(sale, "warehouse", None) else None)
    if branch:
        b_name = getattr(branch, "name", "")
        draw.text((margin, y), f"Filial: {b_name}", fill=(75, 85, 99), font=f_body)
    if float(c_debt or 0) > 0:
        draw.text((width - margin, y), f"Joriy umumiy qarz: {_fmt(c_debt)} so'm", fill=(185, 28, 28), font=f_bold, anchor="rt")
    y += 26
    
    # 4. Jadval sarlavhasi
    tbl_x1 = margin
    tbl_x2 = width - margin
    col_tr = tbl_x1 + 40
    col_name = tbl_x1 + 380
    col_qty = col_name + 90
    col_price = col_qty + 120
    col_total = tbl_x2
    
    # Header box
    draw.rectangle([(tbl_x1, y), (tbl_x2, y + 28)], fill=(243, 244, 246), outline=(156, 163, 175), width=1)
    draw.text((tbl_x1 + 20, y + 6), "T/r", fill=(17, 24, 39), font=f_bold, anchor="mt")
    draw.text((col_tr + 10, y + 6), "Mahsulot nomi", fill=(17, 24, 39), font=f_bold)
    draw.text((col_qty - 10, y + 6), "Miqdor", fill=(17, 24, 39), font=f_bold, anchor="rt")
    draw.text((col_price - 10, y + 6), "Narx", fill=(17, 24, 39), font=f_bold, anchor="rt")
    draw.text((col_total - 10, y + 6), "Summa", fill=(17, 24, 39), font=f_bold, anchor="rt")
    y += 28
    
    total_qty = 0
    total_sub = 0
    
    for idx, item in enumerate(items, 1):
        prod = getattr(item, "product", None)
        p_name = getattr(prod, "name", "") if prod else f"ID={getattr(item, 'product_id', '')}"
        if len(p_name) > 38:
            p_name = p_name[:35] + "..."
            
        qty = float(getattr(item, "quantity", 0) or 0)
        price = float(getattr(item, "unit_price", 0) or 0)
        sub = float(getattr(item, "subtotal", 0) or (qty * price))
        total_qty += qty
        total_sub += sub
        
        # Qator foni (alternating)
        bg_col = (255, 255, 255) if idx % 2 != 0 else (249, 250, 251)
        draw.rectangle([(tbl_x1, y), (tbl_x2, y + item_row_h)], fill=bg_col, outline=(229, 231, 235), width=1)
        
        draw.text((tbl_x1 + 20, y + 6), str(idx), fill=(55, 65, 81), font=f_body, anchor="mt")
        draw.text((col_tr + 10, y + 6), str(p_name), fill=(17, 24, 39), font=f_body)
        qty_str = str(int(qty)) if qty == int(qty) else f"{qty:g}"
        draw.text((col_qty - 10, y + 6), qty_str, fill=(55, 65, 81), font=f_body, anchor="rt")
        draw.text((col_price - 10, y + 6), _fmt(price), fill=(55, 65, 81), font=f_body, anchor="rt")
        draw.text((col_total - 10, y + 6), _fmt(sub), fill=(17, 24, 39), font=f_bold, anchor="rt")
        y += item_row_h
        
    y += 12
    
    # 5. Xulosa (Totals)
    tot_amount = float(getattr(sale, "total_amount", 0) or total_sub)
    disc_amount = float(getattr(sale, "discount_amount", 0) or 0)
    paid_amount = float(getattr(sale, "paid_amount", 0) or 0)
    debt_amount = tot_amount - paid_amount
    
    summary_x = width - margin - 280
    
    draw.text((summary_x, y), "Jami:", fill=(75, 85, 99), font=f_bold)
    draw.text((width - margin, y), f"{_fmt(tot_amount + disc_amount)} so'm", fill=(17, 24, 39), font=f_bold, anchor="rt")
    y += 22
    
    if disc_amount > 0:
        draw.text((summary_x, y), "Chegirma:", fill=(75, 85, 99), font=f_body)
        draw.text((width - margin, y), f"-{_fmt(disc_amount)} so'm", fill=(185, 28, 28), font=f_body, anchor="rt")
        y += 20
        draw.text((summary_x, y), "To'lanishi kerak:", fill=(75, 85, 99), font=f_bold)
        draw.text((width - margin, y), f"{_fmt(tot_amount)} so'm", fill=(17, 24, 39), font=f_bold, anchor="rt")
        y += 22
        
    draw.text((summary_x, y), "To'landi:", fill=(75, 85, 99), font=f_body)
    draw.text((width - margin, y), f"{_fmt(paid_amount)} so'm", fill=(16, 185, 129), font=f_bold, anchor="rt")
    y += 20
    
    if debt_amount > 0:
        draw.text((summary_x, y), "Bu xariddan qarz:", fill=(185, 28, 28), font=f_bold)
        draw.text((width - margin, y), f"{_fmt(debt_amount)} so'm", fill=(185, 28, 28), font=f_bold, anchor="rt")
        y += 22
        
    y += 16
    draw.line([(margin, y), (width - margin, y)], fill=(229, 231, 235), width=1)
    y += 16
    
    # 6. Pastki izoh
    draw.text((width // 2, y), str(final_footer), fill=(107, 114, 128), font=f_sub, anchor="mt")
    y += 22
    draw.text((width // 2, y), "E-Code ERP & POS tizimi orqali yaratildi", fill=(156, 163, 175), font=f_small, anchor="mt")
    y += 24
    
    # Rasmni haqiqiy balandlik bo'yicha qirqish
    final_img = img.crop((0, 0, width, y))
    
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "invoices")
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{sale_num}.png")
    final_img.save(file_path, "PNG", optimize=True)
    return file_path
