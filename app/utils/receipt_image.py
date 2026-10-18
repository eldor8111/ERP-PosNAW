import os
import io
import base64
import tempfile
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def _get_font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates.extend([
            "arialbd.ttf", "DejaVuSans-Bold.ttf", "segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ])
    else:
        candidates.extend([
            "arial.ttf", "DejaVuSans.ttf", "segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
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

def _draw_dashed_line(draw, x1, y, x2, dash_len=4, space_len=3, fill=(200, 200, 200)):
    cur_x = x1
    while cur_x < x2:
        end_x = min(cur_x + dash_len, x2)
        draw.line([(cur_x, y), (end_x, y)], fill=fill, width=1)
        cur_x += dash_len + space_len

def _load_logo(logo_str, max_height=55, max_width=180):
    if not logo_str or not isinstance(logo_str, str):
        return None
    try:
        if logo_str.startswith("data:image/"):
            header, b64_data = logo_str.split(",", 1)
            raw = base64.b64decode(b64_data)
            im = Image.open(io.BytesIO(raw))
        elif os.path.exists(logo_str):
            im = Image.open(logo_str)
        elif logo_str.startswith("http://") or logo_str.startswith("https://"):
            import urllib.request
            req = urllib.request.Request(logo_str, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                im = Image.open(io.BytesIO(resp.read()))
        else:
            return None
            
        im = im.convert("RGBA")
        w, h = im.size
        ratio = min(max_height / max(1, h), max_width / max(1, w))
        new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
        return im.resize((new_w, new_h), Image.Resampling.LANCZOS)
    except Exception as e:
        print("[receipt_image] Logo load error:", e)
        return None

def build_sale_image(
    sale,
    company,
    customer,
    seller: str = None,
    prev_debt=None,
    new_debt=None,
    store_address: str = "Manzil ko'rsatilmagan",
    footer_text: str = "Xaridingiz uchun rahmat!"
) -> str:
    """
    Chek sozlamalaridagi A4 Nakladnoy andozasi asosida
    yuqori sifatli rasmiy chek rasmini (PNG) yaratadi va fayl yo'lini qaytaradi.
    """
    templates = getattr(company, 'receipt_templates', {}) or {}
    nak = templates.get('nak', {}) if isinstance(templates, dict) else {}

    def sh(key, def_val=True):
        val = nak.get(key)
        return bool(val) if val is not None else def_val

    comp_name = nak.get("company") or getattr(company, 'name', "Do'kon") or "Do'kon"
    addr = nak.get("address") or store_address or ""
    phone = nak.get("phone") or getattr(company, 'phone', '') or ""
    inn = nak.get("inn") or ""
    bank = nak.get("bank") or ""
    account = nak.get("account") or ""
    mfo = nak.get("mfo") or ""
    final_footer = nak.get("footer_note") or footer_text or ""

    # Fontlar
    f_comp = _get_font(18, bold=True)
    f_sub = _get_font(11, bold=False)
    f_title = _get_font(13, bold=True)
    f_bold = _get_font(10, bold=True)
    f_body = _get_font(10, bold=False)
    f_small = _get_font(9, bold=False)

    width = 960
    margin = 35
    content_w = width - 2 * margin

    items = list(getattr(sale, "items", []))
    item_row_h = 24
    hdr_h = 26
    tot_row_h = 22

    # Balandlik hisoblash
    est_height = 420 + (len(items) * item_row_h) + (12 * tot_row_h) + 160
    img = Image.new("RGB", (width, max(800, est_height)), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    y = 25

    # 1. Logo
    logo_sz = int(nak.get("logo_size") or 50)
    logo_img = _load_logo(nak.get("logo"), max_height=logo_sz, max_width=180)
    if logo_img:
        lw, lh = logo_img.size
        lx = (width - lw) // 2
        img.paste(logo_img, (lx, y), mask=logo_img.split()[3] if logo_img.mode == 'RGBA' else None)
        y += lh + 8

    # 2. Korxona rekvizitlari
    draw.text((width // 2, y), str(comp_name), fill=(17, 24, 39), font=f_comp, anchor="mt")
    y += 24
    if addr and addr != "Manzil ko'rsatilmagan":
        draw.text((width // 2, y), str(addr), fill=(55, 65, 81), font=f_sub, anchor="mt")
        y += 18
    if phone:
        draw.text((width // 2, y), f"Tel: {phone}", fill=(55, 65, 81), font=f_sub, anchor="mt")
        y += 18
    if inn:
        draw.text((width // 2, y), f"STIR: {inn}", fill=(55, 65, 81), font=f_sub, anchor="mt")
        y += 18
    if bank or account or mfo:
        b_parts = []
        if bank: b_parts.append(f"Bank: {bank}")
        if account: b_parts.append(f"H/r: {account}")
        if mfo: b_parts.append(f"MFO: {mfo}")
        draw.text((width // 2, y), " | ".join(b_parts), fill=(55, 65, 81), font=f_sub, anchor="mt")
        y += 18

    y += 8

    # 3. Hujjat sarlavhasi
    sale_num = getattr(sale, "number", None) or f"#{sale.id}"
    created_at = getattr(sale, "created_at", None) or datetime.now()
    sana_str = created_at.strftime("%Y-%m-%d") if hasattr(created_at, "strftime") else str(created_at)[:10]
    draw.text((width // 2, y), f"NAKLADNOY № {sale_num} / {sana_str}", fill=(17, 24, 39), font=f_title, anchor="mt")
    y += 26

    # 4. Info satri (Mijoz, Filial, Xodim, Holat...)
    c_name = getattr(customer, "name", "Mijoz") if customer else (getattr(sale, "customer_name", None) or "Mijoz")
    branch = getattr(sale, "branch", None) or (getattr(sale, "warehouse", None).branch if getattr(sale, "warehouse", None) else None)
    b_name = getattr(branch, "name", "___") if branch else "___"
    seller_name = seller or getattr(sale, "employee_name", None) or getattr(sale, "cashier_name", None) or "___"
    status_raw = str(getattr(sale, "status", "completed") or "completed")
    st_val = status_raw.value if hasattr(status_raw, "value") else status_raw
    c_phone = getattr(customer, "phone", "") or "___"

    info_parts = [
        ("Mijoz:", str(c_name)),
        ("Filial:", str(b_name)),
        ("Foydalanuvchi:", "___"),
        ("Xodim:", str(seller_name)),
        ("Holat:", str(st_val)),
        ("Kontakt:", str(c_phone)),
    ]
    cur_x = margin
    for label, val in info_parts:
        draw.text((cur_x, y), label, fill=(17, 24, 39), font=f_bold)
        w_lbl = draw.textlength(label + " ", font=f_bold)
        draw.text((cur_x + w_lbl, y), val, fill=(55, 65, 81), font=f_body)
        w_val = draw.textlength(val, font=f_body)
        cur_x += w_lbl + w_val + 20
    y += 24

    # 5. Jadval ustunlari
    all_cols = [
        {"key": "show_ordering_number", "id": "no", "label": "№", "w": 30, "align": "center", "def": True},
        {"key": "show_item", "id": "item", "label": "Mahsulot nomi", "w": 180, "align": "left", "def": True},
        {"key": "show_measurement", "id": "unit", "label": "O'lchov", "w": 50, "align": "center", "def": True},
        {"key": "item_qty", "id": "qty", "label": "Soni", "w": 45, "align": "right", "def": True},
        {"key": "show_price", "id": "price", "label": "Narxi", "w": 70, "align": "right", "def": True},
        {"key": "show_discount", "id": "disc", "label": "Chegirma", "w": 65, "align": "right", "def": True},
        {"key": "show_price_with_discount", "id": "disc_price", "label": "Chegirmali narx", "w": 90, "align": "right", "def": True},
        {"key": "show_net_price", "id": "net_price", "label": "Sof narx", "w": 70, "align": "right", "def": True},
        {"key": "show_currency", "id": "curr", "label": "Valyuta", "w": 55, "align": "center", "def": True},
        {"key": "show_warehouse", "id": "wh", "label": "Ombor", "w": 70, "align": "left", "def": True},
        {"key": "show_sku", "id": "sku", "label": "SKU", "w": 85, "align": "left", "def": True},
        {"key": "item_total", "id": "total", "label": "Jami", "w": 85, "align": "right", "def": True},
    ]

    active_cols = [c for c in all_cols if sh(c["key"], c["def"])]
    if not active_cols:
        active_cols = all_cols

    # Kenglikni content_w ga to'liq proporsional taqsimlash
    total_w_base = sum(c["w"] for c in active_cols)
    scale = content_w / max(1, total_w_base)
    for c in active_cols:
        c["w"] = max(24, int(c["w"] * scale))
    # oxirgi ustunni aniq yopish
    diff = content_w - sum(c["w"] for c in active_cols)
    active_cols[-1]["w"] += diff

    # Jadval Headeri
    cx = margin
    for col in active_cols:
        cw = col["w"]
        draw.rectangle([(cx, y), (cx + cw, y + hdr_h)], fill=(240, 240, 240), outline=(100, 100, 100), width=1)
        if col["align"] == "center":
            draw.text((cx + cw // 2, y + 6), col["label"], fill=(17, 24, 39), font=f_bold, anchor="mt")
        elif col["align"] == "right":
            draw.text((cx + cw - 5, y + 6), col["label"], fill=(17, 24, 39), font=f_bold, anchor="rt")
        else:
            draw.text((cx + 5, y + 6), col["label"], fill=(17, 24, 39), font=f_bold)
        cx += cw
    y += hdr_h

    # Mahsulot qatorlari
    total_qty_sum = 0
    total_calc_sum = 0
    wh_default = getattr(getattr(sale, "warehouse", None), "name", "Do'kon") or "Do'kon"

    for idx, item in enumerate(items, 1):
        prod = getattr(item, "product", None)
        p_name = getattr(prod, "name", "") if prod else f"ID={getattr(item, 'product_id', '')}"
        qty = float(getattr(item, "quantity", 0) or getattr(item, "qty_ordered", 0) or 0)
        price = float(getattr(item, "unit_price", 0) or 0)
        disc = float(getattr(item, "discount", 0) or getattr(item, "discount_val", 0) or 0)
        sub = float(getattr(item, "subtotal", 0) or (qty * price - disc))
        unit = getattr(prod, "measurement_name", None) or getattr(prod, "unit", "") or "dona"
        wh_name = getattr(getattr(item, "warehouse", None), "name", wh_default) or wh_default
        sku = getattr(prod, "sku", "") or getattr(prod, "barcode", "") or ""
        curr = getattr(item, "currency_code", None) or "so'm"

        disc_price = price - (disc / qty if qty > 0 else 0)
        total_qty_sum += qty
        total_calc_sum += sub

        item_data = {
            "no": str(idx),
            "item": str(p_name),
            "unit": str(unit),
            "qty": str(int(qty)) if qty == int(qty) else f"{qty:g}",
            "price": _fmt(price),
            "disc": f"-{_fmt(disc)}" if disc > 0 else "",
            "disc_price": _fmt(disc_price),
            "net_price": _fmt(sub),
            "curr": str(curr),
            "wh": str(wh_name),
            "sku": str(sku),
            "total": f"{_fmt(sub)} so'm",
        }

        # Qatorni chizish
        cx = margin
        for col in active_cols:
            cw = col["w"]
            draw.rectangle([(cx, y), (cx + cw, y + item_row_h)], fill=(255, 255, 255), outline=(100, 100, 100), width=1)
            val = item_data.get(col["id"], "")
            if col["align"] == "center":
                draw.text((cx + cw // 2, y + 5), val, fill=(17, 24, 39), font=f_body, anchor="mt")
            elif col["align"] == "right":
                draw.text((cx + cw - 5, y + 5), val, fill=(17, 24, 39), font=f_body, anchor="rt")
            else:
                # Cheklangan uzunlik
                draw.text((cx + 5, y + 5), val[:38], fill=(17, 24, 39), font=f_body)
            cx += cw
        y += item_row_h

    # Jadval oxiridagi JAMI qatori
    tot_amt = float(getattr(sale, "total_amount", 0) or total_calc_sum)
    span_w = sum(c["w"] for c in active_cols[:-1])
    draw.rectangle([(margin, y), (margin + span_w, y + item_row_h)], fill=(255, 255, 255), outline=(100, 100, 100), width=1)
    draw.text((margin + span_w - 8, y + 5), "JAMI:", fill=(17, 24, 39), font=f_bold, anchor="rt")
    draw.rectangle([(margin + span_w, y), (margin + content_w, y + item_row_h)], fill=(255, 255, 255), outline=(100, 100, 100), width=1)
    draw.text((margin + content_w - 5, y + 5), f"{_fmt(tot_amt)} so'm", fill=(17, 24, 39), font=f_bold, anchor="rt")
    y += item_row_h + 14

    # 6. Totals bo'limi (chiziqli qatorlar)
    disc_amt = float(getattr(sale, "discount_amount", 0) or 0)
    paid_amt = float(getattr(sale, "paid_amount", 0) or 0)
    
    # Qarz hisoblari
    this_sale_debt = max(0.0, tot_amt - paid_amt)
    old_debt_val = float(prev_debt if prev_debt is not None else (getattr(customer, "debt_balance", 0) or 0))
    if new_debt is not None:
        final_debt_val = float(new_debt)
    else:
        final_debt_val = old_debt_val + this_sale_debt

    totals_lines = [
        ("JAMI:", f"{_fmt(tot_amt)} so'm", True, (17, 24, 39)),
        ("Milliy valyutada:", "___", False, (55, 65, 81)),
        ("Jami miqdor:", str(int(total_qty_sum)) if total_qty_sum == int(total_qty_sum) else f"{total_qty_sum:g}", False, (55, 65, 81)),
        ("Chegirma:", f"-{_fmt(disc_amt)} so'm" if disc_amt > 0 else "-0 so'm", False, (55, 65, 81)),
        ("% Chegirma:", "___%", False, (55, 65, 81)),
        ("To'langan:", f"{_fmt(paid_amt)} so'm", False, (55, 65, 81)),
        ("Joriy qarz:", f"{_fmt(tot_amt if paid_amt == 0 else this_sale_debt)} so'm", True, (220, 38, 38)),
        ("Oldingi qarz:", f"{_fmt(old_debt_val)} so'm", False, (55, 65, 81)),
        ("Umumiy qarz:", f"{_fmt(final_debt_val)} so'm", True, (17, 24, 39)),
        ("Oxirgi to'lov:", "___", False, (55, 65, 81)),
        ("Izoh:", str(getattr(sale, 'note', '') or '___'), False, (55, 65, 81)),
    ]

    for t_lbl, t_val, is_b, color in totals_lines:
        font_use = f_bold if is_b else f_body
        draw.text((margin, y + 2), t_lbl, fill=color, font=font_use)
        draw.text((margin + content_w, y + 2), t_val, fill=color, font=font_use, anchor="rt")
        _draw_dashed_line(draw, margin, y + tot_row_h - 2, margin + content_w)
        y += tot_row_h

    y += 18

    # 7. Imzolar
    draw.text((margin, y), "Direktor: ________", fill=(55, 65, 81), font=f_body)
    draw.text((margin + content_w - 180, y), "Buxgalter: ________", fill=(55, 65, 81), font=f_body)
    y += 30

    # 8. Pastki izoh
    if final_footer:
        draw.text((width // 2, y), str(final_footer), fill=(107, 114, 128), font=f_small, anchor="mt")
        y += 20

    # Kesish
    final_h = y + 15
    img = img.crop((0, 0, width, final_h))

    # Faylga saqlash
    out_dir = os.path.join(tempfile.gettempdir(), "receipts")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"sale_{sale.id}_{int(time.time())}.png")
    img.save(out_path, format="PNG", optimize=True)
    return out_path
