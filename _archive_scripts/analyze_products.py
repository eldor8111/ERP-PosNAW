import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.models.product import Product

urls = [
    "postgresql://postgres:postgres@localhost:5432/erp_pos",
    "postgresql://erppos:Erppos2025x@localhost:5432/erppos",
    "postgresql://postgres:Erppos2024!@localhost:5432/erppos",
    "postgresql://postgres:postgres@localhost:5432/erppos",
    "postgresql://postgres:postgres@localhost:5432/postgres",
]

engine = None
session = None
for url in urls:
    try:
        print(f"Trying {url}...")
        temp_engine = create_engine(url)
        with temp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine = temp_engine
        print("Connected!")
        break
    except Exception as e:
        print("Failed.")

if not engine:
    print("Could not connect to any database.")
    sys.exit(1)

Session = sessionmaker(bind=engine)
session = Session()

COMPANY_ID = 17185894

products = session.query(Product).filter(Product.company_id == COMPANY_ID, Product.is_deleted == False).all()

total_rows = len(products)
names_count = {}
barcodes_per_name = {}

total_barcodes = 0
all_barcodes = set()

for p in products:
    name = p.name.strip()
    if name not in names_count:
        names_count[name] = 0
        barcodes_per_name[name] = set()
    
    names_count[name] += 1
    
    # main barcode
    if p.barcode:
        barcodes_per_name[name].add(p.barcode)
        all_barcodes.add(p.barcode)
        total_barcodes += 1
        
    # extra barcodes
    if p.extra_barcodes:
        try:
            extra = json.loads(p.extra_barcodes)
            if isinstance(extra, list):
                for eb in extra:
                    barcodes_per_name[name].add(eb)
                    all_barcodes.add(eb)
                    total_barcodes += 1
        except:
            pass

print(f"\n--- TASHKILOT (ID={COMPANY_ID}) TAVARLARI ANALIZI ---")
print(f"Jami yozuvlar (qatorlar) bazada: {total_rows}")
print(f"Barcha shtrix kodlar yig'indisi: {total_barcodes}")
print(f"Takrorlanmas (noyob) shtrix kodlar soni: {len(all_barcodes)}")
print(f"Takrorlanmas (noyob) tovar nomlari soni: {len(names_count)}")

multiple_barcodes_names = {name: bcs for name, bcs in barcodes_per_name.items() if len(bcs) > 1}
print(f"Bitta nom ostida 1 dan ortiq shtrix kodga ega tovar nomlari soni: {len(multiple_barcodes_names)}")

print("\n--- Bitta nomga bir nechta shtrix kod biriktirilgan ba'zi misollar ---")
count = 0
for name, bcs in list(multiple_barcodes_names.items())[:20]:
    print(f"- {name}: {len(bcs)} ta shtrix kod")
    count += 1
