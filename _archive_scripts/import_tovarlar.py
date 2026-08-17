"""
shtrix_kodli_tovarlar.xlsx → tovarlar_catalog jadvaliga import qilish.

Excel ustunlar (aniqlangan):
  0  → ГУРУҲ НОМИ       → group_name
  5  → AТРИБУТ НОМИ     → attribute_name
  6  → МХИК КОДИ        → mxik_code
  7  → МХИК НОМИ        → mxik_name
  8  → ШТРИХ КОДИ       → barcode
  14 → ИМТИЁЗ ИД        → lgota_id

Ishlatish:
    python3 import_tovarlar.py
"""
import os, sys, time

XLSX_PATH  = os.path.join(os.path.dirname(__file__), "shtrix_kodli_tovarlar.xlsx")
DB_URL     = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/erppos")
BATCH_SIZE = 1000

# ── Ustun indekslari (0-dan boshlanadi) ──────────────────────────────────────
COL_GROUP_NAME  = 0
COL_ATTR_NAME   = 5
COL_MXIK_CODE   = 6
COL_MXIK_NAME   = 7
COL_BARCODE     = 8
COL_LGOTA_ID    = 14

# ── 1. Excel o'qish ──────────────────────────────────────────────────────────
print(f"[1/4] Excel o'qilmoqda: {XLSX_PATH}")
t0 = time.time()

import openpyxl
wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb.active

rows_iter = ws.iter_rows(values_only=True)

# Header qatorini o'tkazib yuboramiz
header = next(rows_iter)
print(f"   Ustunlar soni: {len(header)}")
print(f"   Barcode ustuni ({COL_BARCODE}): '{header[COL_BARCODE]}'")
print(f"   MXIK code    ({COL_MXIK_CODE}): '{header[COL_MXIK_CODE]}'")
print(f"   MXIK name    ({COL_MXIK_NAME}): '{header[COL_MXIK_NAME]}'")
print(f"   Group name   ({COL_GROUP_NAME}): '{header[COL_GROUP_NAME]}'")
print(f"   Attribute    ({COL_ATTR_NAME}): '{header[COL_ATTR_NAME]}'")
print(f"   Lgota id     ({COL_LGOTA_ID}): '{header[COL_LGOTA_ID]}'")
print(f"   O'qildi: {time.time()-t0:.2f}s")

# ── 2. DB ulanish ────────────────────────────────────────────────────────────
print(f"\n[2/4] DB ga ulanilmoqda...")
try:
    import psycopg
    conn_str = DB_URL.replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(conn_str)
except (ImportError, Exception):
    try:
        import psycopg2 as psycopg
        conn_str = DB_URL.replace("postgresql+psycopg://", "postgresql://")
        conn = psycopg.connect(conn_str)
    except Exception as e:
        print(f"❌ DB ulanishda xato: {e}")
        sys.exit(1)

cur = conn.cursor()
print("   ✅ DB ga ulandi")

# ── 3. Jadval yaratish ───────────────────────────────────────────────────────
print(f"\n[3/4] Jadval tekshirilmoqda...")
cur.execute("""
CREATE TABLE IF NOT EXISTS tovarlar_catalog (
    id             SERIAL PRIMARY KEY,
    mxik_code      VARCHAR(30) NOT NULL DEFAULT '',
    mxik_name      TEXT,
    barcode        VARCHAR(30) NOT NULL,
    unit_name      VARCHAR(200),
    group_name     TEXT,
    attribute_name TEXT,
    lgota_id       INTEGER,
    CONSTRAINT uq_tovarlar_barcode UNIQUE (barcode)
);
CREATE INDEX IF NOT EXISTS ix_tovarlar_catalog_barcode   ON tovarlar_catalog (barcode);
CREATE INDEX IF NOT EXISTS ix_tovarlar_catalog_mxik_code ON tovarlar_catalog (mxik_code);
""")
conn.commit()
print("   ✅ Jadval tayyor")

# ── 4. Import ─────────────────────────────────────────────────────────────────
print(f"\n[4/4] Import boshlandi (batch={BATCH_SIZE})...")

def safe_str(val, maxlen=None):
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() in ("none", "null"):
        return None
    return s[:maxlen] if maxlen else s

def safe_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

UPSERT_SQL = """
INSERT INTO tovarlar_catalog
    (mxik_code, mxik_name, barcode, unit_name, group_name, attribute_name, lgota_id)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (barcode) DO UPDATE SET
    mxik_code      = EXCLUDED.mxik_code,
    mxik_name      = EXCLUDED.mxik_name,
    unit_name      = EXCLUDED.unit_name,
    group_name     = EXCLUDED.group_name,
    attribute_name = EXCLUDED.attribute_name,
    lgota_id       = EXCLUDED.lgota_id
"""

batch   = []
total   = 0
skipped = 0
t1 = time.time()

for row in rows_iter:
    # Qator uzunligini tekshiramiz
    row_len = len(row)

    barcode = safe_str(row[COL_BARCODE] if COL_BARCODE < row_len else None, 30)
    if not barcode:
        skipped += 1
        continue

    mxik_code = safe_str(row[COL_MXIK_CODE]   if COL_MXIK_CODE  < row_len else None, 30) or ""
    mxik_name = safe_str(row[COL_MXIK_NAME]   if COL_MXIK_NAME  < row_len else None)
    group_     = safe_str(row[COL_GROUP_NAME]  if COL_GROUP_NAME < row_len else None)
    attr_      = safe_str(row[COL_ATTR_NAME]   if COL_ATTR_NAME  < row_len else None)
    lgota_     = safe_int(row[COL_LGOTA_ID]    if COL_LGOTA_ID   < row_len else None)

    batch.append((mxik_code, mxik_name, barcode, None, group_, attr_, lgota_))
    total += 1

    if len(batch) >= BATCH_SIZE:
        cur.executemany(UPSERT_SQL, batch)
        conn.commit()
        batch = []
        elapsed = time.time() - t1
        print(f"   ... {total:,} qator ({elapsed:.0f}s)")

if batch:
    cur.executemany(UPSERT_SQL, batch)
    conn.commit()

wb.close()
conn.close()

elapsed = time.time() - t0
print(f"\n✅ Import muvaffaqiyatli tugadi!")
print(f"   Jami import:               {total:,} qator")
print(f"   O'tkazib yuborilgan:       {skipped:,} qator (barcodesiz)")
print(f"   Umumiy vaqt:               {elapsed:.1f}s")
