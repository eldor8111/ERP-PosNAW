"""
Seed script — test uchun boshlang'ich ma'lumotlar.
Ishlatish: python seed.py
"""
from decimal import Decimal

from app.core.security import hash_password  # type: ignore
from app.database import SessionLocal, engine  # type: ignore
from app.models import (  # type: ignore
    AuditLog, Category, Product, Sale, SaleItem, StockLevel, StockMovement, User, 
    Warehouse, Supplier, PurchaseOrder, POItem, POStatus, Batch,
    ExpenseCategory, Expense, Transaction, Customer, Shift, Branch
)
from app.models.user import UserRole  # type: ignore
from app.database import Base  # type: ignore
from datetime import datetime, timedelta

# Jadvallarni yaratish (agar mavjud bo'lmasa)
Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        # Agar ma'lumotlar allaqachon bor bo'lsa, o'tkazib yuborish
        if db.query(User).count() > 0:
            print("Tozalash amalga oshirilmoqda...")
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            print("Barcha ma'lumotlar tozalandi. Yangi seed boshlanmoqda...")

        print("Seed ma'lumotlari yuklanmoqda...")

        # ── Foydalanuvchilar ─────────────────────────────────────────────
        users = [
            User(name="Admin", phone="998901234567", hashed_password=hash_password("admin123"), role=UserRole.admin),
            User(name="Direktor", phone="998901234568", hashed_password=hash_password("director123"), role=UserRole.director),
            User(name="Kassir 1", phone="998901234569", hashed_password=hash_password("cashier123"), role=UserRole.cashier),
            User(name="Omborchi", phone="998901234570", hashed_password=hash_password("warehouse123"), role=UserRole.warehouse),
            User(name="Buxgalter", phone="998901234571", hashed_password=hash_password("accountant123"), role=UserRole.accountant),
            User(name="Menejer", phone="998901234572", hashed_password=hash_password("manager123"), role=UserRole.manager),
        ]
        db.add_all(users)
        db.flush()
        admin_user = users[0]
        cashier_user = users[2]
        print(f"  [OK] {len(users)} ta foydalanuvchi qo'shildi")

        # ── Filiallar va Omborlar (Warehouses) ───────────────────────────
        branch_main = Branch(name="Asosiy Filial (Toshkent)")
        db.add(branch_main)
        db.flush()

        wh_main = Warehouse(name="Asosiy Ombor (Yunusobod)", type="main", branch_id=branch_main.id)
        wh_shop = Warehouse(name="Kassa Ombori (Chilonzor)", type="shop", branch_id=branch_main.id)
        db.add_all([wh_main, wh_shop])
        db.flush()
        print("  [OK] Filial va Omborlar qo'shildi")

        # ── Ta'minotchilar (Suppliers) ───────────────────────────────────
        sup1 = Supplier(name="Coca-Cola Beverages Uzbekistan", inn="123456789", phone="+998712000000")
        sup2 = Supplier(name="Nestle Uzbekistan", inn="987654321", phone="+998713000000")
        sup3 = Supplier(name="Local Bakery LLC", inn="112233445", phone="+998900001111")
        db.add_all([sup1, sup2, sup3])
        db.flush()
        print("  [OK] Ta'minotchilar qo'shildi")

        # ── Mijozlar (Customers) ─────────────────────────────────────────
        cust1 = Customer(name="Toshmatov Eshmat", phone="+998901112233", debt_balance=Decimal("50000"), debt_limit=Decimal("500000"))
        cust2 = Customer(name="Gulnora Aliyeva", phone="+998935556677", debt_balance=Decimal("0"), debt_limit=Decimal("200000"))
        cust3 = Customer(name="Doimiy mijoz (Noma'lum)", phone="+998990001122", debt_balance=Decimal("150000"), debt_limit=Decimal("150000"))
        db.add_all([cust1, cust2, cust3])
        db.flush()
        print("  [OK] Mijozlar qo'shildi")

        # ── Xarajatlar (Expenses) ────────────────────────────────────────
        exp_cat1 = ExpenseCategory(name="Ijara", description="Oylik do'kon ijarasi")
        exp_cat2 = ExpenseCategory(name="Soliq va yig'imlar", description="Davlat soliqlari")
        exp_cat3 = ExpenseCategory(name="Tushlik", description="Xodimlar tushligi uchun xarajat")
        db.add_all([exp_cat1, exp_cat2, exp_cat3])
        db.flush()

        exp1 = Expense(branch_id=branch_main.id, category_id=exp_cat3.id, amount=Decimal("45000"), description="Bugungi tushlik", approved_by=admin_user.id)
        exp2 = Expense(branch_id=branch_main.id, category_id=exp_cat1.id, amount=Decimal("5000000"), description="Aprel oyi ijarasi", approved_by=admin_user.id)
        db.add_all([exp1, exp2])
        db.flush()
        print("  [OK] Xarajatlar qo'shildi")

        # ── Smenalar (Shifts) ────────────────────────────────────────────
        shift1 = Shift(cashier_id=cashier_user.id, branch_id=branch_main.id, opening_cash=Decimal("100000"))
        db.add(shift1)
        db.flush()
        print("  [OK] Smena ochildi")

        # ── Kategoriyalar ────────────────────────────────────────────────
        cat_oziq = Category(name="Oziq-ovqat", sort_order=1)
        cat_ichimlik = Category(name="Ichimliklar", sort_order=2)
        cat_gigiyena = Category(name="Gigiyena", sort_order=3)
        cat_elektronika = Category(name="Elektronika", sort_order=4)
        db.add_all([cat_oziq, cat_ichimlik, cat_gigiyena, cat_elektronika])
        db.flush()

        cat_non = Category(name="Non va qandolat", parent_id=cat_oziq.id, sort_order=1)
        cat_sut = Category(name="Sut mahsulotlari", parent_id=cat_oziq.id, sort_order=2)
        cat_suv = Category(name="Suv va sharbat", parent_id=cat_ichimlik.id, sort_order=1)
        db.add_all([cat_non, cat_sut, cat_suv])
        db.flush()
        print("  [OK] Kategoriyalar qo'shildi")

        # ── Mahsulotlar ──────────────────────────────────────────────────
        products_data = [
            {"sku": "NON001", "barcode": "4600001000011", "name": "Oq non (450g)", "category_id": cat_non.id,
             "cost_price": Decimal("3500"), "sale_price": Decimal("4500"), "min_stock": 10},
            {"sku": "NON002", "barcode": "4600001000028", "name": "Baton (400g)", "category_id": cat_non.id,
             "cost_price": Decimal("4000"), "sale_price": Decimal("5000"), "min_stock": 5},
            {"sku": "SUT001", "barcode": "4600001000035", "name": "Sut 1L (Nestle)", "category_id": cat_sut.id,
             "cost_price": Decimal("8000"), "sale_price": Decimal("10000"), "min_stock": 20},
            {"sku": "SUT002", "barcode": "4600001000042", "name": "Qatiq 400g", "category_id": cat_sut.id,
             "cost_price": Decimal("5000"), "sale_price": Decimal("7000"), "min_stock": 15},
            {"sku": "SUV001", "barcode": "4600001000059", "name": "Toshkent suvi 1.5L", "category_id": cat_suv.id,
             "cost_price": Decimal("2500"), "sale_price": Decimal("3500"), "min_stock": 50},
            {"sku": "SUV002", "barcode": "4600001000066", "name": "Coca-Cola 1.5L", "category_id": cat_suv.id,
             "cost_price": Decimal("9000"), "sale_price": Decimal("12000"), "min_stock": 30},
            {"sku": "GIG001", "barcode": "4600001000073", "name": "Colgate tish pastasi", "category_id": cat_gigiyena.id,
             "cost_price": Decimal("12000"), "sale_price": Decimal("16000"), "min_stock": 10},
            {"sku": "ELK001", "barcode": "4600001000080", "name": "AA batareyka (2 dona)", "category_id": cat_elektronika.id,
             "cost_price": Decimal("5000"), "sale_price": Decimal("8000"), "min_stock": 20},
        ]

        products = []
        for p_data in products_data:
            p = Product(**p_data)
            db.add(p)
            products.append(p)

        db.flush()
        print(f"  [OK] {len(products)} ta mahsulot qo'shildi")

        # ── Boshlang'ich qoldiqlar (Warehouse 1) ─────────────────────────
        initial_stocks = [100, 50, 80, 60, 200, 100, 40, 80]
        for product, qty in zip(products, initial_stocks):
            stock = StockLevel(product_id=product.id, warehouse_id=wh_main.id, quantity=Decimal(str(qty)))
            db.add(stock)
            movement = StockMovement(
                product_id=product.id,
                type="IN",
                qty_before=Decimal("0"),
                qty_after=Decimal(str(qty)),
                quantity=Decimal(str(qty)),
                user_id=admin_user.id,
                reason="Boshlang'ich qoldiq (seed)",
            )
            db.add(movement)
            
            # Create a batch/lot for each initialized stock
            batch = Batch(
                product_id=product.id,
                warehouse_id=wh_main.id,
                lot_number=f"LOT-SEED-{product.sku}",
                manufacture_date=datetime.utcnow(),
                expiry_date=datetime.utcnow() + timedelta(days=90),
                quantity=Decimal(str(qty))
            )
            db.add(batch)

        # ── Savdo tranzaksiyalari (Sales and Cash Flow) ──────────────────
        sale1 = Sale(number="S-0001", cashier_id=cashier_user.id, total_amount=Decimal("16500"), paid_amount=Decimal("16500"), payment_type="cash")
        db.add(sale1)
        db.flush()
        
        sale_item1 = SaleItem(sale_id=sale1.id, product_id=products[0].id, quantity=Decimal("1"), unit_price=Decimal("4500"), cost_price=Decimal("3500"), subtotal=Decimal("4500"))
        sale_item2 = SaleItem(sale_id=sale1.id, product_id=products[5].id, quantity=Decimal("1"), unit_price=Decimal("12000"), cost_price=Decimal("9000"), subtotal=Decimal("12000"))
        db.add_all([sale_item1, sale_item2])
        
        trans1 = Transaction(branch_id=branch_main.id, type="income", amount=Decimal("16500"), reference_type="sale", reference_id=sale1.id, description="Naqd savdo")
        trans2 = Transaction(branch_id=branch_main.id, type="expense", amount=Decimal("45000"), reference_type="expense", reference_id=exp1.id, description="Tushlik uchun kassa chiqimi")
        db.add_all([trans1, trans2])

        db.flush()
        print("  [OK] Savdolar va Kassa Tranzaksiyalari qo'shildi")

        db.commit()
        print("\nSeed muvaffaqiyatli yakunlandi!")
        print("\nLogin ma'lumotlari:")
        print("  Admin:      phone=998901234567  parol=admin123")
        print("  Direktor:   phone=998901234568  parol=director123")
        print("  Kassir:     phone=998901234569  parol=cashier123")
        print("  Omborchi:   phone=998901234570  parol=warehouse123")
        print("  Buxgalter:  phone=998901234571  parol=accountant123")
        print("  Menejer:    phone=998901234572  parol=manager123")

    except Exception as e:
        db.rollback()
        print(f"Xato: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
