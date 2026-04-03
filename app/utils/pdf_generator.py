import os
from fpdf import FPDF
from datetime import datetime

def build_sale_pdf(sale, company, customer, store_address="Manzil ko'rsatilmagan", footer_text="Xaridingiz uchun rahmat!"):
    # Font setup
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()

    # Try to load a unicode font (if exists), else fallback to generic
    font_path = os.path.join(os.path.dirname(__file__), 'DejaVuSans.ttf')
    has_unicode = os.path.exists(font_path)
    if has_unicode:
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
    else:
        # Fallback (may not support cyrillic fully but safe)
        pdf.set_font("Arial", size=12)

    templates = getattr(company, 'receipt_templates', {}) or {}
    nak = templates.get('nak', {})
    
    comp_name = nak.get("company") or (company.name if company else "Do'kon")
    addr = nak.get("address") or store_address
    header_text = nak.get("header") or ""
    phone = nak.get("phone") or getattr(company, 'phone', '')
    inn = nak.get("inn") or ""
    final_footer = nak.get("footer_note") or footer_text

    # Header
    pdf.set_font(pdf.font_family, "B", 18)
    pdf.cell(0, 10, comp_name, ln=True, align="C")

    pdf.set_font(pdf.font_family, "", 10)
    if addr:
        pdf.cell(0, 5, addr, ln=True, align="C")
    if phone:
        pdf.cell(0, 5, f"Tel: {phone}", ln=True, align="C")
    if inn:
        pdf.cell(0, 5, f"STIR: {inn}", ln=True, align="C")
    if header_text:
        pdf.set_font(pdf.font_family, "I", 10)
        pdf.cell(0, 5, header_text, ln=True, align="C")
        pdf.set_font(pdf.font_family, "", 10)
    pdf.ln(5)

    # Divider
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Info
    pdf.set_font(pdf.font_family, "B", 12)
    pdf.cell(0, 8, "SOTUV CHEKI (INVOICE)", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font(pdf.font_family, "", 10)
    pdf.cell(100, 6, f"Chek raqami: {sale.number}")
    m_sana = sale.created_at.strftime("%d.%m.%Y %H:%M")
    pdf.cell(90, 6, f"Sana: {m_sana}", align="R", ln=True)

    c_name = customer.name if customer else "Mijoz"
    pdf.cell(100, 6, f"Mijoz: {c_name}", ln=True)

    if customer and customer.debt_balance:
        # Show general debt if customer exists
        pdf.cell(100, 6, f"Joriy Umumiy Qarz: {customer.debt_balance:,.0f} so'm", ln=True)

    pdf.ln(5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    # Table Header
    pdf.set_font(pdf.font_family, "B", 10)
    pdf.cell(10, 8, "T/r", border=1, align="C")
    pdf.cell(80, 8, "Maxsulot nomi", border=1, align="L")
    pdf.cell(20, 8, "Miqdor", border=1, align="C")
    pdf.cell(40, 8, "Narx", border=1, align="C")
    pdf.cell(40, 8, "Summa", border=1, align="C", ln=True)

    pdf.set_font(pdf.font_family, "", 10)
    # Table Rows
    total_qty = 0
    total_sub = 0
    
    for idx, item in enumerate(sale.items, 1):
        if not item.product:
            continue
        p_name = str(item.product.name)
        qty = float(item.quantity)
        price = float(item.unit_price)
        sub = float(item.subtotal)
        total_qty += qty
        total_sub += sub

        # Convert to string formats
        qty_str = f"{qty:g}"
        price_str = f"{price:,.0f}".replace(",", " ")
        sub_str = f"{sub:,.0f}".replace(",", " ")

        # Draw row
        pdf.cell(10, 8, str(idx), border=1, align="C")
        
        # Max width logic for name
        if pdf.get_string_width(p_name) > 78:
            p_name = p_name[:30] + "..."
            
        pdf.cell(80, 8, p_name, border=1, align="L")
        pdf.cell(20, 8, qty_str, border=1, align="C")
        pdf.cell(40, 8, price_str, border=1, align="R")
        pdf.cell(40, 8, sub_str, border=1, align="R", ln=True)

    pdf.ln(2)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Summary
    pdf.set_font(pdf.font_family, "B", 11)
    
    # Discount calculation
    final_amount = float(sale.total_amount)
    discount_val = float(sale.discount_amount)
    grand_total = final_amount + discount_val # original if any

    pdf.cell(140, 8, "Jami:", align="R")
    pdf.cell(50, 8, f"{grand_total:,.0f} so'm".replace(",", " "), align="R", ln=True)

    if discount_val > 0:
        pdf.cell(140, 8, "Chegirma:", align="R")
        pdf.cell(50, 8, f"-{discount_val:,.0f} so'm".replace(",", " "), align="R", ln=True)
        pdf.cell(140, 8, "To'lanishi kerak:", align="R")
        pdf.cell(50, 8, f"{final_amount:,.0f} so'm".replace(",", " "), align="R", ln=True)

    # Payments
    pdf.set_font(pdf.font_family, "", 10)
    pdf.cell(140, 6, "To'landi:", align="R")
    pdf.cell(50, 6, f"{float(sale.paid_amount):,.0f} so'm".replace(",", " "), align="R", ln=True)
    
    debt_this_sale = final_amount - float(sale.paid_amount)
    if debt_this_sale > 0:
        pdf.set_font(pdf.font_family, "B", 10)
        pdf.cell(140, 6, "Bu xarid bo'yicha QARZ:", align="R")
        pdf.cell(50, 6, f"{debt_this_sale:,.0f} so'm".replace(",", " "), align="R", ln=True)

    pdf.ln(10)
    # Footer Note
    pdf.set_font(pdf.font_family, "I", 10)
    pdf.multi_cell(0, 6, final_footer, align="C")

    # Save logic
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "invoices")
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"{sale.number}.pdf")
    pdf.output(path)
    return path
