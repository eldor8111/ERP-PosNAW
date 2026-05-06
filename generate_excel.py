import os
import sys
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("XATO: .env faylida DATABASE_URL topilmadi.")
    sys.exit(1)

try:
    engine = create_engine(DB_URL)
except Exception as e:
    print(f"XATO: Bazaga ulanishda muammo - {e}")
    sys.exit(1)

query1 = """
WITH all_barcodes AS (
    SELECT barcode, name FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND barcode IS NOT NULL AND barcode != ''
    UNION ALL
    SELECT json_array_elements_text(extra_barcodes::json) AS barcode, name FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND extra_barcodes IS NOT NULL AND extra_barcodes != '' AND extra_barcodes != '[]'
)
SELECT 
    COUNT(barcode) AS "Jami shtrix kodlar",
    COUNT(DISTINCT name) AS "Farqli tovarlar soni"
FROM all_barcodes;
"""

query2 = """
WITH all_barcodes AS (
    SELECT name, barcode FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND barcode IS NOT NULL AND barcode != ''
    UNION ALL
    SELECT name, json_array_elements_text(extra_barcodes::json) AS barcode FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND extra_barcodes IS NOT NULL AND extra_barcodes != '' AND extra_barcodes != '[]'
)
SELECT 
    name AS "Tovar nomi", 
    COUNT(barcode) AS "Shtrix kodlar soni", 
    string_agg(barcode, ', ') AS "Barcha shtrix kodlar"
FROM all_barcodes
GROUP BY name
HAVING COUNT(barcode) >= 1
ORDER BY COUNT(barcode) DESC;
"""

print("Ma'lumotlar bazadan o'qilmoqda...")
try:
    with engine.connect() as conn:
        df_summary = pd.read_sql(query1, conn)
        df_details = pd.read_sql(query2, conn)
except Exception as e:
    print(f"XATO: So'rovni bajarishda muammo - {e}")
    sys.exit(1)

excel_file = "17185894_tashkilot_analizi.xlsx"

try:
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Umumiy hisobot', index=False)
        df_details.to_excel(writer, sheet_name='Tovarlar ro`yxati', index=False)
    print(f"MUVAFFAQIYATLI: Excel fayl yaratildi -> {excel_file}")
except Exception as e:
    print(f"XATO: Excel faylini saqlashda muammo (openpyxl kutubxonasi bormi?) - {e}")
    print("O'rnatish uchun: pip install pandas openpyxl")
    sys.exit(1)
