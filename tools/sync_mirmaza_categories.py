import os
import sys

# Ensure root dir is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models.category import Category
from app.models.company import Company
from app.services import marketplace_service as mp

def sync_all():
    db = SessionLocal()
    try:
        cats = mp.fetch_categories(force=True)
        print(f"Mir-maza dan {len(cats)} ta kategoriya olindi.")
        if not cats:
            print("Kategoriyalar bo'sh!")
            return

        # Barcha faol korxonalar yoki kod 87427163 bo'lgan korxona
        companies = db.query(Company).all()
        print(f"Jami {len(companies)} ta korxona topildi.")

        for comp in companies:
            created = 0
            updated = 0
            for c in cats:
                name = c["name"].strip()
                sort_order = c.get("sort_order", 0)

                existing = db.query(Category).filter(
                    Category.name == name,
                    Category.company_id == comp.id,
                ).first()

                if existing:
                    if existing.is_deleted:
                        existing.is_deleted = False
                        created += 1
                    else:
                        updated += 1
                    existing.sort_order = sort_order
                else:
                    new_cat = Category(
                        name=name,
                        sort_order=sort_order,
                        company_id=comp.id,
                    )
                    db.add(new_cat)
                    created += 1

            db.commit()
            print(f"Korxona: {comp.name} (ID: {comp.id}, Code: {comp.company_code}) -> +{created} yangi, {updated} yangilandi.")

        print("Muvaffaqiyatli yakunlandi!")
    finally:
        db.close()

if __name__ == "__main__":
    sync_all()
