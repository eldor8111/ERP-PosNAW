import os
import re

DICTIONARY = {
    "Saqlash": "admin.dict.save", "O'chirish": "admin.dict.delete", "Tahrirlash": "admin.dict.edit",
    "Qo'shish": "admin.dict.add", "Bekor qilish": "admin.dict.cancel", "Yopish": "admin.dict.close",
    "Chop etish": "admin.dict.print", "Izlash": "admin.dict.search", "Filtrlash": "admin.dict.filter",
    "Tasdiqlash": "admin.dict.confirm", "Tozalash": "admin.dict.clear", "Excel": "admin.dict.excel",
    "PDF": "admin.dict.pdf", "Oldingi": "admin.dict.prev", "Keyingi": "admin.dict.next",
    "Sotuv": "admin.dict.sale", "Kirim": "admin.dict.income", "Chiqim": "admin.dict.expense",
    "Xarajat": "admin.dict.expense2", "Qoldiq": "admin.dict.balance", "Foyda": "admin.dict.profit",
    "Zarar": "admin.dict.loss", "Qarz": "admin.dict.debt", "To'lov": "admin.dict.payment",
    "Mahsulot": "admin.dict.product", "Kategoriya": "admin.dict.category", "Ombor": "admin.dict.warehouse",
    "Omborxona": "admin.dict.warehouse2", "Kassa": "admin.dict.pos", "Xodim": "admin.dict.employee",
    "Mijoz": "admin.dict.customer", "Kontragent": "admin.dict.contragent", "Foydalanuvchi": "admin.dict.user",
    "Ta'minotchi": "admin.dict.supplier", "Smena": "admin.dict.shift", "Hisobot": "admin.dict.report",
    "Sana": "admin.dict.date", "Holat": "admin.dict.status", "Status": "admin.dict.status2",
    "Miqdor": "admin.dict.qty", "Narx": "admin.dict.price", "Sotuv narxi": "admin.dict.sale_price",
    "Tan narx": "admin.dict.cost_price", "Jami": "admin.dict.total", "Raqam": "admin.dict.number",
    "Izoh": "admin.dict.comment", "Kassir": "admin.dict.cashier", "Ism": "admin.dict.name",
    "Telefon": "admin.dict.phone", "Manzil": "admin.dict.address", "Barcha": "admin.dict.all",
    "Barchasi": "admin.dict.all2", "Tanlang": "admin.dict.select", "Limit": "admin.dict.limit",
    "Jami:": "admin.dict.total_colon", "Ha": "admin.dict.yes", "Yo'q": "admin.dict.no",
    "Yakunlandi": "admin.dict.completed", "Kutish": "admin.dict.pending", "Faol": "admin.dict.active",
    "Nofaol": "admin.dict.inactive", "Mijoz topilmadi": "admin.dict.no_cust", "Ma'lumot topilmadi": "admin.dict.no_data",
    "RAQAM": "admin.dict.th_num", "SANA": "admin.dict.th_date", "MIJOZ": "admin.dict.th_cust",
    "XODIM": "admin.dict.th_emp", "JAMI": "admin.dict.th_total", "TO'LANGAN": "admin.dict.th_paid",
    "QARZGA": "admin.dict.th_debt", "HOLAT": "admin.dict.th_status", "KASSIR": "admin.dict.th_cashier",
    "MAHSULOT": "admin.dict.th_prod", "MIQDOR": "admin.dict.th_qty", "NARX": "admin.dict.th_price"
}

def fix_imports(content):
    if 'useLang' not in content:
        import_stmt = "import { useLang } from '../../context/LangContext';\n"
        if "import React" in content:
            content = content.replace("import React", import_stmt + "import React", 1)
        else:
            content = import_stmt + content
    
    # Very safe regex to add const { t } = useLang();
    matches = re.finditer(r'^([ \t]*)(export default function|function|const) ([A-Z][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:=>\s*)?{\n', content, re.MULTILINE)
    
    # We apply them in reverse to not mess up indices
    ranges = list(matches)
    for m in reversed(ranges):
        # ensure it's not a tiny arrow function or custom hook
        body_start = m.end()
        # Look ahead, if 'useLang' not inside body quickly
        if 'useLang' not in content[body_start:body_start+80]:
            # make sure it actually has a return statement later (is a component)
            if 'return' in content[body_start:body_start+4000]:
                indent = m.group(1) if m.group(1) else ''
                content = content[:body_start] + indent + "  const { t } = useLang();\n" + content[body_start:]
    
    return content

def safe_translate_all():
    base_dir = r"c:\ERPPos_extracted\ERPPos\frontend\src\pages\admin"
    for filename in os.listdir(base_dir):
        if not filename.endswith('.jsx'): continue
        path = os.path.join(base_dir, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        orig = content
        content = fix_imports(content)

        for word, key in DICTIONARY.items():
            escaped_word = word.replace("'", "\\'")
            
            # Use regex to match exact boundaries where possible
            # >Word<
            pattern_text = f">{word}<"
            repl_text = f">{{t('{key}') || '{escaped_word}'}}<"
            content = content.replace(pattern_text, repl_text)
            
            # placeholder
            pattern_pl_sq = f"placeholder='{word}'"
            repl_pl_sq = f"placeholder={{t('{key}') || '{escaped_word}'}}"
            content = content.replace(pattern_pl_sq, repl_pl_sq)
            
            pattern_pl_dq = f'placeholder="{word}"'
            repl_pl_dq = f'placeholder={{t(\'{key}\') || \'{escaped_word}\'}}'
            content = content.replace(pattern_pl_dq, repl_pl_dq)

            # label
            pattern_lbl_sq = f"label='{word}'"
            repl_lbl_sq = f"label={{t('{key}') || '{escaped_word}'}}"
            content = content.replace(pattern_lbl_sq, repl_lbl_sq)

            pattern_lbl_dq = f'label="{word}"'
            repl_lbl_dq = f'label={{t(\'{key}\') || \'{escaped_word}\'}}'
            content = content.replace(pattern_lbl_dq, repl_lbl_dq)
            
            # space padded > Word <
            pattern_text_sp = f"> {word} <"
            repl_text_sp = f"> {{t('{key}') || '{escaped_word}'}} <"
            content = content.replace(pattern_text_sp, repl_text_sp)

        if content != orig:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Translated words in {filename}")

if __name__ == "__main__":
    safe_translate_all()
    print("Pre-defined dictionary translation completed safely!")
